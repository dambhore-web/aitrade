"""
Faithful port of Kite_API_31.py's remove_orders() / remove_orders_before_mkt_close()
(lines ~2937-3220 as of this port) -- the position-MANAGEMENT half of Module B, which
never got ported alongside the entry side (pipeline.py/execution.py). Without this,
an Announcement Trading position gets a one-time static GTT OCO bracket at entry and
is never revisited: no trailing stop-loss, no time/loss-based forced exit, no EOD
square-off. Added 2026-08-17 after the user reported "exit rules are not getting
forced" and traced it to this whole subsystem being missing -- see
docs/requirements.md.

Runs from auto_loop.py's own poll loop, gated to accounts that actually have an open
(quantity>0) position -- same as the original only ever submitting these via
ThreadPoolExecutor when num_open_positions > 0, so a quiet account costs nothing
beyond one kite.positions() call.
"""
import datetime as dt
import json
import logging
from typing import Optional

from . import reference_data

logger = logging.getLogger("announcement_trading.exit_management")

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# In-memory highest-price-seen tracker, keyed by (zerodha_id, symbol) -- matches the
# original's stoploss_df_temp: a plain in-process store, reset on every process
# restart. A restart briefly loses the "ratchet" (the trailing stop resets to
# wherever the entry bracket was instead of wherever it had trailed to since), but no
# open position's own protection is lost -- the GTT bracket itself is broker-side and
# unaffected by a restart; this tracker only decides how much *tighter* to make it.
_high_price: dict[tuple[str, str], float] = {}

# Forced-exit thresholds -- unchanged from the original.
LOSS_TIME_STOP_MINUTES = 2
HARD_TIME_STOP_MINUTES = 10
LOSS_PCT_STOP = -1.0
EOD_SQUARE_OFF_START = dt.time(15, 28)
EOD_SQUARE_OFF_END = dt.time(15, 30)

# The original prices the forced-exit SELL at exactly last_price -- not actually
# marketable for a SELL (needs to be AT OR BELOW the current bid to match
# immediately), so it can sit open indefinitely if price drifts away from it
# afterward, with no re-quote (confirmed live 2026-08-17: ASALCBR's forced-exit
# order sat OPEN as price ticked down away from it). Same slippage-buffer fix
# already used elsewhere in this codebase (new_trade_tool/execution.py) instead of
# reproducing the original's stale-price behavior.
EXIT_SLIPPAGE_PCT = 0.005  # 0.5% buffer, same as new_trade_tool/execution.py


def calculate_factor(minutes_elapsed: float) -> float:
    """Port of calculate_factor() -- the trailing-stop allowance narrows (and past 4
    minutes goes negative, i.e. tighter than the original stop-loss %) the longer a
    position is held."""
    if minutes_elapsed <= 2:
        return 0.4
    elif minutes_elapsed <= 3:
        return 0.3
    elif minutes_elapsed <= 4:
        return 0.1
    else:
        return -0.2


def _rounded_price(symbol: str, exchange: str, price: float) -> float:
    """Port of get_rounded_price() -- round to the symbol's real tick size instead of
    a flat default, using the same inputs/zerodha_equity_list.csv margin_calculator
    already reads."""
    try:
        df = reference_data.zerodha_list_equity()
        row = df[
            (df["tradingsymbol"].str.upper() == symbol.upper())
            & (df["exchange"].str.upper() == exchange.upper())
        ]
        tick_size = float(row.iloc[0]["tick_size"]) if not row.empty else 0.05
        if not tick_size:
            tick_size = 0.05
        return round(round(price / tick_size) * tick_size, 2)
    except Exception:
        logger.debug("tick rounding failed for %s/%s", symbol, exchange, exc_info=True)
        return round(price, 2)


def _find_open_trade_entry(conn, symbol: str) -> Optional[dict]:
    """Most recent placed trade_entries row for this symbol -- carries the
    stop_loss_pct/stop_loss_price/target_price this position's GTT bracket was
    opened with, and (via order_result) each account's gtt_trigger_id."""
    row = conn.execute(
        "SELECT * FROM trade_entries WHERE symbol = ? AND status = 'placed' "
        "ORDER BY id DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    return dict(row) if row else None


def _account_order_result(trade_entry: dict, zerodha_id: str) -> Optional[dict]:
    try:
        results = json.loads(trade_entry.get("order_result") or "{}").get("results") or []
    except Exception:
        return None
    for r in results:
        if r.get("zerodha_id") == zerodha_id and "gtt_trigger_id" in r:
            return r
    return None


def _minutes_since_entry(orders: list[dict], symbol: str) -> float:
    buy_orders = [
        o for o in orders
        if o.get("tradingsymbol") == symbol
        and o.get("transaction_type") == "BUY"
        and o.get("status") == "COMPLETE"
    ]
    if not buy_orders:
        return 999.0  # unknown entry time -- treat as long-held, matching the
        # original's own behavior of not blocking the forced-exit checks on a
        # lookup failure (its except-block falls back to a stale/default high_price
        # rather than skipping the position entirely)
    buy_orders.sort(key=lambda o: o.get("order_timestamp") or "")
    ts_str = buy_orders[-1].get("order_timestamp")
    try:
        entry_time = dt.datetime.strptime(str(ts_str), "%Y-%m-%d %H:%M:%S")
        return (dt.datetime.now() - entry_time).total_seconds() / 60
    except Exception:
        return 999.0


def _find_pending_sell(orders: list[dict], symbol: str) -> Optional[dict]:
    """Most recent still-open SELL order for this symbol, or None.

    Port note: the original's equivalent check (check_if_open_order_exist(),
    Kite_API_31.py:2792) filters on `orders_df['order_type'] == "SELL"` --
    but order_type is Kite's MARKET/LIMIT/SL/SL-M field, never "SELL"
    (that's transaction_type, a different column). That filter can never
    match anything, so the original's own "quantities != qty" half of its
    gate condition is always vacuously true and contributes nothing -- its
    real, live behavior reduces to just "does this symbol have an order in
    the book at all" (its `flag` check, unaffected by that bug). Matching
    that literally would mean blocking on ANY open order for the symbol
    (e.g. an unrelated pending BUY), which isn't a sensible rule to port
    forward on purpose. Checking transaction_type=="SELL" here instead is
    the correct fix, not a faithfulness gap -- it does what the original
    was clearly trying to do."""
    candidates = [
        o for o in orders
        if o.get("tradingsymbol") == symbol
        and o.get("transaction_type") == "SELL"
        and o.get("status") in ("OPEN", "TRIGGER PENDING")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda o: o.get("order_timestamp") or "", reverse=True)
    return candidates[0]


def _reprice_stuck_order(kite, order: dict, new_price: float, zerodha_id: str, symbol: str) -> None:
    """Port of Kite_API_31.py's modify_order() (~line 2285) -- keeps an
    unfilled forced-exit order chasing the current market price via
    kite.modify_order() on the SAME order (not cancel+replace) instead of
    leaving it stale. Without this, once a forced-exit SELL is placed, it's
    never revisited even if the market keeps moving away from it -- the
    exact ASALCBR failure mode (confirmed live 2026-08-17: a forced-exit
    order sat OPEN as price ticked down away from it, unprotected for the
    rest of the day). The initial slippage buffer this order was placed
    with (EXIT_SLIPPAGE_PCT) makes that less likely to matter, but doesn't
    eliminate it on a fast-moving symbol.

    Falls back to cancel + re-place, matching the original, only when Kite
    rejects the modify with "Maximum allowed order modifications exceeded"
    (Kite caps modifications per order)."""
    order_id = order.get("order_id")
    current_price = float(order.get("price") or 0)
    if order_id is None or abs(current_price - new_price) < 0.005:
        return  # already priced correctly (to within a sub-tick rounding
        # difference) -- avoid burning a modification for no real change

    try:
        kite.modify_order(
            variety=kite.VARIETY_REGULAR, order_id=order_id,
            quantity=order.get("quantity"), order_type="LIMIT", price=new_price,
        )
        logger.info(
            "[%s] Re-priced stuck forced-exit %s: %.2f -> %.2f", zerodha_id, symbol, current_price, new_price
        )
    except Exception as e:
        if "Maximum allowed order modifications exceeded" not in str(e):
            logger.error("[%s] Re-pricing forced-exit failed for %s: %r", zerodha_id, symbol, e)
            return
        try:
            kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
            new_order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR, exchange=order.get("exchange"),
                tradingsymbol=symbol, transaction_type="SELL",
                quantity=order.get("quantity"), product=order.get("product"),
                order_type="LIMIT", price=new_price,
            )
            logger.info(
                "[%s] Modification limit hit for %s -- cancelled %s, re-placed %s at %.2f",
                zerodha_id, symbol, order_id, new_order_id, new_price,
            )
        except Exception as e2:
            logger.error("[%s] Cancel+re-place fallback failed for %s: %r", zerodha_id, symbol, e2)


def _replace_triggered_gtt(kite, zerodha_id, symbol, exchange, qty, product, last_price, new_trigger, entry) -> None:
    """One GTT leg already fired but the position is still open (e.g. the target hit
    but only partially, or Kite's own accounting hasn't caught up yet) -- re-place a
    fresh bracket instead of leaving the remaining quantity with no protection.
    Port of place_new_gtt_if_triggered_only(), simplified: that function inspects
    Kite's GTT history to detect the triggered-but-inactive state; here the caller
    (run_cycle) already establishes that condition by comparing get_gtts() against
    the trigger_id on file, so this just does the re-place."""
    target_price = entry.get("target_price")
    if not target_price:
        logger.debug("No target_price on file for %s -- can't re-place GTT", symbol)
        return
    target_price = _rounded_price(symbol, exchange, target_price)
    order_oco = [
        {"exchange": exchange, "tradingsymbol": symbol, "transaction_type": "SELL",
         "quantity": qty, "order_type": "LIMIT", "product": product, "price": new_trigger},
        {"exchange": exchange, "tradingsymbol": symbol, "transaction_type": "SELL",
         "quantity": qty, "order_type": "LIMIT", "product": product, "price": target_price},
    ]
    try:
        gtt = kite.place_gtt(
            trigger_type=kite.GTT_TYPE_OCO, tradingsymbol=symbol, exchange=exchange,
            trigger_values=[new_trigger, target_price], last_price=last_price, orders=order_oco,
        )
        logger.info("[%s] Re-placed triggered GTT for %s: trigger_id=%s", zerodha_id, symbol, gtt["trigger_id"])
    except Exception as e:
        logger.error("[%s] Re-placing GTT failed for %s: %r", zerodha_id, symbol, e)


def _manage_position(kite, conn, zerodha_id: str, position: dict, orders: list[dict], gtts_by_symbol: dict) -> None:
    symbol = position.get("tradingsymbol")
    exchange = position.get("exchange")
    product = position.get("product")
    qty = position.get("quantity") or 0
    if qty <= 0:
        return  # only manages long positions from BUY entries, matching the
        # original's qty>0 checks throughout remove_orders()

    last_price = position.get("last_price") or 0
    pnl = position.get("pnl") or 0
    avg_price = position.get("average_price") or 0
    pnl_pct = ((last_price - avg_price) / avg_price * 100) if avg_price else 0.0

    entry = _find_open_trade_entry(conn, symbol)
    if not entry:
        logger.debug("No trade_entries row for open position %s -- can't manage, skipping", symbol)
        return

    acct_result = _account_order_result(entry, zerodha_id)
    gtt_trigger_id = acct_result.get("gtt_trigger_id") if acct_result else None
    gtt = gtts_by_symbol.get(symbol)

    minutes_elapsed = _minutes_since_entry(orders, symbol)

    key = (zerodha_id, symbol)
    high_price = max(_high_price.get(key, avg_price or last_price), last_price)
    _high_price[key] = high_price

    stop_loss_pct = entry.get("stop_loss_pct")
    if stop_loss_pct is None:
        stop_loss_pct = 0.6
    factor = calculate_factor(minutes_elapsed)
    new_trigger = _rounded_price(symbol, exchange, high_price - (abs(stop_loss_pct) + factor) * high_price / 100)

    now_t = dt.datetime.now(IST).time()
    pending_sell = _find_pending_sell(orders, symbol)
    forced_exit = (
        (pnl < 0 and minutes_elapsed > LOSS_TIME_STOP_MINUTES)
        or (minutes_elapsed > HARD_TIME_STOP_MINUTES)
        or (pnl_pct < LOSS_PCT_STOP)
        or (EOD_SQUARE_OFF_START <= now_t <= EOD_SQUARE_OFF_END)
    )

    if forced_exit:
        exit_price = _rounded_price(symbol, exchange, last_price * (1 - EXIT_SLIPPAGE_PCT))
        if pending_sell:
            # Already have a forced-exit order out for this symbol from an
            # earlier cycle -- re-price it to the current market instead of
            # placing a second, duplicate order (see _reprice_stuck_order()
            # for why this matters).
            _reprice_stuck_order(kite, pending_sell, exit_price, zerodha_id, symbol)
        else:
            try:
                order_id = kite.place_order(
                    variety="regular", exchange=exchange, tradingsymbol=symbol,
                    transaction_type="SELL", quantity=qty, product=product,
                    order_type="LIMIT", price=exit_price,
                )
                logger.info(
                    "[%s] Forced exit %s qty=%s pnl=%.2f pnl_pct=%.2f%% held=%.1fmin price=%.2f order_id=%s",
                    zerodha_id, symbol, qty, pnl, pnl_pct, minutes_elapsed, exit_price, order_id,
                )
            except Exception as e:
                logger.error("[%s] Forced exit failed for %s: %r", zerodha_id, symbol, e)
        # No return here -- the original (Kite_API_31.py:2937 remove_orders())
        # has no continue/return separating this block from the GTT-trail
        # step below either; they're two independent, unconditional checks
        # that both run every cycle, not mutually exclusive. Confirmed by
        # the ASALCBR incident (2026-08-17, docs/requirements.md): the GTT
        # trailed on the very next cycle while its forced-exit SELL was
        # still OPEN, which only happened because the original never gates
        # one on the other. An earlier version of this port DID return here
        # -- correct before today's fix added _find_pending_sell() (which
        # made forced_exit itself no longer flip false once a SELL was
        # pending), but wrong now that forced_exit stays true indefinitely
        # while a position is held past a time-stop: without removing this
        # return, the GTT would never trail again for the rest of the
        # position's life once any forced-exit condition first fired.

    if gtt_trigger_id and gtt and gtt.get("status") == "active":
        old_trigger, target_price = gtt["condition"]["trigger_values"]
        if new_trigger > old_trigger:
            target_price = _rounded_price(symbol, exchange, target_price)
            order_oco = [
                {"exchange": exchange, "tradingsymbol": symbol, "transaction_type": "SELL",
                 "quantity": qty, "order_type": "LIMIT", "product": product, "price": new_trigger},
                {"exchange": exchange, "tradingsymbol": symbol, "transaction_type": "SELL",
                 "quantity": qty, "order_type": "LIMIT", "product": product, "price": target_price},
            ]
            try:
                kite.modify_gtt(
                    trigger_id=int(gtt_trigger_id), trigger_type=kite.GTT_TYPE_OCO,
                    tradingsymbol=symbol, exchange=exchange,
                    trigger_values=[new_trigger, target_price], last_price=last_price,
                    orders=order_oco,
                )
                logger.info(
                    "[%s] Trailed stop for %s: %.2f -> %.2f (target %.2f)",
                    zerodha_id, symbol, old_trigger, new_trigger, target_price,
                )
            except Exception as e:
                logger.error("[%s] modify_gtt failed for %s: %r", zerodha_id, symbol, e)
    elif gtt_trigger_id and not (gtt and gtt.get("status") == "active"):
        # The GTT this position was opened with is no longer active (one leg
        # triggered) but the position is still open -- re-place a fresh bracket
        # instead of leaving it unprotected.
        _replace_triggered_gtt(kite, zerodha_id, symbol, exchange, qty, product, last_price, new_trigger, entry)


def _square_off_all(kite, zerodha_id: str, positions: list[dict], market_protection_pct: float) -> None:
    """Port of remove_orders_before_mkt_close() -- unconditional MARKET-sell of every
    remaining open (qty>0) position. Called only inside the EOD window by run_cycle.

    market_protection_pct: same setting/rationale as execution.py's entry
    orders (see that module for the full ITI incident writeup) -- applied
    here too since a forced EOD square-off sitting unfilled against the
    exchange's own protection band is if anything a bigger problem than a
    slow entry: this has a hard deadline (market close), not just a missed
    opportunity."""
    for p in positions:
        qty = p.get("quantity") or 0
        if qty <= 0:
            continue
        symbol, exchange, product = p.get("tradingsymbol"), p.get("exchange"), p.get("product")
        try:
            order_id = kite.place_order(
                variety="regular", exchange=exchange, tradingsymbol=symbol,
                transaction_type="SELL", quantity=qty, product=product,
                order_type="MARKET", market_protection=market_protection_pct,
            )
            logger.info("[%s] EOD square-off %s qty=%s order_id=%s", zerodha_id, symbol, qty, order_id)
        except Exception as e:
            logger.error("[%s] EOD square-off failed for %s: %r", zerodha_id, symbol, e)


def run_cycle(conn, kite_instances: list[tuple]) -> None:
    """Call once per auto_loop cycle. A no-op (one kite.positions() call) for any
    account with nothing open."""
    from . import db

    market_protection_pct = db.get_settings(conn).get("market_protection_pct", 3.0) or 3.0

    now_t = dt.datetime.now(IST).time()
    in_eod_window = EOD_SQUARE_OFF_START <= now_t <= EOD_SQUARE_OFF_END

    for kite, user in kite_instances:
        zerodha_id = user.get("Zerodha ID", "unknown")
        try:
            positions = (kite.positions() or {}).get("net", [])
        except Exception:
            logger.exception("[%s] kite.positions() failed", zerodha_id)
            continue

        open_positions = [p for p in positions if (p.get("quantity") or 0) > 0]
        if not open_positions:
            continue

        try:
            orders = kite.orders() or []
        except Exception:
            logger.exception("[%s] kite.orders() failed", zerodha_id)
            orders = []

        try:
            gtts = kite.get_gtts() or []
        except Exception:
            logger.exception("[%s] kite.get_gtts() failed", zerodha_id)
            gtts = []
        gtts_by_symbol = {}
        for g in gtts:
            sym = (g.get("condition") or {}).get("tradingsymbol")
            if sym:
                gtts_by_symbol[sym] = g

        for position in open_positions:
            try:
                _manage_position(kite, conn, zerodha_id, position, orders, gtts_by_symbol)
            except Exception:
                logger.exception("[%s] _manage_position failed for %s", zerodha_id, position.get("tradingsymbol"))

        if in_eod_window:
            _square_off_all(kite, zerodha_id, open_positions, market_protection_pct)

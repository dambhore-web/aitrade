"""
The automatic scan-classify-trade loop -- replaces Kite_API_31.py's
the_thread()/job() (schedule.every(1.5).seconds), calling the ported
pipeline instead. Runs as a background thread. Off by default; only starts
on an explicit POST /announcement-trading/auto/start (see router.py),
mirroring the original's own requirement to click START CODE.

Dedup state (which announcements have already been seen this run) is
in-memory only, matching the original's `master_df`/`symbol_store` -- reset
on every start, not persisted across restarts.
"""
import logging
import threading
import time
from typing import Optional

from . import db, exit_management, market_data, pipeline, session
from .broadcaster import broadcaster

logger = logging.getLogger("announcement_trading.auto_loop")

POLL_INTERVAL_SECONDS = 1.5

_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_state_lock = threading.Lock()
_state = {
    "running": False,
    "last_cycle_utc": None,
    "last_error": None,
    "state_bse": None,
    "state_nse": None,
    "processed_count": 0,
}


def get_status() -> dict:
    with _state_lock:
        state = dict(_state)
    state["bse_error"], state["nse_error"] = market_data.get_last_fetch_errors()
    return state


def _set_state(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def start(conn) -> None:
    global _thread
    if is_running():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run, args=(conn,), name="announcement-auto-loop", daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()


def _run(conn) -> None:
    import datetime as dt

    seen_keys: set[str] = set()
    _set_state(running=True, last_error=None)
    logger.info("Automatic trading loop started")

    try:
        while not _stop_event.is_set():
            cycle_start = time.time()
            try:
                settings = db.get_settings(conn)
                hours_back = settings.get("hours_back", 0) or 0

                data, state_nse, state_bse = market_data.fetch_new_announcements(hours_back)
                _set_state(
                    last_cycle_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                    state_bse=state_bse,
                    state_nse=state_nse,
                )

                if not data.empty:
                    try:
                        kite_instances = session.get_kite_instances()
                    except FileNotFoundError:
                        kite_instances = []

                    for _, row in data.iterrows():
                        symbol = row.get("symbol")
                        text = str(row.get("attchmntText") or "")
                        key = f"{symbol}_{text}"
                        if not symbol or key in seen_keys:
                            continue
                        seen_keys.add(key)

                        try:
                            result = pipeline.process_item(row.to_dict(), settings, kite_instances, conn)
                        except Exception:
                            logger.exception("process_item failed for %s", symbol)
                            continue

                        trade_entry_id = None
                        if result.order_placed:
                            # stop_loss_pct/target_pct back-derived from the actual
                            # trigger/target prices execution.py placed the GTT at --
                            # exit_management.py needs the pct (for its trailing-stop
                            # calc) and the absolute prices (to re-place a triggered
                            # GTT) both, so store all four instead of just the two
                            # pre-existing pct columns.
                            stop_loss_pct = target_pct = None
                            if result.current_price:
                                if result.trigger_price is not None:
                                    stop_loss_pct = abs(result.current_price - result.trigger_price) / result.current_price * 100
                                if result.target_price is not None:
                                    target_pct = abs(result.target_price - result.current_price) / result.current_price * 100
                            entry = db.create_trade_entry(
                                conn,
                                {
                                    "announcement_id": None,
                                    "announcement_snapshot": f"{symbol} - {result.category} - {text[:200]}",
                                    "symbol": symbol,
                                    "exchange": "NSE",
                                    "transaction_type": "BUY",
                                    "amount": settings.get("amount"),
                                    "quantity": result.quantity,
                                    "stop_loss_pct": stop_loss_pct,
                                    "target_pct": target_pct,
                                    "stop_loss_price": result.trigger_price,
                                    "target_price": result.target_price,
                                    "notes": "auto-trading loop",
                                },
                            )
                            db.mark_entry_placed(
                                conn, entry["id"], {"results": result.order_results}, "placed"
                            )
                            trade_entry_id = entry["id"]

                        log_row = db.log_activity(
                            conn,
                            {
                                "symbol": symbol,
                                "category": result.category,
                                "sentiment": result.sentiment,
                                "text_snippet": text[:300],
                                "skipped": int(result.skipped),
                                "skip_reason": result.skip_reason,
                                "order_placed": int(result.order_placed),
                                "quantity": result.quantity,
                                "current_price": result.current_price,
                                "trade_entry_id": trade_entry_id,
                                "source": row.get("source"),
                                # result.published_at (what process_item()
                                # actually parsed and used for the
                                # freshness decision) if it got that far,
                                # falling back to the raw feed value
                                # otherwise -- guarantees what's logged is
                                # exactly what was evaluated, not a
                                # separately re-read value that could in
                                # principle differ (2026-08-17).
                                "an_dt": result.published_at or row.get("an_dt"),
                                "attachment_url": row.get("attchmntFile"),
                            },
                        )
                        broadcaster.publish(log_row)
                        with _state_lock:
                            _state["processed_count"] += 1

                # Position management (trailing stop / forced exits / EOD
                # square-off) -- ported 2026-08-17, see exit_management.py's
                # module docstring. Runs every cycle same as the original
                # (Kite_API_31.py's process_user_data() submits remove_orders()
                # every job() tick too); cheap when nothing is open since it's
                # gated per-account on kite.positions() actually returning
                # something with quantity>0.
                try:
                    kite_instances = session.get_kite_instances()
                except FileNotFoundError:
                    kite_instances = []
                if kite_instances:
                    try:
                        exit_management.run_cycle(conn, kite_instances)
                    except Exception:
                        logger.exception("Error in exit_management.run_cycle")

                _set_state(last_error=None)

            except Exception as e:
                logger.exception("Error in auto-trading loop cycle")
                _set_state(last_error=f"{type(e).__name__}: {e}")

            elapsed = time.time() - cycle_start
            _stop_event.wait(max(0.0, POLL_INTERVAL_SECONDS - elapsed))
    finally:
        _set_state(running=False)
        logger.info("Automatic trading loop stopped")

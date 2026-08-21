"""
Equity auto-trading loop -- runs new_trade_tool/scanner.py's real scan +
execute loop as a start/stop-able background thread inside this platform,
instead of a separate standalone script you run by hand. Everything about
*how it trades* is unchanged and reused directly from that file: same
process_symbol_candle_close() (diagnostics -> wisestock_short_setup_afl
strategy -> position gating -> signal save -> execution), same
PositionManager/LiveExitManager/execution.place_trade_live, same DB-polling
loop structure against marketdata.db. It has no WebSocket of its own and
does not write candles -- new_trade_tool/collector.py is still the one
process that must be running separately to keep marketdata.db's candles/
ticks flowing; this loop only reads that DB and places orders, exactly like
the original.

The one deliberate change, per explicit instruction: scanner.py's own
main() calls auth.wait_for_cached_token(), blocking until collector.py's
independent Selenium+TOTP login publishes a token to
access_token_cache.json -- a second, separate Zerodha session from the one
Announcement Trading's "Generate Token" flow establishes. Here it instead
reuses that SAME session (announcement_trading.session.get_kite_instances(),
backed by Trading_bot/kite_instances.pkl) so the whole platform authenticates
once, not twice. Everything downstream of getting a `kite` object is
identical to scanner.py.

PAPER_TRADING is read straight from new_trade_tool/config.py, unmodified --
currently False there, meaning starting this loop places real live orders
via execution.place_trade_live(), the same as running scanner.py directly
would. `mode` in get_status() surfaces which one is active so the UI can
show it plainly rather than leaving it silent.

Importing new_trade_tool's scanner.py module (done lazily, inside _run(),
matching add_new_trade_tool_root_to_path()'s own on-demand pattern rather
than at backend startup) runs its two module-level side effects once, for
the whole aitrade process: reconfiguring stdout/stderr to utf-8, and
monkey-patching urllib3 to force IPv4 for all connections process-wide
(scanner.py's own comment: "this process places real orders, so it matters
here even more than in the collector"). Both are harmless for the rest of
this platform's HTTP calls, but process-wide, not scoped to this module --
worth knowing if something elsewhere ever needs IPv6.
"""
import logging
import threading
import time
import traceback
from typing import Optional

from app.core.legacy_path import add_new_trade_tool_root_to_path
from app.modules.announcement_trading import session as kite_session

logger = logging.getLogger("equity_auto_trading.scanner_loop")

CANDLE_POLL_SECONDS = 3
PRICE_POLL_SECONDS = 2

_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_state_lock = threading.Lock()
_state = {
    "running": False,
    "mode": None,
    "last_cycle_utc": None,
    "last_error": None,
    "open_positions": 0,
    "watchlist_count": 0,
    "last_health_check_utc": None,
    "collector_running": False,
}

# collector.py (candle collection -- separate from the scan/execute loop
# above by original design, see scanner_loop docstring) used to have to be
# started by hand as its own OS process. Real gap found 2026-08-18: it's
# silent when missing -- this loop just never sees a new candle for any
# symbol, which looks identical to "nothing new yet" from in here, so a
# whole day can go by with zero alerts and zero errors anywhere. Now
# started/stopped bundled with this loop instead, in-process (a thread, not
# a subprocess) -- same reasoning as announcements/listener.py: one Python
# process for the whole platform, and aitrade's own Stop button can
# actually reach it, unlike a separately-launched OS process.
_collector_thread: Optional[threading.Thread] = None
_collector_stop_event = threading.Event()


def is_collector_running() -> bool:
    return _collector_thread is not None and _collector_thread.is_alive()


# Both the collector thread and the scan thread below hit the SAME
# marketdata.db file. Before 2026-08-18 each opened its own separate
# sqlite3.Connection with its own separate Python-level threading.Lock --
# harmless while they only ever ran as genuinely separate OS processes (or,
# as it turned out, never actually running at the same time at all -- see
# scanner_loop's audit notes), but once collector was bundled in-process
# alongside this loop, two uncoordinated locks guarding the same file
# produced real "database is locked" errors: each lock only serializes
# writes *within its own holder*, not against the other one. One shared
# connection + one shared lock for both closes that gap -- db_connect()
# already opens with check_same_thread=False and PRAGMA busy_timeout=5000
# (new_trade_tool/db.py), so a single connection reused across both threads
# is exactly what it was already built to support. Created lazily on first
# start() and kept open for the process lifetime -- repeated start/stop
# cycles reuse it rather than reopening, so there's no "who closes it and
# when" coordination needed between the two threads either.
_shared_conn = None
_shared_db_lock = threading.Lock()
_shared_conn_setup_lock = threading.Lock()


def _get_shared_conn():
    global _shared_conn
    with _shared_conn_setup_lock:
        if _shared_conn is None:
            add_new_trade_tool_root_to_path()
            from db import db_connect, db_init
            from config import DB_PATH

            _shared_conn = db_connect(DB_PATH)
            db_init(_shared_conn)
        return _shared_conn


def get_shared_marketdata_conn():
    """Public accessor for other modules that need to read the same
    marketdata.db this loop and the collector share (e.g. app.modules.
    backtest) -- reuses the one connection instead of opening a second,
    independent one against the same file. See _get_shared_conn()'s own
    comment for why that specifically caused real "database is locked"
    errors once collector+scanner traffic overlapped (2026-08-18)."""
    return _get_shared_conn()


def get_status() -> dict:
    with _state_lock:
        state = dict(_state)
    state["collector_running"] = is_collector_running()
    return state


def _set_state(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def _run_collector() -> None:
    add_new_trade_tool_root_to_path()
    from collector import main as collector_main

    conn = _get_shared_conn()
    logger.info("Equity collector thread starting (candle collection)")
    try:
        collector_main(stop_event=_collector_stop_event, conn=conn, db_lock=_shared_db_lock)
    except Exception:
        logger.exception("Equity collector thread crashed")
    logger.info("Equity collector thread stopped")


def start() -> None:
    global _thread, _collector_thread
    if not is_collector_running():
        _collector_stop_event.clear()
        _collector_thread = threading.Thread(target=_run_collector, name="equity-collector", daemon=True)
        _collector_thread.start()
        # Give the collector a head start on loading its session/watchlist/
        # backfill before the scan loop starts polling for candles -- purely
        # cosmetic (the scan loop's own per-symbol "new candle?" check is
        # harmless to run before any candles exist), but avoids a burst of
        # "no new candle" no-ops in the first couple seconds every time.
        time.sleep(1.5)

    if is_running():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run, name="equity-auto-loop", daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()
    _collector_stop_event.set()


def _get_kite():
    """Reuse the Announcement Trading page's session (Trading_bot/
    kite_instances.pkl, built by Kite_API_31.py's "Load User Data") instead
    of scanner.py's own auth.wait_for_cached_token() -- see module
    docstring. First account in the pickled list, same as
    announcement_trading's own execution.py does."""
    instances = kite_session.get_kite_instances()
    if not instances:
        raise RuntimeError("No Kite accounts in session")
    return instances[0][0]


def _run() -> None:
    import datetime as dt

    add_new_trade_tool_root_to_path()
    from db import fetch_latest_prices
    from execution import place_trade_paper, place_trade_live  # noqa: F401 -- imported by scanner's ported call path
    from live_exit import LiveExitManager
    from common import load_watchlist, PositionManager
    from config import EXCHANGE, INTERVAL_MIN, WATCHLIST_CSV, PAPER_TRADING, PRODUCT, QTY
    from scanner import process_symbol_candle_close  # the real, unmodified function

    from . import db as settings_db

    # Own connection to this module's settings DB -- read fresh on every
    # signal via _get_amount() below, so editing the amount in the
    # Settings panel takes effect on the very next signal with no restart
    # needed (see scanner.py's process_symbol_candle_close amount_getter
    # docstring). Opened once per loop start, not per-signal, but the read
    # itself always happens per-signal.
    settings_conn = settings_db.db_connect()
    settings_db.db_init(settings_conn)

    def _get_amount() -> float:
        return float(settings_db.get_settings(settings_conn)["amount"])

    def _get_strategy() -> str:
        return str(settings_db.get_settings(settings_conn)["strategy"])

    mode = "PAPER" if PAPER_TRADING else "LIVE"
    _set_state(running=True, last_error=None, mode=mode, open_positions=0)
    logger.info("Equity auto-trading loop started (mode=%s)", mode)

    try:
        kite = _get_kite()
    except Exception as e:
        logger.exception("Could not obtain Kite session for equity auto-trading")
        _set_state(running=False, last_error=f"{type(e).__name__}: {e}")
        return

    # Shared with the collector thread -- see _get_shared_conn()'s comment.
    # Not closed here anymore: it's reused across repeated start/stop
    # cycles and across both threads, only ever torn down implicitly at
    # process exit.
    conn = _get_shared_conn()
    db_lock = _shared_db_lock

    try:
        symbols = load_watchlist(WATCHLIST_CSV)
    except Exception as e:
        logger.exception("Could not load equity watchlist")
        _set_state(running=False, last_error=f"{type(e).__name__}: {e}")
        return

    position_mgr = PositionManager(conn, db_lock)
    exit_mgr = LiveExitManager(
        kite=kite, conn=conn, db_lock=db_lock,
        paper=PAPER_TRADING, product=PRODUCT, qty=QTY, trail_pct=0.007,
    )
    if not PAPER_TRADING:
        exit_mgr.reconcile_open_positions(EXCHANGE, symbols)
    _set_state(watchlist_count=len(symbols))

    symbol_cache: dict = {}
    cover_lock: set = set()
    last_seen_candle_ts: dict = {}
    iteration = 0

    # --------------------------------------------------
    # Trailing-stop / time-exit: its own dedicated thread, decoupled from
    # the candle-scan loop below. Previously this poll ran inline at the
    # top of that same loop -- harmless most of the time, but at every
    # 15-min candle boundary EVERY symbol in the watchlist simultaneously
    # has a fresh candle, so the scan loop's `for sym in symbols` pass has
    # to fully reprocess the whole watchlist instead of its usual quick
    # "nothing new" skip (measured: 20-40s+ for ~340-535 symbols). While
    # that runs, this poll -- and the time-based forced exit it's
    # responsible for -- couldn't run at all, so a position due to
    # force-close (e.g. at 15:10) could sail right past its cutoff if that
    # slow pass happened to straddle it. Confirmed live 2026-08-20:
    # positions still open well past 15:10, requiring a manual close. This
    # thread now gets its own steady PRICE_POLL_SECONDS cadence no matter
    # how long candle scanning takes. exit_mgr.claim_cover()/
    # release_claim() (see live_exit.py) make this safe against racing the
    # candle-scan loop's own COVER handling for the same symbol.
    # --------------------------------------------------
    price_poll_stop = threading.Event()

    def _price_poll_loop() -> None:
        while not price_poll_stop.is_set():
            try:
                open_syms = exit_mgr.list_open_symbols()
                if open_syms:
                    prices = fetch_latest_prices(conn, EXCHANGE, symbols=open_syms)
                    for s, (ltp, _ts) in prices.items():
                        exit_mgr.on_tick_symbol(EXCHANGE, s, ltp)
            except Exception as e:
                logger.error("Price poll error: %r", e)
            price_poll_stop.wait(PRICE_POLL_SECONDS)

    price_poll_thread = threading.Thread(target=_price_poll_loop, name="equity-price-poll", daemon=True)
    price_poll_thread.start()

    try:
        while not _stop_event.is_set():
            for sym in symbols:
                if _stop_event.is_set():
                    break
                try:
                    row = conn.execute(
                        "SELECT MAX(ts) FROM candles WHERE symbol=? AND exchange=? AND interval=?",
                        (sym, EXCHANGE, INTERVAL_MIN),
                    ).fetchone()
                    latest_ts = row[0] if row else None
                    if latest_ts is None:
                        continue
                    if last_seen_candle_ts.get(sym) == latest_ts:
                        continue
                    last_seen_candle_ts[sym] = latest_ts

                    process_symbol_candle_close(
                        sym, conn, db_lock, symbol_cache, cover_lock, kite, exit_mgr, position_mgr,
                        amount_getter=_get_amount, strategy_getter=_get_strategy,
                    )
                except Exception as e:
                    logger.error("Scan error %s: %r", sym, e)
                    logger.debug(traceback.format_exc())

            iteration += 1
            _set_state(
                last_cycle_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                open_positions=exit_mgr.count_open(),
            )
            if iteration % (600 // max(CANDLE_POLL_SECONDS, 1)) == 0:
                _set_state(last_health_check_utc=dt.datetime.now(dt.timezone.utc).isoformat())

            time.sleep(CANDLE_POLL_SECONDS)
    except Exception as e:
        logger.exception("Equity auto-trading loop crashed")
        _set_state(last_error=f"{type(e).__name__}: {e}")
    finally:
        price_poll_stop.set()
        # conn is the shared connection (see _get_shared_conn()) -- not
        # closed here, since the collector thread may still be using it.
        _set_state(running=False)
        logger.info("Equity auto-trading loop stopped")

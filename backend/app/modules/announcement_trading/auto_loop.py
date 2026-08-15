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

from . import db, market_data, pipeline, session
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
        return dict(_state)


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
                            result = pipeline.process_item(row.to_dict(), settings, kite_instances)
                        except Exception:
                            logger.exception("process_item failed for %s", symbol)
                            continue

                        trade_entry_id = None
                        if result.order_placed:
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
                            },
                        )
                        broadcaster.publish(log_row)
                        with _state_lock:
                            _state["processed_count"] += 1

                _set_state(last_error=None)

            except Exception as e:
                logger.exception("Error in auto-trading loop cycle")
                _set_state(last_error=f"{type(e).__name__}: {e}")

            elapsed = time.time() - cycle_start
            _stop_event.wait(max(0.0, POLL_INTERVAL_SECONDS - elapsed))
    finally:
        _set_state(running=False)
        logger.info("Automatic trading loop stopped")

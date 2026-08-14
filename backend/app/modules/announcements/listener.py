"""
Module A background worker. Runs in a dedicated background thread (not an
asyncio task) so a bug here can never block the FastAPI event loop, and so
the legacy module's own synchronous sqlite3/requests calls don't need an
async rewrite -- same "never take the whole process down" principle already
used by new_trade_tool/collector.py (see docs/requirements.md NFRs).

Reuses announcement_listener_v2.py's functions directly (fetch_announcements,
push_signal, the lock-file single-instance guard, etc.) rather than
reimplementing the polling loop -- only the enrichment + SSE broadcast step
is new.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import psutil
import requests

from app.core.legacy_path import add_legacy_root_to_path, load_legacy_env

from . import db, enrichment
from .broadcaster import broadcaster

logger = logging.getLogger("announcements.listener")

_state_lock = threading.Lock()
_state: dict = {
    "running": False,
    "last_poll_utc": None,
    "last_error": None,
    "auth_expired": False,
}


def get_status() -> dict:
    with _state_lock:
        return dict(_state)


def _set_state(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def start_background_thread() -> None:
    thread = threading.Thread(target=_run, name="announcements-listener", daemon=True)
    thread.start()


def _clear_stale_lock(legacy) -> None:
    """announcement_listener_v2.py's own lock file records only a PID, with
    no liveness check -- fine for its original single-process CLI use, but
    under `uvicorn --reload` an old worker can be torn down before this
    thread's `finally: legacy.release_lock()` runs, leaving a stale lock
    every reload. Clear it here (only when the recorded PID is confirmed
    dead) rather than requiring a manual delete each time."""
    lock_path = legacy.LOCK_PATH
    if not lock_path.exists():
        return
    try:
        pid = int(lock_path.read_text().strip())
    except (ValueError, OSError):
        return
    if not psutil.pid_exists(pid):
        logger.info("Clearing stale listener.lock (dead PID %s)", pid)
        lock_path.unlink(missing_ok=True)


def _run() -> None:
    load_legacy_env()
    add_legacy_root_to_path()

    try:
        import announcement_listener_v2 as legacy
    except SystemExit as e:
        # The legacy module sys.exit()s at import time if TRUEDATA_AUTH_TOKEN
        # is unset -- treat that as "feature disabled", not a crash.
        logger.error("Announcement listener disabled: %s", e)
        _set_state(running=False, last_error=str(e))
        return
    except Exception as e:
        logger.exception("Could not import announcement_listener_v2.py")
        _set_state(running=False, last_error=f"{type(e).__name__}: {e}")
        return

    _clear_stale_lock(legacy)
    try:
        legacy.acquire_lock()
    except SystemExit:
        _set_state(
            running=False,
            last_error="Another listener instance already holds listener.lock "
            "(e.g. the standalone script is running) -- stop it first.",
        )
        return

    try:
        conn = legacy.init_db()
        db.ensure_enrichment_columns(conn)
        _set_state(running=True, last_error=None)
        logger.info("Announcement listener thread started")

        backoff = legacy.POLL_INTERVAL_SECONDS
        while True:
            cycle_start = datetime.now(legacy.IST)
            from_ts = legacy.get_last_from(conn)

            try:
                items = legacy.fetch_announcements(from_ts)
                for item in items:
                    ann_id = legacy.make_announcement_id(item)
                    if not ann_id:
                        continue
                    cur = conn.execute("SELECT 1 FROM seen_announcements WHERE id = ?", (ann_id,))
                    if cur.fetchone() is None:
                        conn.execute(
                            "INSERT INTO seen_announcements (id, first_seen_utc) VALUES (?, ?)",
                            (ann_id, datetime.now(timezone.utc).isoformat()),
                        )
                        conn.commit()
                        legacy.push_signal(conn, item, ann_id)
                        _enrich_and_broadcast(conn, ann_id)

                legacy.set_last_from(conn, cycle_start.strftime("%y%m%d %H:%M:%S"))
                backoff = legacy.POLL_INTERVAL_SECONDS
                _set_state(
                    last_poll_utc=datetime.now(timezone.utc).isoformat(),
                    last_error=None,
                    auth_expired=False,
                )

            except legacy.RateLimited as e:
                backoff = min(backoff * 2, legacy.MAX_BACKOFF_SECONDS)
                logger.warning("Rate-limited, backing off %ss: %s", backoff, e)
                time.sleep(backoff)
                continue

            except requests.exceptions.HTTPError as e:
                if getattr(e.response, "status_code", None) == 401:
                    _set_state(
                        auth_expired=True,
                        last_error="TRUEDATA_AUTH_TOKEN expired (401) -- refresh it in "
                        "Trading_bot/.env and restart the backend.",
                    )
                    logger.error("Auth token expired")
                else:
                    _set_state(last_error=f"{type(e).__name__}: {e}")
                    logger.warning("HTTP error in listener loop: %s", e)

            except Exception as e:
                _set_state(last_error=f"{type(e).__name__}: {e}")
                logger.exception("Unexpected error in listener loop")

            time.sleep(legacy.POLL_INTERVAL_SECONDS)
    finally:
        legacy.release_lock()
        _set_state(running=False)


def _enrich_and_broadcast(conn, ann_id: str) -> None:
    row = conn.execute(
        "SELECT id, captured_utc, announcement_time_ist, stock_name, bse_code, nse_symbol, "
        "exchange, title, message, link, pdf_url, pdf_path FROM signals "
        "WHERE announcement_id = ? ORDER BY id DESC LIMIT 1",
        (ann_id,),
    ).fetchone()
    if row is None:
        return
    cols = [
        "id", "captured_utc", "announcement_time_ist", "stock_name", "bse_code", "nse_symbol",
        "exchange", "title", "message", "link", "pdf_url", "pdf_path",
    ]
    item = dict(zip(cols, row))

    text = f"{item['title'] or ''} {item['message'] or ''}".strip()
    flag: Optional[int] = enrichment.classify_financial_result(text) if text else None
    if flag is not None:
        db.update_financial_result_flag(item["id"], flag)
        item["financial_result_flag"] = flag

    broadcaster.publish(item)

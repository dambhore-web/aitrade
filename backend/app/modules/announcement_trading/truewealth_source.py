"""
Native TrueWealth (TrueData's "wealth" backend) BSE announcement source --
built directly inside aitrade (2026-08-21) as a genuine third data source
alongside the existing NSE/BSE polling in market_data.py, per explicit
instruction to build this in-house rather than wrap the separate
TrueWealthScraper checkout as an external process.

Reuses the auth-capture / API-polling TECHNIQUE that project proved out
against the real TrueData API (see its own truewealth_monitor.py), written
fresh here against this module's own need: feed pipeline.process_item()
directly, not maintain a separate browsable PDF archive. Endpoint, request
shape, and the positional Records array format below are all copied from
that working reference, not guessed.

Runs on its OWN dedicated thread with its own asyncio event loop --
Playwright's async API needs one, and this stays fully independent from
auto_loop.py's own synchronous NSE/BSE thread rather than risking any
change to that already-working loop. Both threads ultimately call the
exact same pipeline.process_item()/gates.symbol_already_qualified_today()
against the same announcement_trading.db, which is what gives "whichever
source sees a given announcement first wins" for free -- no new dedup
logic needed here.

Auth: TrueData's wealth API expects a session Authorization header that
only the logged-in web app itself generates -- there is no static API key.
This launches a real (non-headless -- see start()'s docstring for why)
persistent Chromium context and passively captures that header from the
page's own outgoing requests. The persistent profile is a ONE-TIME copy of
TrueWealthScraper's already-logged-in browser_profile (see _ensure_profile
_copied()), so this doesn't require a fresh interactive login on first run
-- but that captured session will eventually expire, at which point the
captured-auth wait below will keep timing out until someone opens
BROWSER_PROFILE_DIR's browser (or this module's own visible window, since
it runs non-headless) and logs in again.
"""
import asyncio
import datetime as dt
import logging
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("announcement_trading.truewealth_source")

WEALTH_URL = "https://wealth.truedata.in/"
BACKEND_URL = "https://wealthbackendv2.truedata.in"
ANNOUNCEMENT_API = f"{BACKEND_URL}/api/v1/getannouncementsforcompaniesfrom"
POLL_INTERVAL_SECONDS = 15
FEED_TOP = 50
AUTH_WAIT_TIMEOUT_SECONDS = 25

_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_state_lock = threading.Lock()
_state: Dict[str, Any] = {
    "running": False,
    "authorized": False,
    "last_poll_utc": None,
    "last_error": None,
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


def start() -> None:
    """headless=False, matching TrueWealthScraper's own tuned config --
    a real, visible Chromium window will appear when this starts. That
    project's own comments/config suggest this site's SPA or anti-bot
    behavior was unreliable headless; not worth relitigating without
    evidence it's safe to change."""
    global _thread
    if is_running():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_thread, name="truewealth-source", daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()


def _profile_dir() -> Path:
    # aitrade/data/truewealth_browser_profile -- same parents[N]/data
    # pattern as db.py's own DB_PATH in this module.
    return Path(__file__).resolve().parents[4] / "data" / "truewealth_browser_profile"


def _ensure_profile_copied() -> Path:
    """One-time copy of TrueWealthScraper's own already-logged-in
    browser_profile into aitrade's own data dir, so this doesn't need a
    fresh interactive login on first run. Only copies if aitrade's own
    profile dir doesn't exist yet -- never overwrites it on subsequent
    starts, so a session refreshed here (or a fresh manual login done
    directly against this profile) isn't clobbered by a stale source copy
    later."""
    from app.core.config import get_settings

    dest = _profile_dir()
    if dest.exists():
        return dest
    src = get_settings().truewealth_root / "browser_profile"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        logger.info("Copying TrueWealth browser profile %s -> %s", src, dest)
        shutil.copytree(src, dest)
    else:
        logger.warning("No source browser_profile found at %s -- starting blank (needs manual login)", src)
        dest.mkdir(parents=True, exist_ok=True)
    return dest


def _parse_record(raw: Any) -> Optional[Dict[str, Any]]:
    """Positional Records array -> dict. Field order confirmed against
    TrueWealthScraper's own parse_record() -- this is the API's real
    response shape, not guessed."""
    if not isinstance(raw, list) or not raw:
        return None
    announcement_id = raw[0]
    if announcement_id is None:
        return None
    announcement_id = str(announcement_id).strip()
    if not announcement_id:
        return None

    def value(i):
        return raw[i] if i < len(raw) else None

    return {
        "announcement_id": announcement_id,
        "announcement_time": value(1),
        "symbol": value(3),
        "exchange_symbol": value(4),
        "company_name": value(5),
        "title": value(7),
        "description": value(9),
        "category": value(11),
    }


def _parse_feed_response(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    records = data.get("Records")
    if not records:
        return []
    if isinstance(records, str):
        import json

        try:
            records = json.loads(records)
        except Exception:
            return []
    if not isinstance(records, list):
        return []
    out = []
    for raw in records:
        rec = _parse_record(raw)
        if rec:
            out.append(rec)
    return out


def _truewealth_time(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime("%y%m%d %H:%M:%S")


def _already_logged(conn, symbol: str, text_snippet: str) -> bool:
    """Durable, cross-restart duplicate check -- seen_ids (see _run_async)
    only protects against reprocessing within a single run; it resets to
    empty on every restart, and since from_time also resets to "1 hour
    ago" on every restart, anything still inside that fresh window gets
    reprocessed and re-logged once per restart otherwise. Confirmed live
    2026-08-21: 12 duplicate activity_log rows for the same announcement
    text, one per backend restart that day. activity_log has no
    announcement_id column to key off directly, so (symbol, source,
    text_snippet) is the durable identity instead -- the same 300-char
    snippet genuinely repeating for the same symbol from the same source
    is, in practice, always this exact restart-reprocessing case, not two
    coincidentally-identical real announcements."""
    row = conn.execute(
        "SELECT 1 FROM activity_log WHERE symbol = ? AND source = 'TRUEWEALTH_BSE' AND text_snippet = ? LIMIT 1",
        (symbol, text_snippet[:300]),
    ).fetchone()
    return row is not None


def _run_thread() -> None:
    try:
        asyncio.run(_run_async())
    except Exception:
        logger.exception("TrueWealth source thread crashed")
        _set_state(last_error="crashed, see logs")
    finally:
        _set_state(running=False, authorized=False)


async def _run_async() -> None:
    from playwright.async_api import async_playwright

    from . import db, pipeline, session
    from .broadcaster import broadcaster

    profile_dir = _ensure_profile_copied()
    _set_state(running=True, authorized=False, last_error=None)
    logger.info("TrueWealth source starting (profile: %s)", profile_dir)

    authorization: Dict[str, Optional[str]] = {"value": None}

    async def on_request(request):
        try:
            url = request.url
            if "wealthbackendv2.truedata.in" not in url or "/api/v1/" not in url:
                return
            headers = await request.all_headers()
            auth = (headers.get("authorization") or "").strip()
            if auth:
                if not authorization["value"]:
                    logger.info("TrueWealth authorization captured")
                    _set_state(authorized=True)
                authorization["value"] = auth
        except Exception:
            logger.exception("Failed capturing TrueWealth authorization")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-notifications",
                "--disable-popup-blocking",
            ],
        )
        try:
            context.on("request", lambda r: asyncio.ensure_future(on_request(r)))
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(WEALTH_URL, wait_until="domcontentloaded", timeout=60000)

            for _ in range(AUTH_WAIT_TIMEOUT_SECONDS):
                if authorization["value"] or _stop_event.is_set():
                    break
                await asyncio.sleep(1)

            if not authorization["value"]:
                _set_state(last_error=(
                    "No authorization captured -- the browser profile likely isn't "
                    "logged in. Log in in the visible TrueWealth browser window and "
                    "restart this source."
                ))

            conn = db.db_connect()
            db.db_init(conn)

            from_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)

            # TrueData's own "from" filter turned out NOT to be a strict,
            # non-overlapping cursor -- the reference TrueWealthScraper
            # project relies on its own SQLite PRIMARY KEY(announcement_id)
            # to make re-fetching the same record harmless, not on "from"
            # alone. Missing that here meant the same handful of
            # announcements got reprocessed every ~15s cycle indefinitely
            # (confirmed live 2026-08-21: processed_count went 11 -> 80 in
            # under 2 minutes on a quiet after-hours feed). seen_ids is
            # this module's equivalent of auto_loop.py's own seen_keys --
            # in-memory only, reset on every start, matching that same
            # established convention.
            seen_ids: set[str] = set()

            while not _stop_event.is_set():
                cycle_start = dt.datetime.now(dt.timezone.utc)
                try:
                    if authorization["value"]:
                        records = await _fetch(context, authorization["value"], from_time)
                        from_time = cycle_start
                        candidate_records = [r for r in records if r.get("announcement_id") not in seen_ids]
                        for r in candidate_records:
                            seen_ids.add(r["announcement_id"])
                        # Durable check second, only for records seen_ids
                        # didn't already catch (i.e. new this run) -- avoids
                        # a DB round-trip per record on the common path
                        # where seen_ids alone is already sufficient.
                        new_records = [
                            r for r in candidate_records
                            if r.get("symbol")
                            and not _already_logged(conn, r["symbol"], f"{r.get('title') or ''}. {r.get('description') or ''}")
                        ]
                        if new_records:
                            settings = db.get_settings(conn)
                            try:
                                kite_instances = session.get_kite_instances()
                            except FileNotFoundError:
                                kite_instances = []
                            for rec in new_records:
                                _process_record(rec, settings, kite_instances, conn, pipeline, db, broadcaster)
                    _set_state(last_poll_utc=cycle_start.isoformat(), last_error=None)
                except Exception as e:
                    logger.exception("TrueWealth poll cycle failed")
                    _set_state(last_error=f"{type(e).__name__}: {e}")

                elapsed = (dt.datetime.now(dt.timezone.utc) - cycle_start).total_seconds()
                remaining = max(0.0, POLL_INTERVAL_SECONDS - elapsed)
                waited = 0.0
                while waited < remaining and not _stop_event.is_set():
                    step = min(0.5, remaining - waited)
                    await asyncio.sleep(step)
                    waited += step

            conn.close()
        finally:
            await context.close()
            logger.info("TrueWealth source stopped")


async def _fetch(context, auth: str, from_time: dt.datetime) -> List[Dict[str, Any]]:
    url = f"{ANNOUNCEMENT_API}?from={_truewealth_time(from_time)}&duringmarket=false&top={FEED_TOP}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "referer": WEALTH_URL,
        "authorization": auth,
    }
    response = await context.request.get(url, headers=headers, timeout=30000)
    if response.status != 200:
        if response.status == 401:
            logger.warning("TrueWealth API returned 401 -- session likely expired")
        return []
    data = await response.json()
    return _parse_feed_response(data)


def _process_record(rec: dict, settings: dict, kite_instances: list, conn, pipeline, db, broadcaster) -> None:
    """Mirrors auto_loop.py's own per-row body exactly (process_item ->
    trade_entry on success -> activity log -> broadcast), so a
    TrueWealth-sourced trade shows up identically in the Activity feed /
    Orders list to an NSE/BSE-sourced one -- the only difference visible
    anywhere downstream is the `source` tag."""
    symbol = rec.get("symbol")
    if not symbol:
        return
    title = rec.get("title") or ""
    description = rec.get("description") or ""
    text = f"{title}. {description}".strip()

    row = {
        "symbol": symbol,
        "attchmntText": text,
        "an_dt": rec.get("announcement_time"),
        "attchmntFile": None,
        "desc": title,
    }

    try:
        result = pipeline.process_item(row, settings, kite_instances, conn)
    except Exception:
        logger.exception("process_item failed for %s (TrueWealth)", symbol)
        return

    trade_entry_id = None
    if result.order_placed:
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
                "notes": "auto-trading loop (TrueWealth)",
            },
        )
        db.mark_entry_placed(conn, entry["id"], {"results": result.order_results}, "placed")
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
            "source": "TRUEWEALTH_BSE",
            "an_dt": result.published_at or row.get("an_dt"),
            "attachment_url": row.get("attchmntFile"),
        },
    )
    broadcaster.publish(log_row)
    with _state_lock:
        _state["processed_count"] += 1

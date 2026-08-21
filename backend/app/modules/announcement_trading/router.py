import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import auto_loop, db, execution, market_data, session, session_login, truewealth_source
from .broadcaster import broadcaster
from .schemas import (
    ActivityResponse,
    AutoLoopStatus,
    LoginJobStatus,
    PositionsResponse,
    SessionStatus,
    SettingsOut,
    SettingsUpdate,
    TradeEntriesResponse,
    TradeEntryCreate,
    TradeEntryOut,
    TrueWealthStatus,
)

logger = logging.getLogger("announcement_trading.router")
router = APIRouter()

_conn = db.db_connect()
db.db_init(_conn)

# Seed the live NSE session with whatever nsit/nseappid were last saved to
# Settings -- see seed_nse_cookies_from_settings() for why: automatic
# Selenium refresh proved unreliable against Akamai in live testing, this
# manual-paste path is the one that actually works.
_startup_settings = db.get_settings(_conn)
market_data.seed_nse_cookies_from_settings(
    _startup_settings.get("nse_app_id", ""), _startup_settings.get("nse_it", "")
)


@router.get("/settings", response_model=SettingsOut)
def get_settings() -> dict:
    s = db.get_settings(_conn)
    s["telegram_enabled"] = bool(s["telegram_enabled"])
    return s


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate) -> dict:
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "telegram_enabled" in fields:
        fields["telegram_enabled"] = int(fields["telegram_enabled"])
    if not fields:
        raise HTTPException(400, "No fields to update")
    s = db.update_settings(_conn, fields)
    s["telegram_enabled"] = bool(s["telegram_enabled"])
    market_data.seed_nse_cookies_from_settings(s.get("nse_app_id", ""), s.get("nse_it", ""))
    return s


@router.get("/positions", response_model=PositionsResponse)
def positions() -> dict:
    """Symbol-wise P&L across every account in the shared session --
    read-only (kite.positions()), see market_data.get_positions_with_pnl()."""
    if not session.pkl_path().exists():
        return {"items": [], "total_pnl": 0.0}
    items = market_data.get_positions_with_pnl()
    return {"items": items, "total_pnl": round(sum(i["pnl"] for i in items), 2)}


@router.get("/session-status", response_model=SessionStatus)
def session_status() -> dict:
    return session.get_session_status()


@router.post("/session/generate", response_model=LoginJobStatus)
def generate_session() -> dict:
    """Real Selenium logins to every account in Zerodha_Orders.xlsx --
    only ever runs on this explicit call, never automatically."""
    session_login.start_login_job()
    return session_login.get_job_status()


@router.get("/session/generate/status", response_model=LoginJobStatus)
def generate_session_status() -> dict:
    return session_login.get_job_status()


@router.get("/entries", response_model=TradeEntriesResponse)
def list_entries(announcement_id: int | None = None) -> dict:
    return {"entries": db.list_trade_entries(_conn, announcement_id)}


@router.post("/entries", response_model=TradeEntryOut)
def create_entry(body: TradeEntryCreate) -> dict:
    return db.create_trade_entry(_conn, body.model_dump())


@router.post("/entries/{entry_id}/place-order", response_model=TradeEntryOut)
def place_order(entry_id: int) -> dict:
    """Real order placement -- manually triggered per saved entry, never
    automatic. Uses the shared Kite session (kite_instances.pkl) across all
    connected accounts, via a faithful port of Kite_API_31.py's
    place_orders_parallel (see execution.py)."""
    entry = db.get_trade_entry(_conn, entry_id)
    if not entry:
        raise HTTPException(404, "Trade entry not found")
    if entry["status"] != "draft":
        raise HTTPException(400, f"Entry already {entry['status']}, not placing again")

    try:
        kite_instances = session.get_kite_instances()
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))

    settings = db.get_settings(_conn)
    kite = kite_instances[0][0]

    try:
        quote_key = f"{entry['exchange']}:{entry['symbol']}"
        ltp_data = kite.ltp(quote_key)
        current_price = float(ltp_data[quote_key]["last_price"])
    except Exception as e:
        raise HTTPException(502, f"Could not fetch current price for {quote_key}: {e}")

    stop_loss_pct = entry["stop_loss_pct"] if entry["stop_loss_pct"] is not None else settings["gtt_stop_pct"]
    target_pct = entry["target_pct"] if entry["target_pct"] is not None else settings["gtt_target_pct"]
    stop_loss_price = round(current_price - abs(stop_loss_pct) * current_price / 100, 1)
    target_price = round(current_price + target_pct * current_price / 100, 1)

    quantity = entry["quantity"]
    if not quantity:
        amount = entry["amount"] or settings["amount"]
        quantity = max(1, int(amount // current_price)) if amount else 1

    order_type = entry["order_type"] or settings["order_type"]
    product_type = entry["product_type"] or settings["product_type"]

    results = execution.place_orders_parallel(
        kite_instances,
        quantity,
        entry["exchange"],
        entry["symbol"],
        entry["transaction_type"],
        product_type,
        stop_loss_price,
        target_price,
        current_price,
        settings.get("market_protection_pct", 3.0) or 3.0,
    )
    any_ok = any("order_id" in r for r in results)
    return db.mark_entry_placed(_conn, entry_id, {"results": results, "current_price": current_price}, "placed" if any_ok else "failed")


# ---------------------------------------------------------------------
# Automatic trading loop -- off by default, matching Kite_API_31.py's own
# START CODE/STOP CODE requirement (§0 rule 7: nothing trades live until a
# human explicitly arms it).
# ---------------------------------------------------------------------
@router.post("/auto/start", response_model=AutoLoopStatus)
def start_auto_loop() -> dict:
    if not session.pkl_path().exists():
        raise HTTPException(
            409, "No Kite session -- generate a token first (see Window 1) before starting."
        )
    auto_loop.start(_conn)
    return auto_loop.get_status()


@router.post("/auto/stop", response_model=AutoLoopStatus)
def stop_auto_loop() -> dict:
    auto_loop.stop()
    return auto_loop.get_status()


@router.get("/auto/status", response_model=AutoLoopStatus)
def auto_loop_status() -> dict:
    return auto_loop.get_status()


# ---------------------------------------------------------------------
# TrueWealth (TrueData wealth backend) BSE announcement source -- a
# genuinely separate poller from the NSE/BSE auto loop above (see
# truewealth_source.py's module docstring for why), started/stopped
# independently. Runs a real, visible Chromium window when started.
# ---------------------------------------------------------------------
@router.post("/truewealth/start", response_model=TrueWealthStatus)
def start_truewealth() -> dict:
    truewealth_source.start()
    return truewealth_source.get_status()


@router.post("/truewealth/stop", response_model=TrueWealthStatus)
def stop_truewealth() -> dict:
    truewealth_source.stop()
    return truewealth_source.get_status()


@router.get("/truewealth/status", response_model=TrueWealthStatus)
def truewealth_status() -> dict:
    return truewealth_source.get_status()


@router.get("/activity", response_model=ActivityResponse)
def list_activity(limit: int = 100, order_placed: Optional[bool] = None) -> dict:
    return {"items": db.list_activity(_conn, limit, order_placed)}


@router.get("/activity/stream")
async def activity_stream(request: Request) -> StreamingResponse:
    queue = broadcaster.subscribe()

    async def event_gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(event_gen(), media_type="text/event-stream")

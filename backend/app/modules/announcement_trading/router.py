import logging

from fastapi import APIRouter, HTTPException

from . import db, execution, session
from .schemas import (
    SessionStatus,
    SettingsOut,
    SettingsUpdate,
    TradeEntriesResponse,
    TradeEntryCreate,
    TradeEntryOut,
)

logger = logging.getLogger("announcement_trading.router")
router = APIRouter()

_conn = db.db_connect()
db.db_init(_conn)


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
    return s


@router.get("/session-status", response_model=SessionStatus)
def session_status() -> dict:
    return session.get_session_status()


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
    )
    any_ok = any("order_id" in r for r in results)
    return db.mark_entry_placed(_conn, entry_id, {"results": results, "current_price": current_price}, "placed" if any_ok else "failed")

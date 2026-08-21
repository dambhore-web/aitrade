import datetime as dt
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.modules.announcement_trading import session
from app.modules.equity_trading.service import get_conn  # same mode=ro connection helper, same DB

from . import db as settings_db
from . import scanner_loop
from . import watchlist as watchlist_store
from .schemas import (
    EquityAutoLoopStatus,
    EquitySettingsOut,
    EquitySettingsUpdate,
    PositionItem,
    PositionsResponse,
    SignalItem,
    SignalsResponse,
    WatchlistAddRequest,
    WatchlistResponse,
)

router = APIRouter()

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# This module's own settings DB (aitrade/data/equity_auto_trading.db) --
# separate connection from scanner_loop.py's, same reasoning as
# announcement_trading/router.py holding its own `_conn`.
_settings_conn = settings_db.db_connect()
settings_db.db_init(_settings_conn)


@router.get("/settings", response_model=EquitySettingsOut)
def get_settings() -> dict:
    return settings_db.get_settings(_settings_conn)


@router.put("/settings", response_model=EquitySettingsOut)
def update_settings(body: EquitySettingsUpdate) -> dict:
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    return settings_db.update_settings(_settings_conn, fields)


@router.get("/watchlist", response_model=WatchlistResponse)
def get_watchlist() -> dict:
    return {"symbols": watchlist_store.list_symbols()}


@router.post("/watchlist", response_model=WatchlistResponse)
def add_watchlist_symbols(body: WatchlistAddRequest) -> dict:
    """Accepts one or many symbols in a single call -- paste-a-list support,
    same as the batch add the user already relies on for Announcement
    Trading's symbol entry."""
    if not body.symbols:
        raise HTTPException(400, "No symbols given")
    try:
        return {"symbols": watchlist_store.add_symbols(body.symbols)}
    except watchlist_store.WatchlistLockedError as e:
        raise HTTPException(423, str(e))


@router.delete("/watchlist/{symbol}", response_model=WatchlistResponse)
def remove_watchlist_symbol(symbol: str) -> dict:
    try:
        return {"symbols": watchlist_store.remove_symbol(symbol)}
    except watchlist_store.WatchlistLockedError as e:
        raise HTTPException(423, str(e))


@router.post("/start", response_model=EquityAutoLoopStatus)
def start_equity_auto_loop() -> dict:
    if not session.pkl_path().exists():
        raise HTTPException(
            409,
            "No Kite session -- generate a token first (Announcement Trading page) before starting.",
        )
    scanner_loop.start()
    return scanner_loop.get_status()


@router.post("/stop", response_model=EquityAutoLoopStatus)
def stop_equity_auto_loop() -> dict:
    scanner_loop.stop()
    return scanner_loop.get_status()


@router.get("/status", response_model=EquityAutoLoopStatus)
def equity_auto_loop_status() -> dict:
    return scanner_loop.get_status()


@router.get("/signals", response_model=SignalsResponse)
def recent_signals(limit: int = 100, date: Optional[str] = None) -> dict:
    """Read-only view into the signals table scanner_loop writes -- same
    mode=ro connection Module C already uses for this DB, so this endpoint
    can never write to it even by accident.

    Defaults to today (IST) -- a plain "last N signals" with no date filter
    would show stale multi-day-old rows once fewer than `limit` signals have
    fired yet today, which is exactly the confusing case being fixed here.
    Pass date=YYYY-MM-DD (IST) to look at a specific past day instead.
    """
    if date is None:
        date = dt.datetime.now(IST).strftime("%Y-%m-%d")
    else:
        try:
            dt.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, symbol, exchange, interval, ts, dt_ist, signal, close, meta "
            "FROM signals WHERE dt_ist LIKE ? ORDER BY id DESC LIMIT ?",
            (f"{date}%", limit),
        ).fetchall()
        return {"items": [SignalItem(**dict(r)) for r in rows]}
    finally:
        conn.close()


@router.get("/positions", response_model=PositionsResponse)
def open_positions() -> dict:
    """Read-only kite.positions() view, filtered the same way
    LiveExitManager.reconcile_open_positions() decides what it's willing to
    manage: this strategy's own product (MIS), short (quantity<0) only --
    added 2026-08-17 alongside the UI redesign, since /status only ever
    exposed a bare open_positions COUNT and Equity Trading had no
    positions/P&L panel at all (unlike Announcement Trading's
    /announcement-trading/positions, which this mirrors). Not filtered to
    the current watchlist like the reconciler is -- a position that fell
    off the watchlist between restarts should still be visible here, not
    silently hidden."""
    from app.core.legacy_path import add_new_trade_tool_root_to_path

    add_new_trade_tool_root_to_path()
    from config import EXCHANGE, PRODUCT

    try:
        instances = session.get_kite_instances()
    except FileNotFoundError:
        instances = []

    items: list[PositionItem] = []
    total_pnl = 0.0
    for kite, user in instances:
        zerodha_id = user.get("Zerodha ID")
        try:
            net = (kite.positions() or {}).get("net", [])
        except Exception:
            continue
        for p in net:
            qty = p.get("quantity") or 0
            if qty >= 0 or p.get("product") != PRODUCT or p.get("exchange") != EXCHANGE:
                continue
            pnl = float(p.get("pnl") or 0)
            total_pnl += pnl
            items.append(
                PositionItem(
                    zerodha_id=zerodha_id,
                    tradingsymbol=p.get("tradingsymbol") or "",
                    exchange=p.get("exchange") or EXCHANGE,
                    product=p.get("product") or PRODUCT,
                    quantity=qty,
                    average_price=float(p.get("average_price") or 0),
                    last_price=float(p.get("last_price") or 0),
                    pnl=pnl,
                )
            )
    return {"items": items, "total_pnl": round(total_pnl, 2)}

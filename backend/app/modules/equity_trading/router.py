import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.legacy_path import add_new_trade_tool_root_to_path

from . import service
from .schemas import (
    CandlesResponse,
    DiagnosticsResponse,
    EquityStatus,
    LatestPricesResponse,
    SignalsResponse,
    WatchlistResponse,
)

router = APIRouter()

# Defaults sourced from new_trade_tool's own config.py rather than duplicated
# here -- if EXCHANGE/INTERVAL_MIN ever change there, this follows without a
# separate edit.
add_new_trade_tool_root_to_path()
import config as _ntt_config  # noqa: E402

DEFAULT_EXCHANGE = _ntt_config.EXCHANGE
DEFAULT_INTERVAL = _ntt_config.INTERVAL_MIN

# How often the /live WebSocket re-checks latest_price for changes. This is
# a polling bridge, not a true subscription -- collector.py (the sole
# writer) isn't touched to add a push hook, per the read-only NFR.
LIVE_POLL_SECONDS = 2


@router.get("/status", response_model=EquityStatus)
def status(exchange: str = DEFAULT_EXCHANGE, interval: int = DEFAULT_INTERVAL) -> dict:
    return service.get_status(exchange, interval)


@router.get("/watchlist", response_model=WatchlistResponse)
def watchlist() -> dict:
    try:
        return {"symbols": service.load_watchlist()}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.get("/candles", response_model=CandlesResponse)
def candles(
    symbol: str,
    exchange: str = DEFAULT_EXCHANGE,
    interval: int = DEFAULT_INTERVAL,
    limit: int = 300,
) -> dict:
    rows = service.get_candles(symbol, exchange, interval, limit)
    return {"symbol": symbol, "exchange": exchange, "interval": interval, "candles": rows}


@router.get("/diagnostics", response_model=DiagnosticsResponse)
def diagnostics(
    symbol: str,
    exchange: str = DEFAULT_EXCHANGE,
    interval: int = DEFAULT_INTERVAL,
    limit: int = 300,
) -> dict:
    rows = service.get_diagnostics(symbol, exchange, interval, limit)
    return {"symbol": symbol, "exchange": exchange, "interval": interval, "rows": rows}


@router.get("/signals", response_model=SignalsResponse)
def signals(symbol: Optional[str] = None, exchange: str = DEFAULT_EXCHANGE, limit: int = 100) -> dict:
    return {"signals": service.get_signals(symbol, exchange, limit)}


@router.get("/latest-prices", response_model=LatestPricesResponse)
def latest_prices(exchange: str = DEFAULT_EXCHANGE) -> dict:
    return {"exchange": exchange, "prices": service.get_latest_prices(exchange)}


@router.websocket("/live")
async def live(websocket: WebSocket, exchange: str = DEFAULT_EXCHANGE) -> None:
    """Pushes the full latest_price snapshot for `exchange` every
    LIVE_POLL_SECONDS. Empty (collector.py not currently running) is a valid,
    expected state -- the frontend shows that rather than treating it as an
    error."""
    await websocket.accept()
    try:
        while True:
            prices = service.get_latest_prices(exchange)
            await websocket.send_text(json.dumps({"exchange": exchange, "prices": prices}))
            await asyncio.sleep(LIVE_POLL_SECONDS)
    except WebSocketDisconnect:
        pass

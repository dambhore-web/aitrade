from typing import Optional

from pydantic import BaseModel


class EquitySettingsOut(BaseModel):
    amount: int
    strategy: str
    updated_utc: Optional[str] = None


class EquitySettingsUpdate(BaseModel):
    amount: Optional[int] = None
    strategy: Optional[str] = None


class WatchlistResponse(BaseModel):
    symbols: list[str]


class WatchlistAddRequest(BaseModel):
    symbols: list[str]


class EquityAutoLoopStatus(BaseModel):
    running: bool
    mode: Optional[str] = None  # "PAPER" or "LIVE" -- from new_trade_tool/config.py's PAPER_TRADING
    last_cycle_utc: Optional[str] = None
    last_error: Optional[str] = None
    open_positions: int = 0
    watchlist_count: int = 0
    last_health_check_utc: Optional[str] = None
    # Whether the bundled candle-collection thread is alive -- surfaced
    # separately from `running` because the scan loop itself can report
    # running=true with a fresh last_cycle_utc and zero errors while never
    # actually seeing a new candle if collection died independently (found
    # 2026-08-18: this was completely silent before collector.py was
    # bundled into start()/stop() here).
    collector_running: bool = False


class SignalItem(BaseModel):
    id: int
    symbol: str
    exchange: str
    interval: int
    ts: int
    dt_ist: str
    signal: str
    close: float
    meta: Optional[str] = None


class SignalsResponse(BaseModel):
    items: list[SignalItem]


class PositionItem(BaseModel):
    zerodha_id: Optional[str] = None
    tradingsymbol: str
    exchange: str
    product: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float


class PositionsResponse(BaseModel):
    items: list[PositionItem]
    total_pnl: float

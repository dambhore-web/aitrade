from typing import Optional

from pydantic import BaseModel


class WatchlistResponse(BaseModel):
    symbols: list[str]


class CandleOut(BaseModel):
    ts: int
    dt_ist: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class CandlesResponse(BaseModel):
    symbol: str
    exchange: str
    interval: int
    candles: list[CandleOut]


class DiagnosticOut(BaseModel):
    ts: int
    dt_ist: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    VWAP: Optional[float] = None
    EMA20: Optional[float] = None
    EMA50: Optional[float] = None
    VolMA50: Optional[float] = None
    trend: int
    ema_cross_today: int
    fresh_breakdown: int
    recent_vwap_cross: int
    vwap_gt_ema20: int
    vol_basic: int
    vol_confirm: int
    short_filter: int
    Short_condition: int
    Short: int


class DiagnosticsResponse(BaseModel):
    symbol: str
    exchange: str
    interval: int
    rows: list[DiagnosticOut]


class SignalOut(BaseModel):
    id: int
    symbol: str
    exchange: str
    interval: int
    ts: int
    dt_ist: str
    signal: str
    close: float
    meta: Optional[str] = None
    gen_ts: Optional[int] = None
    gen_dt_ist: Optional[str] = None


class SignalsResponse(BaseModel):
    signals: list[SignalOut]


class LatestPriceEntry(BaseModel):
    ltp: float
    ts: int


class LatestPricesResponse(BaseModel):
    exchange: str
    prices: dict[str, LatestPriceEntry]


class EquityStatus(BaseModel):
    exchange: str
    interval: int
    watchlist_count: int
    latest_candle_utc: Optional[str] = None
    latest_price_utc: Optional[str] = None

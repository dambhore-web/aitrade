from typing import Literal, Optional

from pydantic import BaseModel, Field


class AuthStatusResponse(BaseModel):
    authenticated: bool


class ScreenerJobCreateRequest(BaseModel):
    exchange: str = "NSE"
    # Trailing window the ATR/turnover/volatility metrics are computed over.
    lookback_days: int = Field(30, ge=15, le=180)
    atr_period: int = Field(14, ge=5, le=30)
    min_price: float = Field(50, ge=0)
    min_avg_turnover_cr: float = Field(5.0, ge=0)
    min_atr_pct: float = Field(1.5, ge=0)
    max_atr_pct: float = Field(8.0, ge=0)
    # Restricts the universe to NSE's own SERIES == "EQ" listing (normal
    # rolling-settlement equity) via the securities master list -- excludes
    # BE/BZ and other restricted series. Best-effort: if the master list
    # can't be fetched, falls back to Kite's own instrument_type == "EQ"
    # filter alone rather than failing the whole scan.
    eq_series_only: bool = True
    # None = full universe; sensible for a Nifty-500-sized watchlist, but a
    # full NSE EQ scan is ~2000 symbols and will take real time given Kite's
    # historical-data rate limits -- capped by default so a first run
    # doesn't accidentally take 20+ minutes.
    max_symbols: Optional[int] = Field(500, ge=1, le=3000)
    # Explicit override -- scan only these, ignoring eq_series_only/max_symbols.
    symbols: Optional[list[str]] = None
    # Level 2 -- Elder's Triple Screen (weekly tide + daily Elder-ray
    # divergence + volume confirmation), run only against symbols that
    # already passed Level 1 above. Off by default: it needs a much longer
    # per-symbol history fetch (~1yr, for a stable weekly 13-EMA) than
    # Level 1's own lookback_days, so it materially slows a scan down.
    elder_screen: bool = False


class ScreenerJobCreateResponse(BaseModel):
    id: str


class ScreenerRow(BaseModel):
    symbol: str
    last_close: float
    atr: float
    atr_pct: float
    hist_vol_pct: float
    avg_turnover_cr: float
    avg_volume: float
    avg_gap_pct: float
    passes_filters: bool
    score: float
    # Level 2 (Elder Triple Screen) -- only populated when the job requests
    # it, and only ever computed for rows that passed Level 1
    # (passes_filters=True). None means "not run for this row" (Level 2 off,
    # or this row didn't pass Level 1), distinct from a real False result.
    weekly_trend_down: Optional[bool] = None
    divergence_class: Optional[str] = None  # "A" | "B" | None (no divergence found)
    bull_power_shrink_pct: Optional[float] = None
    volume_confirmed: Optional[bool] = None
    elder_passed: Optional[bool] = None


class ScreenerJobStatusResponse(BaseModel):
    id: str
    status: Literal["running", "done", "error", "cancelled"]
    error: Optional[str] = None
    exchange: str
    lookback_days: int
    min_price: float
    min_avg_turnover_cr: float
    min_atr_pct: float
    max_atr_pct: float
    elder_screen: bool
    done_count: int
    total_count: int
    elder_done_count: int
    elder_total_count: int
    log_tail: list[str]
    rows: list[ScreenerRow]

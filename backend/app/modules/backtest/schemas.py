from typing import Literal, Optional

from pydantic import BaseModel, Field


class BacktestJobCreateRequest(BaseModel):
    # None/empty -> every symbol with candles in marketdata.db (matches
    # replay_backtest.py's own "ALL" mode).
    symbols: Optional[list[str]] = None
    # None -> replay every available day for each symbol (the original's
    # own default); either/both bound the replay to a date range instead.
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    # "wisestock" (default) or "breakout" -- see
    # strategy_breakout.breakout_short_setup / replay_backtest.py's own
    # dispatch. Lets a strategy be validated here before it's ever switched
    # on live via equity_auto_trading's settings.
    strategy: str = "wisestock"


class BacktestJobCreateResponse(BaseModel):
    id: str


class TradeRow(BaseModel):
    """Matches AmiBroker's own tradebook report column set -- exactly what
    replay_backtest.py's close_trade() produces, passed straight through."""

    Symbol: str
    Trade: str
    Date: str
    Price: float
    Ex_date: str = Field(alias="Ex. date")
    Ex_Price: float = Field(alias="Ex. Price")
    pct_chg: float = Field(alias="% chg")
    Profit: float
    pct_Profit: float = Field(alias="% Profit")
    Shares: float
    Position_value: float = Field(alias="Position value")
    Cum_Profit: float = Field(alias="Cum. Profit")
    bars: int = Field(alias="# bars")
    Profit_per_bar: Optional[float] = Field(default=None, alias="Profit/bar")
    MAE: Optional[float] = None
    MFE: Optional[float] = None
    Scale_In_Out: str = Field(alias="Scale In/Out")
    Exit_reason: str = Field(alias="Exit reason")

    model_config = {"populate_by_name": True}


class BacktestSummary(BaseModel):
    trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    max_win: float
    max_loss: float


class BacktestJobStatusResponse(BaseModel):
    id: str
    status: Literal["running", "done", "error", "cancelled"]
    error: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    done_count: int
    total_count: int
    signal_count: int
    log_tail: list[str]
    summary: BacktestSummary
    trades: list[TradeRow]

from typing import Any, Optional

from pydantic import BaseModel


class SettingsOut(BaseModel):
    variety: str
    order_type: str
    product_type: str
    hours_back: float
    amount: int
    gtt_stop_pct: float
    gtt_target_pct: float
    nse_app_id: str
    nse_it: str
    telegram_enabled: bool
    updated_utc: Optional[str] = None


class SettingsUpdate(BaseModel):
    variety: Optional[str] = None
    order_type: Optional[str] = None
    product_type: Optional[str] = None
    hours_back: Optional[float] = None
    amount: Optional[int] = None
    gtt_stop_pct: Optional[float] = None
    gtt_target_pct: Optional[float] = None
    nse_app_id: Optional[str] = None
    nse_it: Optional[str] = None
    telegram_enabled: Optional[bool] = None


class AccountStatus(BaseModel):
    zerodha_id: Optional[str] = None
    multiplier: Optional[float] = None
    enabled: Optional[Any] = None


class SessionStatus(BaseModel):
    connected: bool
    account_count: int
    accounts: list[dict]
    session_file_mtime: Optional[float] = None


class TradeEntryCreate(BaseModel):
    announcement_id: Optional[int] = None
    announcement_snapshot: Optional[str] = None
    symbol: str
    exchange: str = "NSE"
    transaction_type: str = "BUY"
    amount: Optional[int] = None
    quantity: Optional[int] = None
    stop_loss_pct: Optional[float] = None
    target_pct: Optional[float] = None
    order_type: Optional[str] = None
    product_type: Optional[str] = None
    variety: Optional[str] = None
    notes: Optional[str] = None


class TradeEntryOut(BaseModel):
    id: int
    announcement_id: Optional[int] = None
    announcement_snapshot: Optional[str] = None
    symbol: str
    exchange: str
    transaction_type: str
    amount: Optional[int] = None
    quantity: Optional[int] = None
    stop_loss_pct: Optional[float] = None
    target_pct: Optional[float] = None
    order_type: Optional[str] = None
    product_type: Optional[str] = None
    variety: Optional[str] = None
    notes: Optional[str] = None
    status: str
    order_result: Optional[str] = None
    created_utc: str
    placed_utc: Optional[str] = None


class TradeEntriesResponse(BaseModel):
    entries: list[TradeEntryOut]


class ActivityItem(BaseModel):
    id: int
    ts_utc: str
    symbol: Optional[str] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None
    text_snippet: Optional[str] = None
    skipped: int
    skip_reason: Optional[str] = None
    order_placed: int
    quantity: Optional[int] = None
    current_price: Optional[float] = None
    trade_entry_id: Optional[int] = None


class ActivityResponse(BaseModel):
    items: list[ActivityItem]


class LoginAccountStatus(BaseModel):
    status: str
    message: str


class LoginJobStatus(BaseModel):
    running: bool
    accounts: dict[str, LoginAccountStatus]
    error: Optional[str] = None


class AutoLoopStatus(BaseModel):
    running: bool
    last_cycle_utc: Optional[str] = None
    last_error: Optional[str] = None
    state_bse: Optional[int] = None
    state_nse: Optional[int] = None
    processed_count: int

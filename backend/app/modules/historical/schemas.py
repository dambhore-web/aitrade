import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

Interval = Literal[
    "minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"
]


class LoginUrlResponse(BaseModel):
    login_url: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    api_key_configured: bool


class CompleteLoginRequest(BaseModel):
    request_token: str


class InstrumentsResponse(BaseModel):
    exchange: str
    symbols: list[str]


class JobCreateRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    exchange: str = "NSE"
    interval: Interval = "day"
    start_date: dt.date
    end_date: dt.date
    incremental: bool = True
    continuous: bool = False


class JobCreateResponse(BaseModel):
    id: str


class SymbolProgressOut(BaseModel):
    status: str
    message: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    error: Optional[str] = None
    exchange: str
    interval: str
    start_date: dt.date
    end_date: dt.date
    progress: dict[str, SymbolProgressOut]
    log_tail: list[str]
    done_count: int
    total_count: int

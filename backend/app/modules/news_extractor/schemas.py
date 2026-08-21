from typing import Literal, Optional

from pydantic import BaseModel


class ExtractionRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    remove_negative: bool = True
    remove_after_market: bool = True
    compute_price_reaction: bool = True


class ExtractionCreateResponse(BaseModel):
    id: str


class NewsRow(BaseModel):
    symbol: Optional[str] = None
    desc: Optional[str] = None
    an_dt: Optional[str] = None
    attchmntFile: Optional[str] = None
    sentiment: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    gain: Optional[float] = None
    max_high_candle: Optional[float] = None
    max_percentage: Optional[float] = None
    category: Optional[str] = None
    symbol_exist: Optional[str] = None


class ExtractionStatusResponse(BaseModel):
    id: str
    status: Literal["running", "done", "error"]
    error: Optional[str] = None
    start_date: str
    end_date: str
    log_tail: list[str]
    row_count: int
    rows: list[NewsRow]


class BonusBuybackAppendRequest(BaseModel):
    pass  # appends the extraction job's own already-computed result; no body needed


class BonusBuybackAppendResponse(BaseModel):
    appended_count: int

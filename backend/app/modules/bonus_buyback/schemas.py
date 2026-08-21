from typing import Literal, Optional

from pydantic import BaseModel


class ExtractionRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    remove_negative: bool = True
    remove_after_market: bool = True


class ExtractionCreateResponse(BaseModel):
    id: str


class ClassifiedRow(BaseModel):
    symbol: Optional[str] = None
    desc: Optional[str] = None
    an_dt: Optional[str] = None
    sentiment: Optional[str] = None
    category: Optional[str] = None
    qualifies: bool = False  # category in {bo_stock_split, buyback}


class ExtractionStatusResponse(BaseModel):
    id: str
    status: Literal["running", "done", "error"]
    error: Optional[str] = None
    start_date: str
    end_date: str
    log_tail: list[str]
    row_count: int
    rows: list[ClassifiedRow]
    appended_count: int = 0


class ExistingRow(BaseModel):
    symbol: Optional[str] = None
    an_dt: Optional[str] = None
    pred_bert: Optional[str] = None


class ExistingListResponse(BaseModel):
    rows: list[ExistingRow]

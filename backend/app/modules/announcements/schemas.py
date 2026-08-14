from typing import Optional

from pydantic import BaseModel


class AnnouncementOut(BaseModel):
    id: int
    captured_utc: Optional[str] = None
    announcement_time_ist: Optional[str] = None
    stock_name: Optional[str] = None
    bse_code: Optional[str] = None
    nse_symbol: Optional[str] = None
    exchange: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    link: Optional[str] = None
    pdf_url: Optional[str] = None
    pdf_path: Optional[str] = None
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    category: Optional[str] = None
    is_bonus_buyback: Optional[int] = None
    financial_result_flag: Optional[int] = None


class AnnouncementsPage(BaseModel):
    items: list[AnnouncementOut]
    total: int
    limit: int
    offset: int


class ListenerStatus(BaseModel):
    running: bool
    last_poll_utc: Optional[str] = None
    last_error: Optional[str] = None
    auth_expired: bool = False

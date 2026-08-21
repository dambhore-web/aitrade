"""
News Extractor service layer -- thin wrapper over the new
Trading_bot/nse_bse_tool_extraction.py (see that file's own docstring for
why it's a separate, from-scratch file rather than an import of the
existing nse_bse_extraction_tool.py desktop tool).

Session: reuses the same shared multi-account Kite session Announcement
Trading's "Generate Token" flow establishes, and the same NSE cookie
session announcement_trading.market_data already knows how to warm --
no separate login, no separate cookie handling.
"""
from kiteconnect import KiteConnect

from app.core.legacy_path import add_legacy_root_to_path
from app.modules.announcement_trading import market_data, reference_data
from app.modules.announcement_trading import session as kite_session

add_legacy_root_to_path()
import nse_bse_tool_extraction as extractor  # noqa: E402  (must follow add_legacy_root_to_path)


def get_kite() -> KiteConnect:
    instances = kite_session.get_kite_instances()
    if not instances:
        raise PermissionError(
            "No Kite session found -- generate a token first (Announcement Trading page) before extracting news."
        )
    return instances[0][0]


def ensure_nse_session_warm() -> None:
    """Best-effort: kick a cookie refresh if the shared NSE session looks
    unseeded. fetch_nse_range() works even with an empty session for most
    date ranges (BSE-style unauthenticated access appears to cover NSE's
    historical corporate-announcements endpoint too, per live testing) --
    this just gives it the best chance of the fuller/authenticated
    response if cookies are available."""
    if not market_data._session.cookies:
        market_data._maybe_refresh_nse_session()

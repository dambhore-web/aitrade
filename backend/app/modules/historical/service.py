"""
Module D service layer -- thin wrapper over the legacy zerodha_api_core.py
(official Kite Connect API based downloader core). No download orchestration
lives here; see jobs.py for that. This module owns: Kite session/auth,
instrument list caching.

Session: reuses the SAME shared multi-account Kite session Announcement
Trading's "Generate Token" flow establishes
(announcement_trading.session.get_kite_instances(), backed by
Trading_bot/kite_instances.pkl), instead of this module's own separate
KITE_API_KEY/SECRET OAuth login (login_url()/complete_login() below, now
unused by get_kite() but left in place in case a standalone flow is ever
needed again). One authenticated session for the whole platform, not one
per tool -- explicit instruction: "Both tools should use the same kite
session common."
"""
import datetime as dt
import threading
from pathlib import Path

import pandas as pd
from kiteconnect import KiteConnect

from app.core.config import get_settings
from app.core.legacy_path import add_legacy_root_to_path
from app.modules.announcement_trading import session as kite_session

add_legacy_root_to_path()
import zerodha_api_core as core  # noqa: E402  (must follow add_legacy_root_to_path)

# Downloaded CSVs live inside aitrade's own data dir, not the legacy tree --
# keeps this repo self-contained. gitignored (see .gitignore's *.csv-free
# pattern -- data/ is ignored wholesale).
OUT_DIR = Path(__file__).resolve().parents[4] / "data" / "historical"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_instruments_cache: dict[str, tuple[dt.date, pd.DataFrame]] = {}
_instruments_lock = threading.Lock()


def get_kite() -> KiteConnect:
    """Return the shared session's first KiteConnect instance, or raise
    PermissionError if no session has been established yet -- same pattern
    as equity_auto_trading.scanner_loop._get_kite()."""
    instances = kite_session.get_kite_instances()
    if not instances:
        raise PermissionError(
            "No Kite session found -- generate a token first (Announcement Trading page) "
            "before downloading."
        )
    return instances[0][0]


def auth_status() -> dict:
    """Reflects the shared session now, not this module's own (unused)
    OAuth flow -- api_key_configured is kept for the frontend's existing
    error message, always True here since there's no separate key to check."""
    try:
        instances = kite_session.get_kite_instances()
        authenticated = len(instances) > 0
    except FileNotFoundError:
        authenticated = False
    return {"authenticated": authenticated, "api_key_configured": True}


def login_url() -> str:
    """Unused now that get_kite() reuses the shared session -- left in
    place (not deleted) in case a standalone Kite Connect API key flow is
    ever needed again independent of Announcement Trading's session."""
    settings = get_settings()
    if not settings.kite_api_key:
        raise RuntimeError("KITE_API_KEY not set in backend/.env")
    return KiteConnect(api_key=settings.kite_api_key).login_url()


def complete_login(request_token: str) -> None:
    """Unused now -- see login_url() docstring."""
    settings = get_settings()
    if not settings.kite_api_key or not settings.kite_api_secret:
        raise RuntimeError("KITE_API_KEY / KITE_API_SECRET not set in backend/.env")
    kite = KiteConnect(api_key=settings.kite_api_key)
    data = kite.generate_session(request_token, api_secret=settings.kite_api_secret)
    core.save_cached_session(settings.kite_api_key, data["access_token"])


def get_instruments_df(exchange: str) -> pd.DataFrame:
    """Kite's instrument_token values can change, so this is never read from
    a stale local file -- fetched live, cached only per-day per exchange."""
    today = dt.date.today()
    with _instruments_lock:
        cached = _instruments_cache.get(exchange)
        if cached and cached[0] == today:
            return cached[1]
    kite = get_kite()
    df = core.get_instruments(kite, exchange)
    with _instruments_lock:
        _instruments_cache[exchange] = (today, df)
    return df


def list_symbols(exchange: str) -> list[str]:
    df = get_instruments_df(exchange)
    return sorted(df["tradingsymbol"].dropna().astype(str).unique().tolist())

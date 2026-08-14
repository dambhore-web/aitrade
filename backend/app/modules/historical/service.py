"""
Module D service layer -- thin wrapper over the legacy zerodha_api_core.py
(official Kite Connect API based downloader core). No download orchestration
lives here; see jobs.py for that. This module owns: Kite session/auth,
instrument list caching.
"""
import datetime as dt
import threading
from pathlib import Path

import pandas as pd
from kiteconnect import KiteConnect

from app.core.config import get_settings
from app.core.legacy_path import add_legacy_root_to_path

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
    """Return an authenticated KiteConnect client, or raise PermissionError
    if the login flow (login_url -> complete_login) hasn't been done today
    -- Kite access tokens expire ~6am IST daily (see zerodha_api_core.py)."""
    settings = get_settings()
    if not settings.kite_api_key:
        raise RuntimeError("KITE_API_KEY not set in backend/.env")
    cached = core.load_cached_session()
    if not cached or cached.get("api_key") != settings.kite_api_key:
        raise PermissionError("Not authenticated with Kite yet today -- complete the login flow first")
    kite = KiteConnect(api_key=settings.kite_api_key)
    kite.set_access_token(cached["access_token"])
    return kite


def auth_status() -> dict:
    settings = get_settings()
    cached = core.load_cached_session()
    authenticated = bool(cached and cached.get("api_key") == settings.kite_api_key)
    return {"authenticated": authenticated, "api_key_configured": bool(settings.kite_api_key)}


def login_url() -> str:
    settings = get_settings()
    if not settings.kite_api_key:
        raise RuntimeError("KITE_API_KEY not set in backend/.env")
    return KiteConnect(api_key=settings.kite_api_key).login_url()


def complete_login(request_token: str) -> None:
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

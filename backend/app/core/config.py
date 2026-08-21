"""
Central settings for the aitrade backend.

LEGACY_ROOT is the one seam every module uses to reach the existing
Trading_bot scripts it wraps (see docs/requirements.md §4) -- fix it here if
the legacy tree ever moves, not in each module.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "aitrade"
    app_env: str = "local"

    # Absolute path to the sibling Trading_bot checkout this backend wraps.
    legacy_root: Path = Path(r"D:\Trading System\Trading_bot")

    # Module C (Equity Trading) wraps new_trade_tool specifically, a
    # separate directory (with its own common.py/utils_time.py/db.py) one
    # level further in -- kept as its own settings field rather than a
    # derived path since that subtree has already moved once before (see
    # its own config.py comment) and may again.
    new_trade_tool_root: Path = Path(
        r"D:\Trading System\Trading_bot\_archive\other_bot_projects\new_trade_tool"
    )

    # TrueWealth (TrueData wealth backend) BSE announcement source -- a
    # sibling checkout (TrueWealthScraper) whose already-logged-in
    # browser_profile this module's own truewealth_source.py copies once
    # (see _ensure_profile_copied()) so aitrade's native Playwright poller
    # doesn't need a fresh interactive login. Only that one directory is
    # ever read from this path; nothing in aitrade imports or runs that
    # project's own script.
    truewealth_root: Path = Path(r"D:\Trading System\TrueWealthScraper")

    # CORS origins allowed to call this API -- just the local Vite dev server
    # and local build preview for now (single-user, local-only platform).
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Official Kite Connect app credentials (Module D: Historical Extractor).
    kite_api_key: str = ""
    kite_api_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

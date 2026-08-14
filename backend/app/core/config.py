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

    # CORS origins allowed to call this API -- just the local Vite dev server
    # and local build preview for now (single-user, local-only platform).
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

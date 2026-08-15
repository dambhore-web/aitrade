"""
aitrade backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000

Module A (TrueData-based announcement listener) is not wired in here --
dropped as unnecessary per user decision; the announcement_trading module's
own BSE/NSE scan already covers corporate announcements end to end. Its
code still lives under app/modules/announcements/ (not deleted, just
unmounted) in case it's wanted again later.
"""
import asyncio
import logging
import logging.handlers
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.announcement_trading.broadcaster import broadcaster as auto_trading_broadcaster
from app.modules.announcement_trading.router import router as announcement_trading_router
from app.modules.equity_trading.router import router as equity_router
from app.modules.historical.router import router as historical_router

# Console output alone scrolls away and is only visible in whatever terminal
# happens to be running uvicorn -- also write everything to a rotating file
# so there's always a fixed place to `tail`/open, independent of which
# terminal (or how many --reload cycles) is currently active. Most of the
# ported pipeline logs at DEBUG (e.g. every get_current_price failure); INFO
# is the default here to keep this readable, bump to DEBUG when actually
# diagnosing something.
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_file_handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=10_000_000, backupCount=3)
_file_handler.setFormatter(_formatter)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(historical_router, prefix="/historical", tags=["historical"])
app.include_router(equity_router, prefix="/equity", tags=["equity"])
app.include_router(
    announcement_trading_router, prefix="/announcement-trading", tags=["announcement-trading"]
)


@app.on_event("startup")
def on_startup() -> None:
    auto_trading_broadcaster.bind_loop(asyncio.get_running_loop())


@app.get("/health")
def health() -> dict:
    """Liveness check -- Phase 0 DoD: this returns 200 from a running process."""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

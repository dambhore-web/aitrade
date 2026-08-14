"""
aitrade backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000
"""
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.announcements.broadcaster import broadcaster
from app.modules.announcements.listener import start_background_thread
from app.modules.announcements.router import router as announcements_router
from app.modules.equity_trading.router import router as equity_router
from app.modules.historical.router import router as historical_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(announcements_router, prefix="/announcements", tags=["announcements"])
app.include_router(historical_router, prefix="/historical", tags=["historical"])
app.include_router(equity_router, prefix="/equity", tags=["equity"])


@app.on_event("startup")
def on_startup() -> None:
    broadcaster.bind_loop(asyncio.get_running_loop())
    start_background_thread()


@app.get("/health")
def health() -> dict:
    """Liveness check -- Phase 0 DoD: this returns 200 from a running process."""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

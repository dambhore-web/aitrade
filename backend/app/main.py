"""
aitrade backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness check -- Phase 0 DoD: this returns 200 from a running process."""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


# Module routers get included here as each one is built, e.g.:
# from app.modules.announcements.router import router as announcements_router
# app.include_router(announcements_router, prefix="/announcements", tags=["announcements"])

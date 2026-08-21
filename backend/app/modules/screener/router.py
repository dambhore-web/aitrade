from fastapi import APIRouter, HTTPException

from . import jobs, service
from .schemas import (
    AuthStatusResponse,
    ScreenerJobCreateRequest,
    ScreenerJobCreateResponse,
    ScreenerJobStatusResponse,
    ScreenerRow,
)

router = APIRouter()


@router.get("/auth/status", response_model=AuthStatusResponse)
def auth_status() -> dict:
    return service.auth_status()


def _job_status_dict(job: jobs.Job) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "exchange": job.exchange,
        "lookback_days": job.lookback_days,
        "min_price": job.min_price,
        "min_avg_turnover_cr": job.min_avg_turnover_cr,
        "min_atr_pct": job.min_atr_pct,
        "max_atr_pct": job.max_atr_pct,
        "elder_screen": job.elder_screen,
        "done_count": job.done_count,
        "total_count": job.total_count,
        "elder_done_count": job.elder_done_count,
        "elder_total_count": job.elder_total_count,
        "log_tail": job.log_lines[-50:],
        # Explicit dataclass -> pydantic conversion (not passed through
        # raw) -- matches historical/router.py's SymbolProgressOut
        # construction; FastAPI's response_model validation doesn't
        # auto-coerce arbitrary dataclass instances into nested BaseModel
        # fields without from_attributes configured, so this is done here
        # rather than relying on that.
        "rows": [ScreenerRow(**vars(r)) for r in job.rows],
    }


@router.post("/jobs", response_model=ScreenerJobCreateResponse)
def create_job(body: ScreenerJobCreateRequest) -> dict:
    job = jobs.create_job(
        exchange=body.exchange,
        lookback_days=body.lookback_days,
        atr_period=body.atr_period,
        min_price=body.min_price,
        min_avg_turnover_cr=body.min_avg_turnover_cr,
        min_atr_pct=body.min_atr_pct,
        max_atr_pct=body.max_atr_pct,
        eq_series_only=body.eq_series_only,
        max_symbols=body.max_symbols,
        symbols=body.symbols,
        elder_screen=body.elder_screen,
    )
    return {"id": job.id}


@router.get("/jobs/{job_id}", response_model=ScreenerJobStatusResponse)
def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_status_dict(job)


@router.post("/jobs/{job_id}/cancel", response_model=ScreenerJobStatusResponse)
def cancel_job(job_id: str) -> dict:
    job = jobs.cancel_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_status_dict(job)

from fastapi import APIRouter, HTTPException

from . import jobs
from .schemas import (
    BacktestJobCreateRequest,
    BacktestJobCreateResponse,
    BacktestJobStatusResponse,
    BacktestSummary,
    TradeRow,
)

router = APIRouter()


def _job_status_dict(job: jobs.Job) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "start_date": job.start_date,
        "end_date": job.end_date,
        "done_count": job.done_count,
        "total_count": job.total_count,
        "signal_count": job.signal_count,
        "log_tail": job.log_lines[-50:],
        "summary": BacktestSummary(**job.summary) if job.summary else BacktestSummary(
            trades=0, win_rate=0.0, total_pnl=0.0, avg_pnl=0.0, max_win=0.0, max_loss=0.0
        ),
        # Extra keys on each trade dict (entry_ts/exit_ts, used internally
        # for sorting) are silently ignored by pydantic's default
        # extra="ignore" -- no need to strip them here.
        "trades": [TradeRow(**t) for t in job.trades],
    }


@router.post("/jobs", response_model=BacktestJobCreateResponse)
def create_job(body: BacktestJobCreateRequest) -> dict:
    job = jobs.create_job(
        symbols=body.symbols, start_date=body.start_date, end_date=body.end_date, strategy=body.strategy
    )
    return {"id": job.id}


@router.get("/jobs/{job_id}", response_model=BacktestJobStatusResponse)
def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_status_dict(job)


@router.post("/jobs/{job_id}/cancel", response_model=BacktestJobStatusResponse)
def cancel_job(job_id: str) -> dict:
    job = jobs.cancel_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_status_dict(job)

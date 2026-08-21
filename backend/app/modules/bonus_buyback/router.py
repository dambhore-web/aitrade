import datetime as dt

import numpy as np
from fastapi import APIRouter, HTTPException

from . import jobs, service
from .jobs import QUALIFYING_CATEGORIES
from .schemas import (
    ClassifiedRow,
    ExistingListResponse,
    ExistingRow,
    ExtractionCreateResponse,
    ExtractionRequest,
    ExtractionStatusResponse,
)

router = APIRouter()


@router.get("/auth/status")
def auth_status() -> dict:
    try:
        service.get_kite()
        return {"authenticated": True}
    except PermissionError:
        return {"authenticated": False}


@router.get("/existing", response_model=ExistingListResponse)
def existing() -> dict:
    df = service.read_existing_bonus_buyback()
    clean = df.replace({np.nan: None})
    rows = [ExistingRow(**r) for r in clean.to_dict("records")]
    return {"rows": rows}


@router.post("/jobs", response_model=ExtractionCreateResponse)
def create_job(body: ExtractionRequest) -> dict:
    try:
        start = dt.date.fromisoformat(body.start_date)
        end = dt.date.fromisoformat(body.end_date)
    except ValueError:
        raise HTTPException(400, "start_date/end_date must be YYYY-MM-DD")
    if start > end:
        raise HTTPException(400, "start_date must not be after end_date")

    job = jobs.create_job(
        start_date=start,
        end_date=end,
        remove_negative=body.remove_negative,
        remove_after_market=body.remove_after_market,
    )
    return {"id": job.id}


@router.get("/jobs/{job_id}", response_model=ExtractionStatusResponse)
def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    rows = []
    if job.status == "done" and job.result is not None and not job.result.empty:
        clean = job.result.replace({np.nan: None})
        for r in clean.to_dict("records"):
            rows.append(
                ClassifiedRow(
                    symbol=r.get("symbol"),
                    desc=r.get("desc"),
                    an_dt=r.get("an_dt"),
                    sentiment=r.get("sentiment"),
                    category=r.get("category"),
                    qualifies=r.get("category") in QUALIFYING_CATEGORIES,
                )
            )

    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "start_date": job.start_date.isoformat(),
        "end_date": job.end_date.isoformat(),
        "log_tail": job.log_lines[-50:],
        "row_count": len(rows),
        "rows": rows,
        "appended_count": job.appended_count,
    }

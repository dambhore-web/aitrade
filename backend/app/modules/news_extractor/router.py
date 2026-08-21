import datetime as dt

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from . import jobs, service
from .schemas import (
    BonusBuybackAppendResponse,
    ExtractionCreateResponse,
    ExtractionRequest,
    ExtractionStatusResponse,
    NewsRow,
)

router = APIRouter()


def _rows_from_df(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    clean = df.replace({np.nan: None})
    return clean.to_dict("records")


@router.get("/auth/status")
def auth_status() -> dict:
    try:
        service.get_kite()
        return {"authenticated": True}
    except PermissionError:
        return {"authenticated": False}


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
        compute_price_reaction=body.compute_price_reaction,
    )
    return {"id": job.id}


@router.get("/jobs/{job_id}", response_model=ExtractionStatusResponse)
def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    rows = _rows_from_df(job.result) if job.status == "done" else []
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "start_date": job.start_date.isoformat(),
        "end_date": job.end_date.isoformat(),
        "log_tail": job.log_lines[-50:],
        "row_count": len(rows),
        "rows": [NewsRow(**{k: v for k, v in r.items() if k in NewsRow.model_fields}) for r in rows],
    }


@router.post("/jobs/{job_id}/append-bonus-buyback", response_model=BonusBuybackAppendResponse)
def append_bonus_buyback(job_id: str) -> dict:
    """Explicit opt-in step: appends any bo_stock_split/buyback category
    rows from this job's result to inputs/bonus_buyback.csv -- the exact
    file the live announcement-trading auto-loop's already_processed()
    gate reads to stop repeat orders on a symbol/category it's already
    seen (see gates.py). Not run automatically -- see
    nse_bse_tool_extraction.append_bonus_buyback()'s docstring for why.
    A dedicated Bonus/Buyback Download page (app/modules/bonus_buyback/)
    also drives this same function as its main action."""
    job = jobs.get_job(job_id)
    if not job or job.status != "done" or job.result is None:
        raise HTTPException(400, "Job not found or not finished yet")
    if job.result.empty or "category" not in job.result.columns:
        return {"appended_count": 0}
    appended = service.extractor.append_bonus_buyback(job.result)
    return {"appended_count": len(appended)}

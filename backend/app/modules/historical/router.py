import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from . import jobs, service
from .schemas import (
    AuthStatusResponse,
    CompleteLoginRequest,
    InstrumentsResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    LoginUrlResponse,
    SymbolProgressOut,
)

router = APIRouter()


@router.get("/auth/status", response_model=AuthStatusResponse)
def auth_status() -> dict:
    return service.auth_status()


@router.get("/auth/login-url", response_model=LoginUrlResponse)
def get_login_url() -> dict:
    try:
        return {"login_url": service.login_url()}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/auth/session", response_model=AuthStatusResponse)
def complete_login(body: CompleteLoginRequest) -> dict:
    try:
        service.complete_login(body.request_token)
    except Exception as e:
        raise HTTPException(400, f"Login failed: {e}")
    return service.auth_status()


@router.get("/instruments", response_model=InstrumentsResponse)
def instruments(exchange: str = "NSE") -> dict:
    try:
        return {"exchange": exchange, "symbols": service.list_symbols(exchange)}
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/jobs", response_model=JobCreateResponse)
def create_job(body: JobCreateRequest) -> dict:
    job = jobs.create_job(
        symbols=body.symbols,
        exchange=body.exchange,
        interval=body.interval,
        start_date=body.start_date,
        end_date=body.end_date,
        incremental=body.incremental,
        continuous=body.continuous,
    )
    return {"id": job.id}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    done = sum(1 for p in job.progress.values() if p.status in ("success", "failed"))
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "exchange": job.exchange,
        "interval": job.interval,
        "start_date": job.start_date,
        "end_date": job.end_date,
        "progress": {
            s: SymbolProgressOut(status=p.status, message=p.message) for s, p in job.progress.items()
        },
        "log_tail": job.log_lines[-50:],
        "done_count": done,
        "total_count": len(job.progress),
    }


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str) -> StreamingResponse:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.result_paths:
        raise HTTPException(400, "No results available yet")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for symbol, path in job.result_paths.items():
            zf.write(path, arcname=f"{symbol}.csv")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=historical_{job_id[:8]}.zip"},
    )

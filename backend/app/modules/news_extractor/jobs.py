"""
In-memory job registry for news-extraction runs -- same scoping call as
historical/jobs.py: single-user, single local process, jobs don't survive a
backend restart.
"""
import datetime as dt
import threading
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from . import service
from .service import extractor

JobStatus = Literal["running", "done", "error"]


@dataclass
class Job:
    id: str
    start_date: dt.date
    end_date: dt.date
    remove_negative: bool
    remove_after_market: bool
    compute_price_reaction: bool
    status: JobStatus = "running"
    error: Optional[str] = None
    log_lines: list[str] = field(default_factory=list)
    result: Optional[pd.DataFrame] = None


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def create_job(
    start_date: dt.date,
    end_date: dt.date,
    remove_negative: bool = True,
    remove_after_market: bool = True,
    compute_price_reaction: bool = True,
) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        start_date=start_date,
        end_date=end_date,
        remove_negative=remove_negative,
        remove_after_market=remove_after_market,
        compute_price_reaction=compute_price_reaction,
    )
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _jobs_lock:
        return _jobs.get(job_id)


def _run_job(job: Job) -> None:
    def log_cb(msg: str) -> None:
        job.log_lines.append(msg)

    try:
        kite = service.get_kite()
        service.ensure_nse_session_warm()

        from app.modules.announcement_trading import market_data, reference_data

        df = extractor.run_extraction(
            start_date=dt.datetime.combine(job.start_date, dt.time.min),
            end_date=dt.datetime.combine(job.end_date, dt.time.min),
            kite=kite,
            symbol_df=reference_data.zerodha_list_equity(),
            bse_symbol_map=reference_data.symbol_list(),
            nse_session=market_data._session,
            nse_headers=market_data.NSE_HEADERS,
            remove_negative=job.remove_negative,
            remove_after_market=job.remove_after_market,
            compute_price_reaction=job.compute_price_reaction,
            progress_cb=log_cb,
        )
        job.result = df
        job.status = "done"
    except Exception as e:
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
        job.log_lines.append(job.error)

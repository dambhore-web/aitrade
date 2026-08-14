"""
In-memory job registry for historical download jobs. Single-user, single
local process -- no need for a persisted job store yet (jobs don't survive
a backend restart; see docs/requirements.md open-questions log for this
scoping call).
"""
import datetime as dt
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Literal, Optional

from . import service

SymbolStatus = Literal["pending", "running", "success", "failed"]
JobStatus = Literal["running", "done", "error"]


@dataclass
class SymbolProgress:
    status: SymbolStatus = "pending"
    message: str = ""


@dataclass
class Job:
    id: str
    symbols: list[str]
    exchange: str
    interval: str
    start_date: dt.date
    end_date: dt.date
    incremental: bool
    continuous: bool
    status: JobStatus = "running"
    error: Optional[str] = None
    progress: dict[str, SymbolProgress] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)
    result_paths: dict[str, str] = field(default_factory=dict)


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="historical-job")


def create_job(
    symbols: list[str],
    exchange: str,
    interval: str,
    start_date: dt.date,
    end_date: dt.date,
    incremental: bool = True,
    continuous: bool = False,
) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        symbols=symbols,
        exchange=exchange,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        incremental=incremental,
        continuous=continuous,
    )
    for s in symbols:
        job.progress[s] = SymbolProgress()
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _jobs_lock:
        return _jobs.get(job_id)


def _run_job(job: Job) -> None:
    try:
        kite = service.get_kite()
        instruments_df = service.get_instruments_df(job.exchange)
    except Exception as e:
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
        return

    futures = {}
    for symbol in job.symbols:
        job.progress[symbol].status = "running"

        def log_cb(msg: str, _symbol: str = symbol) -> None:
            job.log_lines.append(f"[{_symbol}] {msg}")

        future = _executor.submit(
            service.core.download_symbol,
            kite,
            instruments_df,
            symbol,
            job.interval,
            str(service.OUT_DIR),
            job.start_date,
            job.end_date,
            job.incremental,
            job.continuous,
            log_cb,
        )
        futures[future] = symbol

    for future in as_completed(futures):
        symbol = futures[future]
        try:
            sym, ok, message = future.result()
            job.progress[sym].status = "success" if ok else "failed"
            job.progress[sym].message = message
            if ok:
                job.result_paths[sym] = str(service.OUT_DIR / f"{sym}.csv")
        except Exception as e:
            job.progress[symbol].status = "failed"
            job.progress[symbol].message = f"{type(e).__name__}: {e}"

    job.status = "done"

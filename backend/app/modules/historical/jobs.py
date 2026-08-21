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
from pathlib import Path
from typing import Literal, Optional

from . import service

SymbolStatus = Literal["pending", "running", "success", "failed"]
JobStatus = Literal["running", "done", "error", "cancelled"]


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
    output_dir: str
    status: JobStatus = "running"
    error: Optional[str] = None
    progress: dict[str, SymbolProgress] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)
    result_paths: dict[str, str] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    # Populated once _run_job submits work, so cancel_job() can reach the
    # actual Future objects -- Future.cancel() only succeeds on one that's
    # still queued (not yet picked up by a worker thread), which is exactly
    # the set of symbols a cancel click can still stop before they start.
    futures: dict = field(default_factory=dict)


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
    output_dir: Optional[str] = None,
) -> Job:
    # Blank/omitted -> the existing default (aitrade/data/historical); a
    # provided path must exist as (or be creatable as) a real directory --
    # fails the job with a clear error rather than silently falling back,
    # since silently writing somewhere other than what was typed is worse
    # than just telling you the path's bad.
    resolved_dir = str(service.OUT_DIR)
    if output_dir and output_dir.strip():
        target = Path(output_dir.strip())
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            job = Job(
                id=str(uuid.uuid4()), symbols=symbols, exchange=exchange, interval=interval,
                start_date=start_date, end_date=end_date, incremental=incremental,
                continuous=continuous, output_dir=output_dir, status="error",
                error=f"Can't use download path {output_dir!r}: {e}",
            )
            with _jobs_lock:
                _jobs[job.id] = job
            return job
        resolved_dir = str(target)

    job = Job(
        id=str(uuid.uuid4()),
        symbols=symbols,
        exchange=exchange,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        incremental=incremental,
        continuous=continuous,
        output_dir=resolved_dir,
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


def cancel_job(job_id: str) -> Optional[Job]:
    """Stops every symbol that hasn't started downloading yet. Can't safely
    abort one already in flight (Kite's SDK gives no cancellation hook, and
    killing the thread mid-write risks a half-written CSV) -- so the up to
    `max_workers` symbols a worker thread has already picked up finish
    normally, and everything still queued behind them is cancelled via
    Future.cancel(), which only succeeds on a future a worker hasn't
    started yet -- exactly the set this can still stop in time. Returns
    None if the job doesn't exist or has already finished (nothing left to
    cancel)."""
    job = get_job(job_id)
    if job is None or job.status != "running":
        return job
    job.cancel_event.set()
    for future, symbol in job.futures.items():
        if future.cancel():
            job.progress[symbol].status = "failed"
            job.progress[symbol].message = "Cancelled"
    return job


def _run_job(job: Job) -> None:
    try:
        kite = service.get_kite()
        instruments_df = service.get_instruments_df(job.exchange)
    except Exception as e:
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
        return

    # Every future is submitted upfront (ThreadPoolExecutor.submit() only
    # queues -- it doesn't block on max_workers), so a cancel click can
    # never arrive early enough to catch this loop mid-way; job.futures is
    # populated here specifically so cancel_job() can reach back in and
    # Future.cancel() whatever's still queued once it does.
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
            job.output_dir,
            job.start_date,
            job.end_date,
            job.incremental,
            job.continuous,
            log_cb,
        )
        futures[future] = symbol
    job.futures = futures

    # Covers the narrow race where cancel_job() ran between job creation
    # and this point (it would have found job.futures still empty and had
    # nothing to Future.cancel() yet) -- catch up now so a cancel click
    # during the brief kite/instruments setup above isn't silently lost.
    if job.cancel_event.is_set():
        for future, symbol in futures.items():
            if future.cancel():
                job.progress[symbol].status = "failed"
                job.progress[symbol].message = "Cancelled"

    for future in as_completed(futures):
        symbol = futures[future]
        if future.cancelled():
            # cancel_job() already set progress/message for this one --
            # nothing left to do here except not overwrite it.
            continue
        try:
            sym, ok, message = future.result()
            job.progress[sym].status = "success" if ok else "failed"
            job.progress[sym].message = message
            if ok:
                job.result_paths[sym] = str(Path(job.output_dir) / f"{sym}.csv")
        except Exception as e:
            job.progress[symbol].status = "failed"
            job.progress[symbol].message = f"{type(e).__name__}: {e}"

    if job.cancel_event.is_set():
        job.status = "cancelled"
        cancelled_count = sum(1 for p in job.progress.values() if p.message == "Cancelled")
        job.log_lines.append(
            f"Cancelled -- {cancelled_count} symbol(s) stopped before starting; "
            "any already in progress were left to finish."
        )
    else:
        job.status = "done"

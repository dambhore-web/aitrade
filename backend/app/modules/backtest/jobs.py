"""
In-memory job registry for backtest runs -- same pattern as
historical/jobs.py and screener/jobs.py (single-user, single local process,
jobs don't survive a backend restart), including the same Future.cancel()
based cancellation.

Deliberate deviation from replay_backtest.py's own orchestration: that file
parallelizes with ProcessPoolExecutor (real OS processes) -- awkward to embed
inside a running FastAPI/uvicorn process on Windows (spawning a Process
re-imports the main module, which this backend isn't structured for). Uses
the SAME ThreadPoolExecutor-based job pattern every other tool in this app
already uses instead. The actual per-symbol work is mostly pandas/sqlite
I/O, which releases the GIL for a good share of its time, so this still
parallelizes reasonably -- correctness and embeddability matter more here
than matching the original's exact process count.
"""
import threading
import uuid
from concurrent.futures import as_completed, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Literal, Optional

from . import service

JobStatus = Literal["running", "done", "error", "cancelled"]

_MAX_WORKERS = 6  # matches replay_backtest.py's own MAX_WORKERS default


@dataclass
class Job:
    id: str
    requested_symbols: Optional[list[str]]
    start_date: Optional[str]
    end_date: Optional[str]
    strategy: str = "wisestock"
    status: JobStatus = "running"
    error: Optional[str] = None
    trades: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)
    done_count: int = 0
    total_count: int = 0
    signal_count: int = 0
    cancel_event: threading.Event = field(default_factory=threading.Event)
    futures: dict = field(default_factory=dict)
    trades_lock: threading.Lock = field(default_factory=threading.Lock)


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="backtest-job")


def create_job(
    symbols: Optional[list[str]], start_date: Optional[str], end_date: Optional[str],
    strategy: str = "wisestock",
) -> Job:
    job = Job(
        id=str(uuid.uuid4()), requested_symbols=symbols, start_date=start_date, end_date=end_date,
        strategy=strategy,
    )
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _jobs_lock:
        return _jobs.get(job_id)


def cancel_job(job_id: str) -> Optional[Job]:
    """Same Future.cancel()-based pattern as historical/jobs.py and
    screener/jobs.py -- see either's cancel_job() for the full reasoning."""
    job = get_job(job_id)
    if job is None or job.status != "running":
        return job
    job.cancel_event.set()
    for future, symbol in job.futures.items():
        if future.cancel():
            with job.trades_lock:
                job.done_count += 1
    return job


def _run_job(job: Job) -> None:
    def log_cb(msg: str) -> None:
        job.log_lines.append(msg)

    try:
        symbols = service.resolve_symbols(job.requested_symbols)
    except Exception as e:
        job.status = "error"
        job.error = f"Symbol resolution failed: {type(e).__name__}: {e}"
        return

    job.total_count = len(symbols)
    range_desc = f"{job.start_date or 'earliest'} -> {job.end_date or 'latest'}"
    log_cb(f"Replaying {len(symbols)} symbol(s), {range_desc}")
    if not symbols:
        job.status = "done"
        job.summary = service.summarize([])
        return

    futures = {}
    for symbol in symbols:
        # Each worker opens its own DB connection inside service.replay_symbol
        # -- not a shared one across threads, see service.py's module
        # docstring for why that matters here specifically.
        future = _executor.submit(
            service.replay_symbol, symbol, job.start_date, job.end_date, job.cancel_event.is_set,
            job.strategy,
        )
        futures[future] = symbol
    job.futures = futures

    # Covers the narrow race where cancel_job() ran before job.futures was
    # populated -- see historical/jobs.py's identical comment.
    if job.cancel_event.is_set():
        for future, symbol in futures.items():
            if future.cancel():
                with job.trades_lock:
                    job.done_count += 1

    for future in as_completed(futures):
        symbol = futures[future]
        if future.cancelled():
            continue
        with job.trades_lock:
            job.done_count += 1
        try:
            signals, trades = future.result()
        except Exception as e:
            log_cb(f"[{symbol}] {type(e).__name__}: {e}")
            continue
        if not signals and not trades:
            continue
        with job.trades_lock:
            job.signal_count += len(signals)
            job.trades.extend(trades)
        if trades:
            log_cb(f"[{symbol}] {len(trades)} trade(s), {len(signals)} signal(s)")

    with job.trades_lock:
        job.trades.sort(key=lambda t: (t.get("exit_ts") or 0, t.get("Symbol") or ""))
        cum = 0.0
        for t in job.trades:
            cum += t.get("Profit") or 0.0
            t["Cum. Profit"] = round(cum, 2)
        job.summary = service.summarize(job.trades)

    job.status = "cancelled" if job.cancel_event.is_set() else "done"
    if job.status == "cancelled":
        log_cb(f"Cancelled -- {job.done_count}/{job.total_count} symbols were replayed before stopping")

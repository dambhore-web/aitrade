"""
In-memory job registry for screener scans -- same pattern as
historical/jobs.py (single-user, single local process, jobs don't survive a
backend restart), including the same Future.cancel() based cancellation
(see historical/jobs.py's own comments for why submit-then-cancel is the
correct approach rather than checking a flag mid-submission-loop).
"""
import datetime as dt
import threading
import uuid
from concurrent.futures import as_completed, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Literal, Optional

from . import elder_screen, service

JobStatus = Literal["running", "done", "error", "cancelled"]


@dataclass
class ScreenerRow:
    symbol: str
    last_close: float
    atr: float
    atr_pct: float
    hist_vol_pct: float
    avg_turnover_cr: float
    avg_volume: float
    avg_gap_pct: float
    passes_filters: bool
    score: float = 0.0
    # Level 2 (Elder Triple Screen) -- see jobs.py's _run_elder_screen_phase().
    weekly_trend_down: Optional[bool] = None
    divergence_class: Optional[str] = None
    bull_power_shrink_pct: Optional[float] = None
    volume_confirmed: Optional[bool] = None
    elder_passed: Optional[bool] = None


@dataclass
class Job:
    id: str
    exchange: str
    lookback_days: int
    atr_period: int
    min_price: float
    min_avg_turnover_cr: float
    min_atr_pct: float
    max_atr_pct: float
    eq_series_only: bool
    elder_screen: bool = False
    status: JobStatus = "running"
    error: Optional[str] = None
    rows: list[ScreenerRow] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    done_count: int = 0
    total_count: int = 0
    elder_done_count: int = 0
    elder_total_count: int = 0
    cancel_event: threading.Event = field(default_factory=threading.Event)
    futures: dict = field(default_factory=dict)
    rows_lock: threading.Lock = field(default_factory=threading.Lock)


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
# Kite's historical-data endpoint is rate-limited; 5 concurrent workers
# matches historical/jobs.py's own download job, which already runs
# against the same endpoint without tripping it.
_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="screener-job")


def create_job(
    exchange: str,
    lookback_days: int,
    atr_period: int,
    min_price: float,
    min_avg_turnover_cr: float,
    min_atr_pct: float,
    max_atr_pct: float,
    eq_series_only: bool,
    max_symbols: Optional[int],
    symbols: Optional[list[str]],
    elder_screen: bool = False,
) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        exchange=exchange,
        lookback_days=lookback_days,
        atr_period=atr_period,
        min_price=min_price,
        min_avg_turnover_cr=min_avg_turnover_cr,
        min_atr_pct=min_atr_pct,
        max_atr_pct=max_atr_pct,
        eq_series_only=eq_series_only,
        elder_screen=elder_screen,
    )
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=_run_job, args=(job, max_symbols, symbols), daemon=True).start()
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _jobs_lock:
        return _jobs.get(job_id)


def cancel_job(job_id: str) -> Optional[Job]:
    """Stops every symbol not already being fetched -- see
    historical/jobs.py's cancel_job() for the full reasoning (identical
    pattern: Future.cancel() only succeeds on work a worker hasn't started
    yet, which is exactly what a cancel click can still catch in time)."""
    job = get_job(job_id)
    if job is None or job.status != "running":
        return job
    job.cancel_event.set()
    for future, symbol in job.futures.items():
        if future.cancel():
            with job.rows_lock:
                job.done_count += 1
    return job


def _run_job(job: Job, max_symbols: Optional[int], explicit_symbols: Optional[list[str]]) -> None:
    try:
        kite = service.get_kite()
        instruments_df = service.get_instruments_df(job.exchange)
    except Exception as e:
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
        return

    def log_cb(msg: str) -> None:
        job.log_lines.append(msg)

    try:
        universe = service.build_universe(
            instruments_df, job.eq_series_only, explicit_symbols, max_symbols, log_cb
        )
    except Exception as e:
        job.status = "error"
        job.error = f"Universe build failed: {type(e).__name__}: {e}"
        return

    job.total_count = len(universe)
    log_cb(f"Universe: {len(universe)} symbols")
    if not universe:
        job.status = "done"
        return

    token_by_symbol = {symbol: token for symbol, token in universe}

    futures = {}
    for symbol, token in universe:
        future = _executor.submit(
            service.compute_symbol_metrics, kite, token, job.lookback_days, job.atr_period
        )
        futures[future] = symbol
    job.futures = futures

    # Covers the narrow race where cancel_job() ran before job.futures was
    # populated -- see historical/jobs.py's identical comment.
    if job.cancel_event.is_set():
        for future, symbol in futures.items():
            if future.cancel():
                with job.rows_lock:
                    job.done_count += 1

    for future in as_completed(futures):
        symbol = futures[future]
        if future.cancelled():
            continue
        with job.rows_lock:
            job.done_count += 1
        try:
            metrics = future.result()
        except Exception as e:
            log_cb(f"[{symbol}] {type(e).__name__}: {e}")
            continue
        if metrics is None:
            continue

        passes = (
            metrics["last_close"] >= job.min_price
            and job.min_atr_pct <= metrics["atr_pct"] <= job.max_atr_pct
            and metrics["avg_turnover_cr"] >= job.min_avg_turnover_cr
        )
        row = ScreenerRow(symbol=symbol, passes_filters=passes, **metrics)
        with job.rows_lock:
            job.rows.append(row)
            # Recomputed on every completion, not just once at the end --
            # the UI polls and shows rows live while the scan is still
            # running, and a live "score: 0 while running" (recomputed
            # only after the whole scan finished) reads as a bug rather
            # than "not calculated yet". Cheap at this scale (a handful of
            # hundred rows, at most).
            _score_and_sort(job)

    with job.rows_lock:
        _score_and_sort(job)

    if job.elder_screen and not job.cancel_event.is_set():
        _run_elder_screen_phase(job, kite, token_by_symbol, log_cb)

    job.status = "cancelled" if job.cancel_event.is_set() else "done"
    if job.status == "cancelled":
        log_cb(f"Cancelled -- {job.done_count}/{job.total_count} symbols were scanned before stopping")


def _run_elder_for_symbol(kite, token: int) -> Optional[dict]:
    df = service.fetch_elder_history(kite, token)
    if df is None:
        return None
    return elder_screen.run_elder_screen(df)


def _run_elder_screen_phase(job: Job, kite, token_by_symbol: dict, log_cb) -> None:
    """Level 2 -- only ever run against rows that already passed Level 1.
    Reuses job.futures/job.cancel_event so cancel_job() (which just acts on
    whatever's currently in job.futures) keeps working unchanged across
    both phases without needing its own separate cancel path."""
    candidates = [r for r in job.rows if r.passes_filters]
    job.elder_total_count = len(candidates)
    log_cb(f"Elder Triple Screen (Level 2): {len(candidates)} Level-1 candidates")
    if not candidates:
        return

    futures = {}
    for row in candidates:
        token = token_by_symbol.get(row.symbol)
        if token is None:
            continue
        future = _executor.submit(_run_elder_for_symbol, kite, token)
        futures[future] = row
    job.futures = futures

    if job.cancel_event.is_set():
        for future, row in futures.items():
            if future.cancel():
                with job.rows_lock:
                    job.elder_done_count += 1
        return

    for future in as_completed(futures):
        row = futures[future]
        if future.cancelled():
            continue
        with job.rows_lock:
            job.elder_done_count += 1
        try:
            result = future.result()
        except Exception as e:
            log_cb(f"[{row.symbol}] Elder screen error: {type(e).__name__}: {e}")
            continue
        if result is None:
            continue
        with job.rows_lock:
            row.weekly_trend_down = result.get("weekly_trend_down")
            row.divergence_class = result.get("divergence_class")
            row.bull_power_shrink_pct = result.get("bull_power_shrink_pct")
            row.volume_confirmed = result.get("volume_confirmed")
            row.elder_passed = result.get("elder_passed")
            if row.elder_passed:
                log_cb(
                    f"[{row.symbol}] Elder Class {row.divergence_class} divergence, "
                    f"Bull Power shrank {row.bull_power_shrink_pct}%, volume confirmed"
                )
            _score_and_sort(job)

    with job.rows_lock:
        _score_and_sort(job)


def _score_and_sort(job: Job) -> None:
    """Composite score = average percentile rank of ATR% and turnover among
    symbols that pass the hard filters -- the two things this tool was
    explicitly asked to screen for (volatility, then volume/liquidity),
    combined rather than picked one at a time so a stock strong on both
    ranks above one that's merely extreme on a single axis."""
    passing = [r for r in job.rows if r.passes_filters]
    if passing:
        atr_sorted = sorted(r.atr_pct for r in passing)
        turnover_sorted = sorted(r.avg_turnover_cr for r in passing)

        def pct_rank(sorted_vals: list[float], x: float) -> float:
            if len(sorted_vals) <= 1:
                return 100.0
            import bisect

            i = bisect.bisect_left(sorted_vals, x)
            return i / (len(sorted_vals) - 1) * 100

        for r in passing:
            r.score = round((pct_rank(atr_sorted, r.atr_pct) + pct_rank(turnover_sorted, r.avg_turnover_cr)) / 2, 1)

    def sort_key(r: ScreenerRow) -> tuple:
        # Elder Class A ranks above Class B, both above everything else --
        # matches step 6's "rank by divergence class (A > B), and by how
        # sharply Bull Power is shrinking" -- layered on top of, not
        # replacing, Level 1's pass/score ordering (elder_class_rank and
        # bull_power_shrink_pct are both 0 for every row when elder_screen
        # wasn't requested, so this collapses back to the original
        # Level-1-only sort exactly).
        elder_class_rank = 2 if r.divergence_class == "A" else 1 if r.divergence_class == "B" else 0
        elder_rank = elder_class_rank if r.elder_passed else 0
        shrink = r.bull_power_shrink_pct if (r.elder_passed and r.bull_power_shrink_pct is not None) else 0.0
        return (r.passes_filters, elder_rank, shrink, r.score)

    job.rows.sort(key=sort_key, reverse=True)

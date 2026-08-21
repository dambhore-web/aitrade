"""
Volatility/liquidity screener -- built 2026-08-18 for "we need stocks with
volatility for trading, second filter is volume". Reuses the platform's
existing shared Kite session (historical.service.get_kite(), same session
Announcement Trading's "Generate Token" establishes) rather than any new
auth flow -- one authenticated session for the whole platform, matching
every other module here.

Metric definitions (see docs/requirements.md strategy notes this was built
from):
  - ATR% = 14-day Average True Range / last close, as a percentage.
    Normalizes volatility across price levels so a ₹50 stock and a ₹2000
    stock are comparable -- raw ATR alone isn't.
  - Historical volatility% = annualized stdev of daily returns.
  - Avg turnover (₹ cr) = mean(close * volume) over the lookback window,
    in crores. The liquidity filter -- turnover, not raw share count, so a
    low-price/high-share-count stock doesn't look falsely liquid.
  - Avg gap% = mean(|open - prev close| / prev close) -- a secondary
    volatility signal, how much this stock tends to move overnight.

Scoped out of v1 (see docs/requirements.md open-questions log): intraday
relative-volume (RVOL, today's volume vs N-day average at the same time of
day) needs minute-level history for the whole universe, which is expensive
enough at scale (hundreds of symbols x months of minute bars) to warrant a
separate decision on whether/how to do it cheaply, rather than baking it
into v1 silently. Turnover is used as the liquidity signal instead.
"""
import datetime as dt
import threading
import time
from io import StringIO
from typing import Optional

import pandas as pd
import requests

from app.core.legacy_path import add_legacy_root_to_path
from app.modules.historical import service as historical_service

add_legacy_root_to_path()
from zerodha_scrape_core import build_from_to  # noqa: E402  (must follow add_legacy_root_to_path)

MASTER_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
# nsearchives.nseindia.com is a static archive subdomain -- unlike the main
# site/API (which needs a warmed browser session past Akamai's bot-check,
# see announcement_trading/market_data.py), this one answers a plain
# requests.get() with just a browser User-Agent. Confirmed live 2026-08-18.
_MASTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/csv,*/*",
}

_master_cache: Optional[tuple[dt.date, pd.DataFrame]] = None
_master_lock = threading.Lock()


class _RateLimiter:
    """Enforces a minimum spacing between calls, shared across every worker
    thread via one lock -- added 2026-08-18 after a live scan against
    hundreds of symbols came back "NetworkException: Too many requests" on
    most of them. jobs.py's 5 concurrent workers were hitting
    kite.historical_data() with zero pacing between them; Kite's historical
    endpoint is rate-limited (documented around 3 req/sec) regardless of
    how many worker threads are asking. This serializes actual API calls to
    a safe rate no matter how many workers are running -- worker
    concurrency still helps (each one blocks here only as long as its own
    turn takes), it just can't flood the endpoint anymore."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.next_allowed = 0.0

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            wait = self.next_allowed - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self.next_allowed = now + self.min_interval


# ~2.7 req/sec -- a bit under Kite's documented 3 req/sec historical-data
# limit, leaving margin since other modules (equity_auto_trading's scanner
# loop, exit management) may be calling other Kite endpoints concurrently
# on the same account.
_historical_rate_limiter = _RateLimiter(min_interval=0.37)


def _fetch_historical_with_retry(kite, token: int, from_str: str, to_str: str, max_attempts: int = 4) -> list:
    """Retries specifically on rate-limit throttling (exponential backoff);
    any other error (bad token, no data, auth) is raised immediately rather
    than burning retries on something backoff can't fix."""
    delay = 1.0
    last_exc: Optional[Exception] = None
    for _ in range(max_attempts):
        _historical_rate_limiter.acquire()
        try:
            return kite.historical_data(int(token), from_str, to_str, "day")
        except Exception as e:
            if "too many requests" not in str(e).lower():
                raise
            last_exc = e
            time.sleep(delay)
            delay *= 2
    raise last_exc  # type: ignore[misc]


def get_kite():
    return historical_service.get_kite()


def auth_status() -> dict:
    return historical_service.auth_status()


def get_instruments_df(exchange: str) -> pd.DataFrame:
    return historical_service.get_instruments_df(exchange)


def get_nse_securities_master() -> pd.DataFrame:
    """NSE's own master list of currently-listed equities (SYMBOL, SERIES,
    NAME OF COMPANY, ...). Cached per-day, same pattern as
    historical.service.get_instruments_df(). Raises on failure -- callers
    that want a soft fallback (eq_series_only) catch it themselves rather
    than this function silently returning something misleading."""
    global _master_cache
    today = dt.date.today()
    with _master_lock:
        cached = _master_cache
        if cached and cached[0] == today:
            return cached[1]
    resp = requests.get(MASTER_CSV_URL, headers=_MASTER_HEADERS, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    df["SERIES"] = df["SERIES"].astype(str).str.strip()
    with _master_lock:
        _master_cache = (today, df)
    return df


def build_universe(
    instruments_df: pd.DataFrame,
    eq_series_only: bool,
    explicit_symbols: Optional[list[str]],
    max_symbols: Optional[int],
    log_cb=None,
) -> list[tuple[str, int]]:
    """Returns [(tradingsymbol, instrument_token), ...]."""
    if explicit_symbols:
        wanted = {s.strip().upper() for s in explicit_symbols if s.strip()}
        df = instruments_df[instruments_df["tradingsymbol"].isin(wanted)]
    else:
        df = instruments_df[instruments_df["instrument_type"] == "EQ"]
        if eq_series_only:
            try:
                master = get_nse_securities_master()
                eq_symbols = set(master.loc[master["SERIES"] == "EQ", "SYMBOL"])
                df = df[df["tradingsymbol"].isin(eq_symbols)]
            except Exception as e:
                if log_cb:
                    log_cb(f"NSE securities master fetch failed ({e}) -- continuing without SERIES filter")

    df = df.drop_duplicates(subset="tradingsymbol")
    pairs = list(zip(df["tradingsymbol"].tolist(), df["instrument_token"].tolist()))
    if max_symbols:
        pairs = pairs[:max_symbols]
    return pairs


def compute_symbol_metrics(
    kite,
    token: int,
    lookback_days: int,
    atr_period: int,
) -> Optional[dict]:
    """None means "not enough data to score" (new listing, illiquid/no
    trades, etc.) -- callers skip these rather than showing a misleading
    zero."""
    end = dt.date.today()
    # Calendar-day buffer over the trading-day lookback so weekends/holidays
    # don't leave the window short once filtered down to actual candles.
    start = end - dt.timedelta(days=int((lookback_days + atr_period) * 1.6) + 10)
    from_str, to_str = build_from_to("day", start, end)

    candles = _fetch_historical_with_retry(kite, token, from_str, to_str)
    if not candles:
        return None

    df = pd.DataFrame(candles).sort_values("date").reset_index(drop=True)
    if len(df) < atr_period + 2:
        return None
    df = df.tail(lookback_days + atr_period).reset_index(drop=True)

    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(atr_period).mean().iloc[-1]
    last_close = float(df["close"].iloc[-1])
    if not last_close or pd.isna(atr):
        return None
    atr_pct = float(atr / last_close * 100)

    returns = df["close"].pct_change().dropna()
    hist_vol_pct = float(returns.std() * (252**0.5) * 100) if len(returns) > 1 else 0.0

    turnover = df["close"] * df["volume"]
    avg_turnover_cr = float(turnover.mean() / 1e7)
    avg_volume = float(df["volume"].mean())

    gap_pct = ((df["open"] - prev_close).abs() / prev_close * 100).dropna()
    avg_gap_pct = float(gap_pct.mean()) if not gap_pct.empty else 0.0

    return {
        "last_close": round(last_close, 2),
        "atr": round(float(atr), 2),
        "atr_pct": round(atr_pct, 2),
        "hist_vol_pct": round(hist_vol_pct, 2),
        "avg_turnover_cr": round(avg_turnover_cr, 2),
        "avg_volume": round(avg_volume, 0),
        "avg_gap_pct": round(avg_gap_pct, 2),
    }


# Level 2 (elder_screen.py) needs enough daily history for a stable weekly
# 13-period EMA -- a 13-week EMA only really converges after several times
# its own period, so this fetches roughly a year of calendar days rather
# than reusing Level 1's much shorter lookback_days.
ELDER_HISTORY_CALENDAR_DAYS = 380


def fetch_elder_history(kite, token: int) -> Optional[pd.DataFrame]:
    """Daily OHLCV for elder_screen.py's weekly-tide + divergence pipeline.
    None if there's not enough history (new listing) or the fetch failed."""
    end = dt.date.today()
    start = end - dt.timedelta(days=ELDER_HISTORY_CALENDAR_DAYS)
    from_str, to_str = build_from_to("day", start, end)

    candles = _fetch_historical_with_retry(kite, token, from_str, to_str)
    if not candles:
        return None
    df = pd.DataFrame(candles).sort_values("date").reset_index(drop=True)
    if len(df) < 150:  # not enough for a trustworthy weekly 13-EMA
        return None
    return df

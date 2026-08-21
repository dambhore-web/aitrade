"""
Level 2 of the volatility screener -- Alexander Elder's Triple Screen system
(Trading for a Living / Come Into My Trading Room): a weekly trend ("tide")
filter, daily Elder-ray/Force Index oscillators, bearish price/oscillator
divergence classification (A/B), and a volume-confirmation veto. Runs only
against symbols that already passed Level 1 (service.py's ATR%/turnover
screen) -- the weekly resample + divergence scan is the expensive part of
this, so it's bounded to a few dozen candidates, not the whole universe.

Design choices locked in with the user 2026-08-18:
  - Weekly tide indicator: 13-week EMA slope only (not weekly MACD-Hist) --
    simpler, less noisy, Elder's own primary tide indicator.
  - Divergence classes: A and B only. Class C (marginal new high, oscillator
    roughly flat) is excluded -- Elder's own weakest/lowest-conviction case,
    kept out to keep the shortlist to genuinely actionable setups.

Class definitions (Elder's own, since the source book doesn't give exact
numeric thresholds -- these are reasonable, defensible bands, not invented
from scratch):
  - Class A (strongest): price makes a CLEAR higher high (>0.5% above the
    prior peak) while the oscillator makes a lower high. Bulls pushed price
    further with less force than before -- the strongest "running out of
    steam" signal.
  - Class B: price makes an essentially EQUAL high (within 0.5%, a "double
    top") while the oscillator makes a lower high. Weaker than A since price
    didn't even make a new high, but still a real divergence.
  - Anything else (price makes a clearly LOWER high, or the oscillator
    didn't actually decline) -- no divergence flagged, matches Class C or
    "no signal" and is excluded either way per the locked-in choice above.
"""
import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

# How many peak-to-peak local-maxima each side of a candidate peak must be
# the highest within, to count as a real peak rather than daily noise.
PEAK_ORDER = 3
# How many bars of "approach" volume to average for the volume-confirmation
# check (the days leading into each peak).
VOLUME_APPROACH_BARS = 5
# Tolerance for "equal high" (Class B, double top) vs "clear higher high"
# (Class A).
EQUAL_HIGH_TOLERANCE_PCT = 0.5


def resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLCV -> weekly (Mon-Fri NSE week, closing Friday). Kite's
    historical API has no native "week" interval (only minute/day/N-minute),
    so this is done here rather than requested from the API directly."""
    d = df.set_index(pd.DatetimeIndex(df["date"]))
    weekly = d.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return weekly.dropna(subset=["close"]).reset_index()


def weekly_tide_down(daily_df: pd.DataFrame, ema_period: int = 13) -> Optional[bool]:
    """True if the 13-week EMA's slope is down (this week's value below last
    week's) -- Elder's primary weekly trend ("tide") indicator. None if
    there isn't enough weekly history yet to trust the EMA."""
    weekly = resample_weekly(daily_df)
    if len(weekly) < ema_period + 2:
        return None
    ema = weekly["close"].ewm(span=ema_period, adjust=False).mean()
    return bool(ema.iloc[-1] < ema.iloc[-2])


def elder_ray(df: pd.DataFrame, ema_period: int = 13) -> tuple[pd.Series, pd.Series]:
    """Bull Power = daily High - 13-day EMA; Bear Power = daily Low - 13-day
    EMA. Positive Bull Power means bulls pushed price above the average;
    its trend (not its level) is what the divergence scan cares about."""
    ema = df["close"].ewm(span=ema_period, adjust=False).mean()
    bull_power = df["high"] - ema
    bear_power = df["low"] - ema
    return bull_power, bear_power


def force_index_2ema(df: pd.DataFrame) -> pd.Series:
    """Elder's Force Index, smoothed with a 2-day EMA -- (close - prev
    close) * volume, then EMA'd. Computed as a supplementary confirmation
    signal alongside Bull Power (the primary divergence oscillator here,
    per the locked-in design), not used as its own separate gate."""
    raw = df["close"].diff() * df["volume"]
    return raw.ewm(span=2, adjust=False).mean()


def _find_local_maxima(values: np.ndarray, order: int = PEAK_ORDER) -> list[int]:
    """Indices where values[i] is the max within [i-order, i+order] -- a
    plain windowed-max peak finder (no scipy dependency needed for
    something this simple)."""
    n = len(values)
    peaks = []
    for i in range(order, n - order):
        window = values[i - order : i + order + 1]
        if np.isnan(values[i]):
            continue
        if values[i] >= np.nanmax(window):
            peaks.append(i)
    # Collapse adjacent/plateau peaks (a flat top can satisfy the window
    # check at several consecutive indices) down to one, keeping the last.
    collapsed = []
    for i in peaks:
        if collapsed and i - collapsed[-1] <= order:
            collapsed[-1] = i
        else:
            collapsed.append(i)
    return collapsed


def _approach_volume(df: pd.DataFrame, peak_idx: int, n: int = VOLUME_APPROACH_BARS) -> float:
    start = max(0, peak_idx - n + 1)
    return float(df["volume"].iloc[start : peak_idx + 1].mean())


def detect_bearish_divergence(df: pd.DataFrame, lookback_bars: int = 60) -> Optional[dict]:
    """Compares the two most recent significant price peaks (within the
    trailing `lookback_bars` daily candles) against Bull Power's value at
    those same two dates. Returns None if there aren't two peaks to compare,
    or if what's found doesn't clear the Class A/B bar (see module
    docstring). Class C and non-divergent cases both return None --
    identical treatment, per the locked-in "A/B only" choice."""
    if len(df) < lookback_bars:
        lookback_bars = len(df)
    window = df.tail(lookback_bars).reset_index(drop=True)

    bull_power, _bear_power = elder_ray(df)
    bull_power_window = bull_power.tail(lookback_bars).reset_index(drop=True)

    price_peaks = _find_local_maxima(window["high"].values)
    if len(price_peaks) < 2:
        return None

    prior_idx, recent_idx = price_peaks[-2], price_peaks[-1]
    price_prior = float(window["high"].iloc[prior_idx])
    price_recent = float(window["high"].iloc[recent_idx])
    bull_prior = float(bull_power_window.iloc[prior_idx])
    bull_recent = float(bull_power_window.iloc[recent_idx])

    if not (bull_recent < bull_prior):
        return None  # oscillator didn't actually weaken -- no divergence

    price_pct_change = (price_recent - price_prior) / price_prior * 100

    if price_pct_change > EQUAL_HIGH_TOLERANCE_PCT:
        divergence_class = "A"
    elif abs(price_pct_change) <= EQUAL_HIGH_TOLERANCE_PCT:
        divergence_class = "B"
    else:
        return None  # price made a clearly LOWER high -- Class C/no signal, excluded

    bull_power_shrink_pct = (bull_prior - bull_recent) / abs(bull_prior) * 100 if bull_prior else 0.0

    vol_prior = _approach_volume(window, prior_idx)
    vol_recent = _approach_volume(window, recent_idx)
    volume_confirmed = vol_recent < vol_prior

    return {
        "divergence_class": divergence_class,
        "bull_power_shrink_pct": round(bull_power_shrink_pct, 1),
        "volume_confirmed": volume_confirmed,
        "prior_peak_date": str(window["date"].iloc[prior_idx]),
        "recent_peak_date": str(window["date"].iloc[recent_idx]),
    }


def run_elder_screen(daily_df: pd.DataFrame) -> Optional[dict]:
    """Full Level-2 pipeline for one symbol's daily OHLCV history (needs
    enough bars for a stable weekly 13-EMA -- see WEEKLY_LOOKBACK_DAYS in
    service.py). Returns None immediately if the weekly tide isn't down
    (step 2's hard discard) or there's not enough history yet; otherwise
    returns the full result dict including divergence + volume findings
    (which may themselves be "no divergence found", also a valid, non-error
    outcome for a candidate that passed the tide filter but shows no
    weakness signal yet)."""
    tide_down = weekly_tide_down(daily_df)
    if tide_down is not True:
        return {"weekly_trend_down": tide_down, "elder_passed": False}

    divergence = detect_bearish_divergence(daily_df)
    if not divergence:
        return {"weekly_trend_down": True, "elder_passed": False}

    elder_passed = divergence["volume_confirmed"]  # rising volume on the
    # up-move vetoes the signal even with valid divergence -- step 5's
    # explicit "skip the stock even if divergence is present"

    return {
        "weekly_trend_down": True,
        "divergence_class": divergence["divergence_class"],
        "bull_power_shrink_pct": divergence["bull_power_shrink_pct"],
        "volume_confirmed": divergence["volume_confirmed"],
        "elder_passed": elder_passed,
    }

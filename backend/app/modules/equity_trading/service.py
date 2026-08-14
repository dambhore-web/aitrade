"""
Module C service layer -- READ-ONLY window into new_trade_tool/marketdata.db.

collector.py is the sole writer of that database (see docs/requirements.md
NFRs) and scanner.py already runs its own live strategy + order execution
loop against it independently -- this module must never write to it or call
into strategies.py/execution.py/live_exit.py. Connections are opened with
SQLite's own `mode=ro` URI flag as a hard backstop against that, not just a
convention (verified: it raises OperationalError on any write attempt).
"""
import datetime as dt
import sqlite3
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.legacy_path import add_new_trade_tool_root_to_path


def db_path() -> Path:
    return get_settings().new_trade_tool_root / "marketdata.db"


def watchlist_path() -> Path:
    return get_settings().new_trade_tool_root / "watchlist.csv"


def get_conn() -> sqlite3.Connection:
    uri_path = str(db_path()).replace("\\", "/")
    conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def load_watchlist() -> list[str]:
    add_new_trade_tool_root_to_path()
    from common import load_watchlist as _load_watchlist  # noqa: E402

    # common.load_watchlist() doesn't dedupe (unlike zerodha_scrape_core.py's
    # dedupe_upper for the same class of CSV) -- watchlist.csv genuinely has
    # at least one duplicate row (WCIL) today. Dedupe here, order preserved,
    # rather than editing the user's watchlist file.
    seen: set[str] = set()
    out: list[str] = []
    for s in _load_watchlist(str(watchlist_path())):
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def get_candles(symbol: str, exchange: str, interval: int, limit: int = 300) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT ts, dt_ist, open, high, low, close, volume
               FROM candles WHERE symbol = ? AND exchange = ? AND interval = ?
               ORDER BY ts DESC LIMIT ?""",
            (symbol, exchange, interval, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_diagnostics(symbol: str, exchange: str, interval: int, limit: int = 300) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT ts, dt_ist, open, high, low, close, volume,
                      VWAP, EMA20, EMA50, VolMA50, trend, ema_cross_today,
                      fresh_breakdown, recent_vwap_cross, vwap_gt_ema20,
                      vol_basic, vol_confirm, short_filter, Short_condition, Short
               FROM diagnostics WHERE symbol = ? AND exchange = ? AND interval = ?
               ORDER BY ts DESC LIMIT ?""",
            (symbol, exchange, interval, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_signals(symbol: Optional[str], exchange: str, limit: int = 100) -> list[dict]:
    conn = get_conn()
    try:
        if symbol:
            rows = conn.execute(
                """SELECT id, symbol, exchange, interval, ts, dt_ist, signal, close, meta,
                          gen_ts, gen_dt_ist
                   FROM signals WHERE symbol = ? AND exchange = ?
                   ORDER BY id DESC LIMIT ?""",
                (symbol, exchange, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, symbol, exchange, interval, ts, dt_ist, signal, close, meta,
                          gen_ts, gen_dt_ist
                   FROM signals WHERE exchange = ?
                   ORDER BY id DESC LIMIT ?""",
                (exchange, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_latest_prices(exchange: str) -> dict[str, dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT symbol, ltp, ts FROM latest_price WHERE exchange = ?", (exchange,)
        ).fetchall()
        return {r["symbol"]: {"ltp": r["ltp"], "ts": r["ts"]} for r in rows}
    finally:
        conn.close()


def get_status(exchange: str, interval: int) -> dict:
    conn = get_conn()
    try:
        max_candle_ts = conn.execute(
            "SELECT MAX(ts) FROM candles WHERE exchange = ? AND interval = ?", (exchange, interval)
        ).fetchone()[0]
        max_price_ts = conn.execute(
            "SELECT MAX(ts) FROM latest_price WHERE exchange = ?", (exchange,)
        ).fetchone()[0]
        watchlist_count = len(load_watchlist())
        return {
            "exchange": exchange,
            "interval": interval,
            "watchlist_count": watchlist_count,
            "latest_candle_utc": (
                dt.datetime.fromtimestamp(max_candle_ts, tz=dt.timezone.utc).isoformat()
                if max_candle_ts
                else None
            ),
            "latest_price_utc": (
                dt.datetime.fromtimestamp(max_price_ts, tz=dt.timezone.utc).isoformat()
                if max_price_ts
                else None
            ),
        }
    finally:
        conn.close()

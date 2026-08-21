"""
AmiBroker-style tradebook backtester -- wraps new_trade_tool/replay_backtest.py
(the current, most complete version -- NOT replay_backtest_with_date.py, an
older single-day predecessor superseded by this one's "ALL days" mode with a
date-range option added instead; NOT backtest.py, which is marked SUPERSEDED
in its own header and uses a different, not-live-accurate fixed ATR
stop/target model). Runs the exact same strategy
(strategies.wisestock_short_setup_afl) and exit rule
(exit_rules.evaluate_exit -- the SAME function LiveExitManager uses live) this
platform's Equity Auto Trading actually runs, so results here are what would
have actually happened, not a separate approximation with its own drift risk.

Never wired into aitrade at all until 2026-08-18 -- found after the user
pointed out "in the old equity trading we had backtesting very similar to
amibroker seems you missed it". Confirmed: a real, sophisticated,
AmiBroker-format tradebook engine (Trade/# bars/MAE/MFE/Scale In-Out/Cum.
Profit -- AmiBroker's own report column set) that had simply never been
exposed through any aitrade endpoint.

DB access: each call here opens and closes its OWN sqlite3 connection to
marketdata.db, rather than reusing equity_auto_trading.scanner_loop's shared
one. Deliberately NOT the same pattern as that module's writer coordination
fix (2026-08-18): that fix serializes WRITES from collector/scanner around
one Python-level lock on one shared connection -- correct for that case, but
this module's jobs run several symbols concurrently across worker threads
purely for READS, and reusing one connection object across genuinely
simultaneous reads from multiple threads produced real
"DatabaseError: bad parameter or other API misuse" errors, confirmed live
2026-08-18 (Python's sqlite3, even with check_same_thread=False, doesn't
guarantee one connection is safe for truly concurrent use from several
threads at once -- only that it CAN be built on one thread and used from
another, not several simultaneously). marketdata.db already runs in WAL
mode (new_trade_tool/db.py), which is exactly what supports many independent
connections reading concurrently without any of this -- so the correct fix
is separate connections per worker, not a shared one with more locking.
"""
from typing import Optional

from app.core.legacy_path import add_new_trade_tool_root_to_path

add_new_trade_tool_root_to_path()
import replay_backtest  # noqa: E402  (must follow add_new_trade_tool_root_to_path)


def _open_conn():
    from config import DB_PATH
    from db import db_connect

    return db_connect(DB_PATH)


def resolve_symbols(symbols: Optional[list[str]]) -> list[str]:
    """None/empty -> every symbol with candles for EXCHANGE+INTERVAL in the
    DB (replay_backtest.py's own "ALL" mode); otherwise just the ones given,
    filtered to those actually present. One-off, single-threaded call (at
    job start, before any worker threads spin up), so its own short-lived
    connection is opened and closed here without any concurrency concern."""
    conn = _open_conn()
    try:
        return replay_backtest.resolve_symbols(conn, symbols if symbols else "ALL")
    finally:
        conn.close()


def replay_symbol(
    symbol: str, start_date: Optional[str], end_date: Optional[str], cancel_check=None,
    strategy: str = "wisestock",
) -> tuple[list[dict], list[dict]]:
    """Opens and closes its own connection -- see module docstring for why
    this must NOT share a connection with other concurrently-running
    workers. Returns (signals, trades) -- see
    replay_backtest.replay_symbol_all_days's own docstring for the exact
    shape of each, and for what cancel_check does (a day-boundary
    cancellation checkpoint). strategy: "wisestock" or "breakout" -- see
    that function's own docstring."""
    conn = _open_conn()
    try:
        return replay_backtest.replay_symbol_all_days(
            conn, symbol, start_date, end_date, cancel_check=cancel_check, strategy=strategy
        )
    finally:
        conn.close()


def summarize(trades: list[dict]) -> dict:
    """Port of backtest.py's summarize() -- the one function in that
    SUPERSEDED file that isn't tied to its own not-live-accurate exit model;
    it just aggregates a trade list, which is format-agnostic. Headline
    stats over a completed trade list, applied here to trades produced by
    the live-accurate replay above instead."""
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0, "max_win": 0.0, "max_loss": 0.0}
    profits = [t["Profit"] for t in trades]
    wins = [p for p in profits if p > 0]
    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "total_pnl": round(sum(profits), 2),
        "avg_pnl": round(sum(profits) / len(profits), 2),
        "max_win": round(max(profits), 2),
        "max_loss": round(min(profits), 2),
    }

"""
Watchlist read/write -- new_trade_tool/watchlist.csv, the plain CSV that
scanner.py's own main() and this platform's scanner_loop.py both load via
common.load_watchlist() once per loop start (config.WATCHLIST_CSV).

Deliberately NOT added to equity_trading's router (Module C) -- that
module's whole service.py is documented read-only ("must never write to
[marketdata.db] ... connections opened with mode=ro as a hard backstop"),
and mixing a write path into a module built around that invariant would
blur a boundary that's enforced elsewhere at the DB-connection level. This
lives in equity_auto_trading instead, alongside the other settings that
actually govern the live scanner (amount, strategy).

Editing here writes the CSV directly; the change takes effect the next
time the equity auto-trading loop is (re)started -- watchlist membership is
read once per loop start, not re-polled per cycle like amount/strategy are,
so this is NOT live-reloaded the way those two are. Making it so would need
scanner_loop.py to track newly-added/removed symbols mid-run without
disrupting open positions -- a bigger structural change, out of scope here.
"""
from pathlib import Path
from typing import List

from app.core.legacy_path import add_new_trade_tool_root_to_path


def _csv_path() -> Path:
    add_new_trade_tool_root_to_path()
    from config import WATCHLIST_CSV

    return Path(WATCHLIST_CSV)


def list_symbols() -> List[str]:
    add_new_trade_tool_root_to_path()
    from common import load_watchlist as _load_watchlist

    # common.load_watchlist() doesn't dedupe -- watchlist.csv has at least
    # one known duplicate (WCIL). Dedupe here, order preserved, same as
    # equity_trading/service.py's own read path does.
    seen: set = set()
    out: List[str] = []
    for s in _load_watchlist(str(_csv_path())):
        s = s.strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


class WatchlistLockedError(Exception):
    """watchlist.csv is currently held open by another program (Excel, a
    text editor, etc.) -- Windows enforces an exclusive lock in that case,
    so the write fails outright rather than queuing. Caught in router.py
    and turned into a clear 423 instead of a raw 500."""


def _write_symbols(symbols: List[str]) -> None:
    path = _csv_path()
    try:
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write("symbol\n")
            for s in symbols:
                f.write(f"{s}\n")
    except PermissionError as e:
        raise WatchlistLockedError(
            f"{path.name} is open in another program (Excel, a text editor, etc.) -- close it and try again."
        ) from e


def add_symbols(new_symbols: List[str]) -> List[str]:
    """Adds any of new_symbols not already present (case-insensitive,
    normalized to upper). Returns the full updated list."""
    current = list_symbols()
    seen = set(current)
    for raw in new_symbols:
        s = raw.strip().upper()
        if s and s not in seen:
            seen.add(s)
            current.append(s)
    _write_symbols(current)
    return current


def remove_symbol(symbol: str) -> List[str]:
    """Removes one symbol (case-insensitive). No-op, not an error, if it
    wasn't present. Returns the full updated list."""
    target = symbol.strip().upper()
    current = [s for s in list_symbols() if s != target]
    _write_symbols(current)
    return current

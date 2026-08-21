"""
Lazy-loaded static reference data used by the automatic trading pipeline --
ported from Kite_API_31.py's module-level CSV/list loads (script_folder +
"\\inputs\\..."), which run unconditionally at import in the original. Here
each is loaded once, on first use, off the event loop.
"""
import threading
from pathlib import Path
from typing import Optional

import pandas as pd

from app.core.config import get_settings

_lock = threading.Lock()
_zerodha_list_equity: Optional[pd.DataFrame] = None
_symbol_list: Optional[pd.DataFrame] = None
_bonus_buyback_list: Optional[pd.DataFrame] = None
_bonus_buyback_list_mtime: Optional[float] = None
_black_listed_df: Optional[pd.DataFrame] = None
_categories_to_exclude: Optional[list[str]] = None
_sto_loss_data: Optional[pd.DataFrame] = None


def _inputs_dir() -> Path:
    return get_settings().legacy_root / "inputs"


def zerodha_list_equity() -> pd.DataFrame:
    """symbol/token/exchange/margin/tick_size master list."""
    global _zerodha_list_equity
    with _lock:
        if _zerodha_list_equity is None:
            _zerodha_list_equity = pd.read_csv(_inputs_dir() / "zerodha_equity_list.csv")
        return _zerodha_list_equity


def symbol_list() -> pd.DataFrame:
    """BSE SCRIP_CD -> symbol mapping, used by merge_bse_nse_ticker."""
    global _symbol_list
    with _lock:
        if _symbol_list is None:
            _symbol_list = pd.read_csv(_inputs_dir() / "symbol_list.csv")
        return _symbol_list


def bonus_buyback_list() -> pd.DataFrame:
    """Doubles as the symbol+category "already processed" store in the
    original (check_symbol_and_pred_bert_existence) -- not actually
    bonus/buyback specific data by the time it's used this way.

    Unlike this module's other lazy-loaded tables, this one is re-read
    whenever the file's mtime changes rather than cached forever: the new
    Bonus/Buyback Download page (app/modules/bonus_buyback/) writes to this
    exact file from the same long-lived backend process the auto-loop runs
    in, specifically so gates.already_processed() picks up newly-logged
    rows without a restart. A plain load-once cache (still fine for the
    genuinely-static tables above) would have silently made every append
    invisible to the gate until the process restarted -- caught while
    verifying the exclusion logic actually works end-to-end, not just in
    isolation."""
    global _bonus_buyback_list, _bonus_buyback_list_mtime
    path = _inputs_dir() / "bonus_buyback.csv"
    with _lock:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        if _bonus_buyback_list is None or mtime != _bonus_buyback_list_mtime:
            _bonus_buyback_list = pd.read_csv(path)
            _bonus_buyback_list_mtime = mtime
        return _bonus_buyback_list


def black_listed_df() -> pd.DataFrame:
    global _black_listed_df
    with _lock:
        if _black_listed_df is None:
            df = pd.read_csv(_inputs_dir() / "black_listed_keyword.csv")
            df["category"] = df["category"].str.lower()
            _black_listed_df = df
        return _black_listed_df


def sto_loss_data() -> pd.DataFrame:
    """Per-category stop-loss % table, used by get_stop_loss()."""
    global _sto_loss_data
    with _lock:
        if _sto_loss_data is None:
            _sto_loss_data = pd.read_csv(_inputs_dir() / "stop_loss.csv")
        return _sto_loss_data


def categories_to_exclude() -> list[str]:
    global _categories_to_exclude
    with _lock:
        if _categories_to_exclude is None:
            path = _inputs_dir() / "categories_to_exclude.txt"
            with open(path, "r") as f:
                _categories_to_exclude = [line.strip() for line in f]
        return _categories_to_exclude

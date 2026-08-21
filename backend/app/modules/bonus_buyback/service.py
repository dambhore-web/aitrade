"""
Bonus/Buyback Download service layer -- thin wrapper over
Trading_bot/nse_bse_tool_extraction.py's run_extraction()/append_bonus_buyback(),
the same functions news_extractor uses (see that module for why this is a
separate, from-scratch file rather than an import of/edit to
nse_bse_extraction_tool.py or Kite_API_31.py).

Modeled on Trading_bot/bonus_buyback_extract.py's run_main_with_bonus_append()
-- confirmed the *actual* function Kite_API_31.py's "Get Bonus/Buy Back Data"
button calls (`from bonus_buyback_extract import run_main_with_bonus_append`),
not the near-identical copy embedded in nse_bse_extraction_tool.py (which
targets a different, unread file -- see nse_bse_tool_extraction.py's
append_bonus_buyback() docstring). Session/reuse is identical to
news_extractor, so imported from there rather than duplicated.
"""
import pandas as pd
from kiteconnect import KiteConnect

from app.modules.news_extractor.service import ensure_nse_session_warm, get_kite  # noqa: F401
from app.modules.news_extractor.service import extractor


def read_existing_bonus_buyback() -> pd.DataFrame:
    import os

    if not os.path.exists(extractor.DEFAULT_BONUS_BUYBACK_PATH):
        return pd.DataFrame(columns=["symbol", "an_dt", "pred_bert"])
    return pd.read_csv(extractor.DEFAULT_BONUS_BUYBACK_PATH)

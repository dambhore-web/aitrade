"""
The gating chain from Kite_API_31.py's job() -- each function here mirrors
one `continue` check in the original loop, in the same order they're
applied. See pipeline.py for the assembled sequence.
"""
import datetime as dt
import logging

from . import reference_data

logger = logging.getLogger("announcement_trading.gates")


def already_processed(symbol: str, category: str) -> bool:
    """Port of check_symbol_and_pred_bert_existence -- despite living in
    inputs/bonus_buyback.csv, this list is used generically here as an
    already-seen (symbol, category) store, not bonus/buyback-specific
    data."""
    df = reference_data.bonus_buyback_list()
    symbol_l, category_l = symbol.lower(), category.lower()
    matches = df[(df["symbol"].str.lower() == symbol_l) & (df["pred_bert"].str.lower() == category_l)]
    return not matches.empty


def blacklisted_keyword_hit(category: str, text: str) -> bool:
    """Port of check_category_and_text_for_keywords."""
    df = reference_data.black_listed_df()
    category_l, text_l = category.lower(), text.lower()
    matches = df[df["category"] == category_l]
    if matches.empty:
        return False
    return any(keyword in text_l for keyword in matches["keyword"].tolist())


def category_allowed(category: str) -> bool:
    """Port of check_category_exists -- True if NOT excluded (matches the
    original's inverted naming: "exists" here means "passes the filter")."""
    excluded = [c.lower() for c in reference_data.categories_to_exclude()]
    return category.lower() not in excluded


def is_fresh(published_at: dt.datetime, hours_back: float) -> bool:
    """Port of the timeofpublish > tt freshness check."""
    tt = dt.datetime.today() - dt.timedelta(hours=hours_back, seconds=120)
    return published_at > tt

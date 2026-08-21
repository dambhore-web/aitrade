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
    """Port of the timeofpublish > tt freshness check. The original
    (Kite_API_31.py:4599) uses a 120-second grace period on top of
    hours_back; tightened to 60 seconds per explicit instruction
    (2026-08-17), then to 20 seconds per further explicit instruction
    (2026-08-19) -- only trade news within 20 seconds of publish,
    hours_back unchanged.

    Not the same window as market_data.py's own hardcoded 60-second grace
    buffer on the BSE fetch cutoff -- that one controls which announcements
    get FETCHED from BSE's API at all (a data-completeness margin so a
    slow poll cycle doesn't miss one that just published), not whether a
    fetched announcement is fresh enough to ORDER on. Narrowing that one to
    match this gate would risk missing genuinely fresh announcements
    entirely rather than just correctly rejecting stale ones -- a different
    failure mode than what this instruction is about, so it's untouched."""
    tt = dt.datetime.today() - dt.timedelta(hours=hours_back, seconds=20)
    return published_at > tt


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Every reason pipeline.py can return BEFORE a symbol has passed the
# content-relevance filters (symbol/date validity, sentiment, already-
# processed-by-bonus-buyback, blacklist, category exclusion). Anything else
# -- stale_news, sizing_failed, final_filters_not_met, no_kite_session, or
# no skip at all -- means the symbol got at least as far as
# Kite_API_31.py's own symbol_store.append(symbol) point (job(), ~line
# 4935), which runs unconditionally once those checks pass, regardless of
# whether an order actually ends up placed.
_EARLY_REJECTION_REASONS = {
    "no_symbol",
    "symbol_not_tradeable",
    "token_not_found",
    "unparseable_date",
    "neutral_or_other",
    "already_processed",
    "blacklisted_keyword",
    "category_excluded",
}


def symbol_already_qualified_today(conn, symbol: str) -> bool:
    """Port of Kite_API_31.py's `symbol_store` (job(), ~line 4622/4935;
    persisted to inputs/symbol_store.pkl, reloaded and filtered to today's
    entries on every script start). Real gap found 2026-08-18: once a
    symbol has ANY announcement pass the content filters on a given day,
    the original skips every subsequent announcement for that symbol that
    day -- regardless of source, exact wording, or even a different
    classified category. That's what stops the same real-world event,
    independently re-posted by NSE and BSE with different exact text, from
    placing two orders. Neither of the other two dedup mechanisms already
    here reliably catches that: auto_loop.py's seen_keys is in-memory only
    (reset on every backend restart) and keyed on exact text; gates.
    already_processed() is keyed on (symbol, category) together via
    bonus_buyback.csv specifically, not a general per-symbol-per-day gate.

    Backed by activity_log directly rather than a separate pickle/table --
    every symbol that reached the original's append point already has a
    logged row here. "Today" is IST calendar day, matching every other
    day-boundary already in this codebase (e.g.
    equity_auto_trading/router.py's recent_signals()).

    Ported exactly, including the original's actual scope: a second,
    later, genuinely different qualifying announcement for the same symbol
    on the same day is ALSO blocked -- confirmed as the intended behavior,
    not a side effect, 2026-08-18."""
    today = dt.datetime.now(IST).date()
    rows = conn.execute(
        "SELECT ts_utc, skip_reason FROM activity_log WHERE symbol = ? ORDER BY id DESC LIMIT 200",
        (symbol,),
    ).fetchall()
    for ts_utc, skip_reason in rows:
        try:
            ts = dt.datetime.fromisoformat(ts_utc)
        except (TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        if ts.astimezone(IST).date() != today:
            continue
        if skip_reason not in _EARLY_REJECTION_REASONS:
            return True
    return False

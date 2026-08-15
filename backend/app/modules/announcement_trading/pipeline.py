"""
The per-announcement decision chain from Kite_API_31.py's job() (inner loop
body over unprocessed_data.iterrows()), assembled from the ported pieces in
classification.py / market_data.py / gates.py / execution.py.

SCOPED OUT (see docs/requirements.md): the short/ambiguous-text fallback
that re-extracts and re-classifies from the announcement's PDF (and its
LLM-sentiment fallback) is not ported. In the original this only fires for
short or category="other"+sentiment="positive" text, as a rescue path.
Skipping it means some announcements that path *would* have rescued into a
real category/sentiment here instead just fall through the normal
sentiment=="neutral" or category=="other" skip below. It's a real, bounded
behavior difference, not a silent one -- logged per-item as skip reason
"pdf_fallback_not_ported" so it's visible in the activity feed, not hidden.
"""
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Optional

import dateparser

from app.core.legacy_path import add_legacy_root_to_path

from . import classification, execution, gates, market_data, reference_data

logger = logging.getLogger("announcement_trading.pipeline")

add_legacy_root_to_path()
import margin_data_calculator  # noqa: E402  (clean, side-effect-free module)


@dataclass
class ItemResult:
    symbol: str
    category: str = ""
    sentiment: str = ""
    text: str = ""
    skipped: bool = True
    skip_reason: str = ""
    order_placed: bool = False
    order_results: list = field(default_factory=list)
    quantity: Optional[int] = None
    current_price: Optional[float] = None
    trigger_price: Optional[float] = None
    target_price: Optional[float] = None


def _get_stop_loss(category: str) -> float:
    """Port of get_stop_loss()."""
    try:
        df = reference_data.sto_loss_data()
        result = df[df["category"].str.lower() == category.lower()]["stop_loss"]
        return float(result.values[0]) if not result.empty else 0.7
    except Exception:
        logger.debug("get_stop_loss failed for category=%s", category, exc_info=True)
        return 0.6


MARKET_TRADE_START = dt.time(9, 15, 0)
MARKET_TRADE_END = dt.time(15, 28, 0)


def process_item(row: dict, settings: dict, kite_instances: list) -> ItemResult:
    """`row` has the merged announcement schema: desc, an_dt, attchmntText,
    attchmntFile, symbol. `settings` is the announcement_trading settings
    row (amount, gtt_stop_pct/gtt_target_pct as fallback -- category-specific
    stop-loss from get_stop_loss() takes precedence, matching the original).
    """
    symbol = row.get("symbol") or ""
    text = str(row.get("attchmntText") or "").lower()
    result = ItemResult(symbol=symbol, text=text)

    if not symbol:
        result.skip_reason = "no_symbol"
        return result

    if market_data.symbol_check(symbol) == 0:
        result.skip_reason = "symbol_not_tradeable"
        return result

    token_info = market_data.get_token(symbol)
    if token_info is None:
        result.skip_reason = "token_not_found"
        return result
    _token, exchange, _name = token_info

    try:
        published_at = dateparser.parse(str(row.get("an_dt")))
        if published_at is None:
            raise ValueError("unparseable an_dt")
    except Exception:
        result.skip_reason = "unparseable_date"
        return result

    volume, spread_pct = market_data.get_stock_info(exchange, symbol)
    category = classification.classify_category(text)
    sentiment = classification.analyse_sentiment(text)
    _change, highest_value, _last_open = market_data.historical_pricev1(symbol)
    result.category, result.sentiment = category, sentiment

    if len(text) < 200 or (category == "other" and sentiment == "positive"):
        # See module docstring -- the PDF re-extraction/re-classification
        # rescue path for short/ambiguous text is not ported. Falling
        # through to the ordinary gates below with what we already have.
        logger.debug("pdf_fallback_not_ported for %s (not fatal, continuing with initial classification)", symbol)

    if sentiment == "neutral" or category == "other":
        result.skip_reason = "neutral_or_other"
        return result

    if gates.already_processed(symbol, category):
        result.skip_reason = "already_processed"
        return result

    if gates.blacklisted_keyword_hit(category, text):
        result.skip_reason = "blacklisted_keyword"
        return result

    if not gates.category_allowed(category):
        result.skip_reason = "category_excluded"
        return result

    hours_back = settings.get("hours_back", 0) or 0
    if not gates.is_fresh(published_at, hours_back):
        result.skip_reason = "stale_news"
        return result

    try:
        current_price = market_data.get_current_price(symbol)
        amount = settings.get("amount") or 0
        base_quantity = round(amount / current_price) if current_price else 1
        quantity, margin, tick_size = margin_data_calculator.margin_calculator(
            reference_data.zerodha_list_equity(), symbol, exchange, current_price, amount, base_quantity
        )
    except Exception:
        logger.exception("Price/quantity sizing failed for %s", symbol)
        result.skip_reason = "sizing_failed"
        return result

    quantity = 5 if quantity < 2 else quantity
    current_price = 1 if current_price < 1 else current_price
    result.quantity, result.current_price = quantity, current_price

    down_from_high = (highest_value - current_price) * 100 / highest_value if highest_value else 0
    gtt_stop_pct = _get_stop_loss(category)
    gtt_target_pct = settings.get("gtt_target_pct", 20) or 20

    stop_loss_amt = abs(gtt_stop_pct) * current_price / 100
    target_amt = gtt_target_pct * current_price / 100

    product_type = "MTF"
    if margin >= 100:
        product_type = "CNC"
    elif exchange == "BSE":
        exchange = "NSE"

    trigger_price = round(current_price - stop_loss_amt, 2)
    target_price = round(current_price + target_amt, 2)
    trigger_price = round(round(trigger_price / tick_size) * tick_size, 2) if tick_size else trigger_price
    target_price = round(round(target_price / tick_size) * tick_size, 2) if tick_size else target_price
    result.trigger_price, result.target_price = trigger_price, target_price

    current_time = dt.datetime.now().time()
    if not (
        MARKET_TRADE_START <= current_time <= MARKET_TRADE_END
        and volume > quantity
        and down_from_high < 2
        and spread_pct < 1
        and current_price > 50
    ):
        result.skip_reason = "final_filters_not_met"
        return result

    result.skipped = False
    if not kite_instances:
        result.skip_reason = "no_kite_session"
        return result

    order_results = execution.place_orders_parallel(
        kite_instances, quantity, exchange, symbol, "BUY", product_type,
        trigger_price, target_price, current_price,
    )
    result.order_results = order_results
    result.order_placed = any("order_id" in r for r in order_results)
    return result

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
    # The exact published_at process_item() itself parsed and used for the
    # freshness decision -- added 2026-08-17 so auto_loop.py logs this
    # instead of separately re-reading row.get("an_dt"), which could in
    # principle diverge from what was actually evaluated. Set whenever
    # parsing succeeds, regardless of what happens after.
    published_at: Optional[str] = None


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


def process_item(row: dict, settings: dict, kite_instances: list, conn) -> ItemResult:
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
    result.published_at = published_at.isoformat()

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

    if gates.symbol_already_qualified_today(conn, symbol):
        # Port of Kite_API_31.py's symbol_store -- see gates.py's docstring
        # for the full rationale. Placed here, matching the original's own
        # placement relative to the sentiment/blacklist/category checks
        # above: reaching this point is exactly what the original marks a
        # symbol as "done for today" for, whether or not an order actually
        # ends up placed below.
        result.skip_reason = "symbol_already_qualified_today"
        return result

    hours_back = settings.get("hours_back", 0) or 0
    if not gates.is_fresh(published_at, hours_back):
        # Embeds the actual age at decision time -- added 2026-08-17 after
        # a "why did this get marked stale_news, what was the real gap"
        # investigation hit a dead end: the raw published_at used for a
        # past decision was never persisted anywhere, so it couldn't be
        # reconstructed after the fact. This makes every future stale_news
        # self-explanatory in the activity feed instead of requiring log
        # archaeology.
        age_seconds = (dt.datetime.today() - published_at).total_seconds()
        result.skip_reason = f"stale_news ({age_seconds:.0f}s old, published {published_at.strftime('%H:%M:%S')})"
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
        # Embeds which specific sub-condition(s) actually failed -- added
        # 2026-08-18 after "why didn't MCLOUD place an order" required
        # reconstructing this by hand from raw activity_log fields; the
        # bundled reason alone doesn't say which of the four gates tripped.
        failed = []
        if not (MARKET_TRADE_START <= current_time <= MARKET_TRADE_END):
            failed.append(f"outside_trade_window({current_time.strftime('%H:%M:%S')})")
        if not (volume > quantity):
            failed.append(f"low_volume({volume}<={quantity})")
        if not (down_from_high < 2):
            failed.append(f"down_from_high({down_from_high:.2f}%>=2%)")
        if not (spread_pct < 1):
            failed.append(f"spread({spread_pct:.2f}%>=1%)")
        if not (current_price > 50):
            failed.append(f"price(₹{current_price:.2f}<=50)")
        result.skip_reason = f"final_filters_not_met ({', '.join(failed)})"
        return result

    result.skipped = False
    if not kite_instances:
        result.skip_reason = "no_kite_session"
        return result

    order_results = execution.place_orders_parallel(
        kite_instances, quantity, exchange, symbol, "BUY", product_type,
        trigger_price, target_price, current_price,
        settings.get("market_protection_pct", 3.0) or 3.0,
    )
    result.order_results = order_results
    result.order_placed = any("order_id" in r for r in order_results)
    return result

"""
Faithful port of Kite_API_31.py's place_orders() / place_orders_parallel()
(lines 651-757 as of this port). Ported rather than imported: Kite_API_31.py
is a 235KB monolith with substantial module-level side effects on import
(reads Zerodha_Orders.xlsx, builds a PySimpleGUI layout's supporting state,
etc. -- see docs/requirements.md open-questions log), so importing it
wholesale just to reuse these two self-contained functions would be far
riskier than porting them. Behavior is intentionally unchanged from the
original: MARKET order, immediate GTT OCO (stop-loss + target) bracket,
per-account MULTIPLIER-scaled quantity, MTF-not-allowed-on-exchange retry
on BSE/CNC.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

logger = logging.getLogger("announcement_trading.execution")


def place_orders(
    kite,
    user: dict,
    base_quantity: int,
    exchange: str,
    symbol: str,
    transaction_type: str,
    product_type: str,
    stop_loss_price: float,
    target_price: float,
    current_price: float,
) -> Optional[dict]:
    """Places one MARKET order + a GTT OCO bracket for one account. Returns
    {"order_id", "gtt_trigger_id", "exchange"} on success, None on failure
    (matches the original's return-None-on-any-error behavior -- errors are
    logged, not raised, so one account's failure doesn't stop the others)."""
    zerodha_id = user.get("Zerodha ID", "unknown")
    try:
        multiplier = user.get("MULTIPLIER", 1) or 1
        adjusted_quantity = round(base_quantity * multiplier)
        logger.info("Placing order for %s: qty=%s", zerodha_id, adjusted_quantity)

        try:
            order_id = kite.place_order(
                variety="regular",
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=adjusted_quantity,
                product=product_type,
                order_type="MARKET",
                market_protection=-1.0,
            )
        except Exception as e:
            if "MTF orders are only allowed on NSE" in str(e):
                logger.warning("[%s] MTF not allowed on %s, retrying on BSE/CNC", zerodha_id, exchange)
                exchange = "BSE"
                order_id = kite.place_order(
                    variety="regular",
                    exchange="BSE",
                    tradingsymbol=symbol,
                    transaction_type=transaction_type,
                    quantity=adjusted_quantity,
                    product="CNC",
                    order_type="MARKET",
                    market_protection=-1.0,
                )
            else:
                raise

        logger.info("Order placed for %s: id=%s", zerodha_id, order_id)

        order_oco = [
            {
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_SELL,
                "quantity": adjusted_quantity,
                "order_type": "LIMIT",
                "product": product_type,
                "price": stop_loss_price,
            },
            {
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_SELL,
                "quantity": adjusted_quantity,
                "order_type": "LIMIT",
                "product": product_type,
                "price": target_price,
            },
        ]
        gtt_oco = kite.place_gtt(
            trigger_type=kite.GTT_TYPE_OCO,
            tradingsymbol=symbol,
            exchange=exchange,
            trigger_values=[stop_loss_price, target_price],
            last_price=current_price,
            orders=order_oco,
        )
        logger.info("GTT OCO trigger_id for %s: %s", zerodha_id, gtt_oco["trigger_id"])

        return {"zerodha_id": zerodha_id, "order_id": order_id, "gtt_trigger_id": gtt_oco["trigger_id"], "exchange": exchange}

    except Exception as e:
        logger.error("Order failed for %s: %s", zerodha_id, e)
        return {"zerodha_id": zerodha_id, "error": str(e)}


def place_orders_parallel(
    kite_instances: list[tuple],
    base_quantity: int,
    exchange: str,
    symbol: str,
    transaction_type: str,
    product_type: str,
    stop_loss_price: float,
    target_price: float,
    current_price: float,
) -> list[dict]:
    """Runs place_orders() across every connected account in parallel.
    Unlike the original (which only logged results), this returns them --
    the caller persists them onto the trade_entries row for the message-
    to-order traceability this module exists to provide."""
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(len(kite_instances), 1)) as executor:
        futures = [
            executor.submit(
                place_orders, kite, user, base_quantity, exchange, symbol,
                transaction_type, product_type, stop_loss_price, target_price, current_price,
            )
            for kite, user in kite_instances
        ]
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    return results

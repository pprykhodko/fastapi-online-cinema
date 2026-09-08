from decimal import Decimal
from typing import Optional

from src.database.validators.money import validate_money


def validate_order_status(status: str) -> str:
    if not isinstance(status, str) or status not in (
        "pending", "paid", "canceled",
    ):
        raise ValueError("Order status must be pending, paid, or canceled.")
    return status


def validate_total_amount(amount: Optional[Decimal]) -> Optional[Decimal]:
    if amount is None:
        return None
    return validate_money(amount, "Order total amount")


def validate_price_at_order(price: Decimal) -> Decimal:
    return validate_money(price, "Price at order")

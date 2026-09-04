from decimal import Decimal
from typing import Optional


def validate_total_amount(amount: Optional[Decimal]) -> Optional[Decimal]:
    if amount is not None and amount < 0:
        raise ValueError("Order total amount must not be negative.")
    return amount


def validate_price_at_order(price: Decimal) -> Decimal:
    if price < 0:
        raise ValueError("Price at order must not be negative.")
    return price

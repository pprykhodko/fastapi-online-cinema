from decimal import Decimal
from typing import Optional

from src.database.validators.money import validate_money


def validate_order_status(status: str) -> str:
    """
    Accept only pending, paid or canceled order states.

    Args:
        status (str): Stored order or payment status.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if not isinstance(status, str) or status not in (
        "pending", "paid", "canceled",
    ):
        raise ValueError("Order status must be pending, paid, or canceled.")
    return status


def validate_total_amount(amount: Optional[Decimal]) -> Optional[Decimal]:
    """
    Allow no order total or an amount within the supported monetary limits.

    Args:
        amount (Optional[Decimal]): Monetary amount in major currency units, not cents.

    Returns:
        Optional[Decimal]: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if amount is None:
        return None
    return validate_money(amount, "Order total amount")


def validate_price_at_order(price: Decimal) -> Decimal:
    """
    Validate the historical order-item price without rounding it.

    Args:
        price (Decimal): Historical item price as a Decimal.

    Returns:
        Decimal: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    return validate_money(price, "Price at order")

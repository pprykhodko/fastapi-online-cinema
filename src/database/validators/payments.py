from decimal import Decimal

from src.database.validators.money import validate_money


def validate_payment_status(status: str) -> str:
    """
    Accept only successful, canceled or refunded payment states.

    Args:
        status (str): Stored order or payment status.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if not isinstance(status, str) or status not in (
        "successful", "canceled", "refunded",
    ):
        raise ValueError(
            "Payment status must be successful, canceled, or refunded."
        )
    return status


def validate_payment_amount(amount: Decimal) -> Decimal:
    """
    Validate a payment amount within the supported monetary limits.

    Args:
        amount (Decimal): Monetary amount in major currency units, not cents.

    Returns:
        Decimal: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    return validate_money(amount, "Payment amount")


def validate_price_at_payment(price: Decimal) -> Decimal:
    """
    Validate the historical payment-item price without rounding it.

    Args:
        price (Decimal): Historical item price as a Decimal.

    Returns:
        Decimal: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    return validate_money(price, "Price at payment")

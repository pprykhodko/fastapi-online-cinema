from decimal import Decimal

from src.database.validators.money import validate_money


def validate_payment_status(status: str) -> str:
    if not isinstance(status, str) or status not in (
        "successful", "canceled", "refunded",
    ):
        raise ValueError(
            "Payment status must be successful, canceled, or refunded."
        )
    return status


def validate_payment_amount(amount: Decimal) -> Decimal:
    return validate_money(amount, "Payment amount")


def validate_price_at_payment(price: Decimal) -> Decimal:
    return validate_money(price, "Price at payment")

from decimal import Decimal
from typing import cast


MAX_MONEY_AMOUNT = Decimal("99999999.99")


def validate_money(value: Decimal, field_name: str) -> Decimal:
    label = field_name.capitalize()
    if not isinstance(value, Decimal):
        raise ValueError(f"{label} must be a Decimal value.")
    if not value.is_finite():
        raise ValueError(f"{label} must be finite.")
    if value < 0:
        raise ValueError(f"{label} must not be negative.")
    if value > MAX_MONEY_AMOUNT:
        raise ValueError(f"{label} must not exceed {MAX_MONEY_AMOUNT}.")

    parts = value.as_tuple()
    exponent = cast(int, parts.exponent)
    if exponent < -2 and any(parts.digits[exponent + 2:]):
        raise ValueError(f"{label} must not contain fractional cents.")
    return value

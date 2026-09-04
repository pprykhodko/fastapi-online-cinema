from decimal import Decimal


def validate_payment_amount(amount: Decimal) -> Decimal:
    if amount < 0:
        raise ValueError("Payment amount must not be negative.")
    return amount


def validate_price_at_payment(price: Decimal) -> Decimal:
    if price < 0:
        raise ValueError("Price at payment must not be negative.")
    return price

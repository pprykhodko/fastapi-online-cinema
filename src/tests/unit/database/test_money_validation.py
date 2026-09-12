from decimal import Decimal, localcontext
from typing import Any

import pytest

from src.database import (
    Base,
    MovieModel,
    OrderItemModel,
    OrderModel,
    PaymentItemModel,
    PaymentModel,
)


MONEY_FIELDS = [
    (MovieModel, "price"),
    (OrderModel, "total_amount"),
    (OrderItemModel, "price_at_order"),
    (PaymentModel, "amount"),
    (PaymentItemModel, "price_at_payment"),
]


@pytest.mark.parametrize(("model", "field"), MONEY_FIELDS)
@pytest.mark.parametrize("amount", [
    Decimal("NaN"), Decimal("sNaN"),
    Decimal("Infinity"), Decimal("-Infinity"),
    Decimal("-0.01"), Decimal("100000000.00"),
    Decimal("0.001"), Decimal("9.999"), Decimal("1E-1000"),
    9.99, "9.99", True,
])
def test_money_fields_reject_invalid_values_on_create_and_update(
    model: type[Base], field: str, amount: Any,
) -> None:
    with pytest.raises(ValueError):
        model(**{field: amount})
    instance = model(**{field: Decimal("9.99")})
    with pytest.raises(ValueError):
        setattr(instance, field, amount)
    assert getattr(instance, field) == Decimal("9.99")


@pytest.mark.parametrize(("model", "field"), MONEY_FIELDS)
@pytest.mark.parametrize("amount", [
    Decimal("0"), Decimal("0.01"), Decimal("99999999.99"),
    Decimal("1E+2"), Decimal("9.9900"), Decimal("0E-1000"),
])
def test_money_fields_preserve_valid_values_without_rounding(
    model: type[Base], field: str, amount: Decimal,
) -> None:
    instance = model(**{field: amount})
    assert getattr(instance, field) == amount


@pytest.mark.parametrize(("model", "field"), MONEY_FIELDS)
def test_money_fields_do_not_depend_on_decimal_context(
    model: type[Base], field: str,
) -> None:
    with localcontext() as context:
        context.prec = 2
        with pytest.raises(ValueError):
            model(**{field: Decimal("1.001")})
        instance = model(**{field: Decimal("99999999.99")})
        assert getattr(instance, field) == Decimal("99999999.99")


@pytest.mark.parametrize(("model", "field"), MONEY_FIELDS)
def test_money_nullability_matches_assignment(
    model: type[Base], field: str,
) -> None:
    if model in (MovieModel, OrderModel):
        assert getattr(model(**{field: None}), field) is None
    else:
        with pytest.raises(ValueError):
            model(**{field: None})

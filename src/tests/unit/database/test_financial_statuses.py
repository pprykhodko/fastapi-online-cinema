from typing import Any

import pytest

from src.database import (
    OrderModel, OrderStatusEnum, PaymentModel, PaymentStatusEnum,
)


@pytest.mark.parametrize(("model", "enum_type"), [
    (OrderModel, OrderStatusEnum),
    (PaymentModel, PaymentStatusEnum),
])
def test_financial_statuses_accept_enum_members_and_exact_values(
    model: type[OrderModel] | type[PaymentModel],
    enum_type: type[OrderStatusEnum] | type[PaymentStatusEnum],
) -> None:
    for member in enum_type:
        for value in (member, member.value):
            instance = model(status=value)
            assert instance.status is member


@pytest.mark.parametrize("model", [OrderModel, PaymentModel])
@pytest.mark.parametrize("status", [
    "invalid-status", "PAID", "pending ", "", None, 1, True,
])
def test_financial_statuses_reject_invalid_assignments(
    model: type[OrderModel] | type[PaymentModel], status: Any,
) -> None:
    with pytest.raises(ValueError):
        model(status=status)
    instance = model()
    with pytest.raises(ValueError):
        instance.status = status

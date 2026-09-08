from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import (
    DefaultClause,
    Enum,
    Numeric,
    String,
    Table,
    create_engine,
    inspect,
)

from src.database import Base
from src.database.models.accounts import UserModel
from src.database.models.orders import OrderItemModel, OrderModel
from src.database.models.payments import (
    PaymentItemModel,
    PaymentModel,
    PaymentStatusEnum,
)
from src.database.validators.payments import (
    validate_payment_amount,
    validate_price_at_payment,
)


def test_payment_status_enum_contains_required_values() -> None:
    assert {status.value for status in PaymentStatusEnum} == {
        "successful",
        "canceled",
        "refunded",
    }


def test_payment_columns_match_assignment_schema() -> None:
    table = cast(Table, PaymentModel.__table__)
    status_type = cast(Enum, table.c.status.type)
    status_default = cast(DefaultClause, table.c.status.server_default)
    amount_type = cast(Numeric, table.c.amount.type)
    external_id_type = cast(String, table.c.external_payment_id.type)

    assert table.c.user_id.nullable is False
    assert table.c.order_id.nullable is False
    assert table.c.created_at.nullable is False
    assert table.c.created_at.server_default is not None
    assert table.c.status.nullable is False
    assert status_type.length == 50
    assert status_type.native_enum is False
    assert status_type.create_constraint is True
    assert status_type.validate_strings is True
    assert status_type.enums == ["successful", "canceled", "refunded"]
    assert str(status_default.arg) == "successful"
    assert table.c.amount.nullable is False
    assert amount_type.precision == 10
    assert amount_type.scale == 2
    assert table.c.external_payment_id.nullable is True
    assert external_id_type.length == 255


def test_payment_item_columns_match_assignment_schema() -> None:
    table = cast(Table, PaymentItemModel.__table__)
    price_type = cast(Numeric, table.c.price_at_payment.type)

    assert table.c.payment_id.nullable is False
    assert table.c.order_item_id.nullable is False
    assert table.c.price_at_payment.nullable is False
    assert price_type.precision == 10
    assert price_type.scale == 2


def test_payment_relationships_match_assignment() -> None:
    assert UserModel.payments.property.uselist is True
    assert UserModel.payments.property.back_populates == "user"
    assert PaymentModel.user.property.back_populates == "payments"
    assert OrderModel.payments.property.uselist is True
    assert OrderModel.payments.property.back_populates == "order"
    assert PaymentModel.order.property.back_populates == "payments"
    assert PaymentModel.items.property.uselist is True
    assert PaymentModel.items.property.back_populates == "payment"
    assert PaymentItemModel.payment.property.back_populates == "items"
    assert OrderItemModel.payment_items.property.uselist is True
    assert OrderItemModel.payment_items.property.back_populates == (
        "order_item"
    )
    assert PaymentItemModel.order_item.property.back_populates == (
        "payment_items"
    )


def test_payment_foreign_keys_define_delete_behavior() -> None:
    payment_table = cast(Table, PaymentModel.__table__)
    item_table = cast(Table, PaymentItemModel.__table__)

    user_fk = next(iter(payment_table.c.user_id.foreign_keys))
    order_fk = next(iter(payment_table.c.order_id.foreign_keys))
    payment_fk = next(iter(item_table.c.payment_id.foreign_keys))
    order_item_fk = next(iter(item_table.c.order_item_id.foreign_keys))

    assert user_fk.ondelete == "RESTRICT"
    assert order_fk.ondelete == "RESTRICT"
    assert payment_fk.ondelete == "CASCADE"
    assert order_item_fk.ondelete == "RESTRICT"


@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("9.99")])
def test_validate_payment_amount_accepts_valid_values(amount: Decimal) -> None:
    assert validate_payment_amount(amount) == amount


def test_validate_payment_amount_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        validate_payment_amount(Decimal("-0.01"))


@pytest.mark.parametrize("price", [Decimal("0.00"), Decimal("9.99")])
def test_validate_price_at_payment_accepts_valid_values(
    price: Decimal,
) -> None:
    assert validate_price_at_payment(price) == price


def test_validate_price_at_payment_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        validate_price_at_payment(Decimal("-0.01"))


def test_payment_models_apply_amount_validation() -> None:
    with pytest.raises(ValueError):
        PaymentModel(
            user_id=1,
            order_id=1,
            amount=Decimal("-0.01"),
        )

    with pytest.raises(ValueError):
        PaymentItemModel(
            payment_id=1,
            order_item_id=1,
            price_at_payment=Decimal("-0.01"),
        )


def test_payment_model_representations() -> None:
    payment = PaymentModel(
        id=1,
        user_id=2,
        order_id=3,
        status=PaymentStatusEnum.SUCCESSFUL,
        amount=Decimal("9.99"),
    )
    item = PaymentItemModel(
        id=4,
        payment_id=1,
        order_item_id=5,
        price_at_payment=Decimal("9.99"),
    )

    assert repr(payment) == (
        "<PaymentModel(id=1, user_id=2, order_id=3, "
        "status=successful)>"
    )
    assert repr(item) == (
        "<PaymentItemModel(id=4, payment_id=1, order_item_id=5)>"
    )


def test_metadata_creates_payment_tables_in_sqlite() -> None:
    engine = create_engine("sqlite://")

    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    assert {"payments", "payment_items"}.issubset(table_names)

from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import (
    DefaultClause,
    Enum,
    Numeric,
    Table,
    create_engine,
    inspect,
)

from src.database import Base
from src.database.models.accounts import UserModel
from src.database.models.movies import MovieModel
from src.database.models.orders import (
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
)
from src.database.validators.orders import (
    validate_price_at_order,
    validate_total_amount,
)


def test_order_status_enum_contains_required_values() -> None:
    assert {status.value for status in OrderStatusEnum} == {
        "pending",
        "paid",
        "canceled",
    }


def test_order_columns_match_assignment_schema() -> None:
    table = cast(Table, OrderModel.__table__)
    status_type = cast(Enum, table.c.status.type)
    status_default = cast(DefaultClause, table.c.status.server_default)
    total_amount_type = cast(Numeric, table.c.total_amount.type)

    assert table.c.user_id.nullable is False
    assert table.c.created_at.nullable is False
    assert table.c.created_at.server_default is not None
    assert table.c.status.nullable is False
    assert status_type.length == 50
    assert status_type.native_enum is False
    assert status_type.enums == ["pending", "paid", "canceled"]
    assert str(status_default.arg) == "pending"
    assert table.c.total_amount.nullable is True
    assert total_amount_type.precision == 10
    assert total_amount_type.scale == 2


def test_order_item_columns_match_assignment_schema() -> None:
    table = cast(Table, OrderItemModel.__table__)
    price_type = cast(Numeric, table.c.price_at_order.type)

    assert table.c.order_id.nullable is False
    assert table.c.movie_id.nullable is False
    assert table.c.price_at_order.nullable is False
    assert price_type.precision == 10
    assert price_type.scale == 2


def test_order_relationships_match_assignment() -> None:
    assert UserModel.orders.property.uselist is True
    assert UserModel.orders.property.back_populates == "user"
    assert OrderModel.user.property.back_populates == "orders"
    assert OrderModel.items.property.uselist is True
    assert OrderModel.items.property.back_populates == "order"
    assert OrderItemModel.order.property.back_populates == "items"
    assert MovieModel.order_items.property.uselist is True
    assert MovieModel.order_items.property.back_populates == "movie"
    assert OrderItemModel.movie.property.back_populates == "order_items"


def test_order_foreign_keys_define_delete_behavior() -> None:
    order_table = cast(Table, OrderModel.__table__)
    item_table = cast(Table, OrderItemModel.__table__)

    user_fk = next(iter(order_table.c.user_id.foreign_keys))
    order_fk = next(iter(item_table.c.order_id.foreign_keys))
    movie_fk = next(iter(item_table.c.movie_id.foreign_keys))

    assert user_fk.ondelete == "RESTRICT"
    assert order_fk.ondelete == "CASCADE"
    assert movie_fk.ondelete == "RESTRICT"


@pytest.mark.parametrize("amount", [None, Decimal("0.00"), Decimal("9.99")])
def test_validate_total_amount_accepts_valid_values(
    amount: Decimal | None,
) -> None:
    assert validate_total_amount(amount) == amount


def test_validate_total_amount_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        validate_total_amount(Decimal("-0.01"))


@pytest.mark.parametrize("price", [Decimal("0.00"), Decimal("9.99")])
def test_validate_price_at_order_accepts_valid_values(price: Decimal) -> None:
    assert validate_price_at_order(price) == price


def test_validate_price_at_order_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        validate_price_at_order(Decimal("-0.01"))


def test_order_models_apply_amount_validation() -> None:
    with pytest.raises(ValueError):
        OrderModel(user_id=1, total_amount=Decimal("-0.01"))

    with pytest.raises(ValueError):
        OrderItemModel(
            order_id=1,
            movie_id=1,
            price_at_order=Decimal("-0.01"),
        )


def test_order_model_representations() -> None:
    order = OrderModel(
        id=1,
        user_id=2,
        status=OrderStatusEnum.PENDING,
        total_amount=Decimal("9.99"),
    )
    item = OrderItemModel(
        id=3,
        order_id=1,
        movie_id=4,
        price_at_order=Decimal("9.99"),
    )

    assert repr(order) == "<OrderModel(id=1, user_id=2, status=pending)>"
    assert repr(item) == "<OrderItemModel(id=3, order_id=1, movie_id=4)>"


def test_metadata_creates_order_tables_in_sqlite() -> None:
    engine = create_engine("sqlite://")

    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    assert {"orders", "order_items"}.issubset(table_names)

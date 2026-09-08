from decimal import Decimal

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from src.database import (
    Base,
    MovieModel,
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
    PaymentItemModel,
    PaymentModel,
    PaymentStatusEnum,
    UserModel,
)


MONEY_COLUMNS = [
    ("movies", "price"),
    ("orders", "total_amount"),
    ("order_items", "price_at_order"),
    ("payments", "amount"),
    ("payment_items", "price_at_payment"),
]


@pytest.fixture
def financial_records(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> dict[str, Base]:
    user = catalog_users[0]
    movie = catalog_movies[0]
    order = OrderModel(user=user, total_amount=Decimal("9.99"))
    order_item = OrderItemModel(
        order=order, movie=movie, price_at_order=Decimal("9.99"),
    )
    payment = PaymentModel(user=user, order=order, amount=Decimal("9.99"))
    payment_item = PaymentItemModel(
        payment=payment, order_item=order_item,
        price_at_payment=Decimal("9.99"),
    )
    db_session.add_all([order, order_item, payment, payment_item])
    db_session.commit()
    return {
        "movies": movie,
        "orders": order,
        "order_items": order_item,
        "payments": payment,
        "payment_items": payment_item,
    }


def test_financial_status_defaults_can_be_read_as_enums(
    db_session: Session, financial_records: dict[str, Base],
) -> None:
    db_session.expire_all()
    assert getattr(financial_records["orders"], "status") is (
        OrderStatusEnum.PENDING
    )
    assert getattr(financial_records["payments"], "status") is (
        PaymentStatusEnum.SUCCESSFUL
    )


@pytest.mark.parametrize(("table", "status"), [
    *[("orders", status) for status in OrderStatusEnum],
    *[("payments", status) for status in PaymentStatusEnum],
])
def test_valid_financial_statuses_survive_database_round_trip(
    db_session: Session, financial_records: dict[str, Base],
    table: str, status: OrderStatusEnum | PaymentStatusEnum,
) -> None:
    record = financial_records[table]
    setattr(record, "status", status.value)
    db_session.commit()
    db_session.expire_all()
    assert getattr(record, "status") is status


@pytest.mark.parametrize("table", ["orders", "payments"])
@pytest.mark.parametrize("status", ["invalid-status", "PAID", "", None])
def test_database_rejects_invalid_status_updates_without_orm_validation(
    db_session: Session, financial_records: dict[str, Base],
    table: str, status: str | None,
) -> None:
    record_id = getattr(financial_records[table], "id")
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text(
                f"UPDATE {table} SET status = :status WHERE id = :id"
            ), {"status": status, "id": record_id})
    db_session.expire_all()
    assert getattr(financial_records[table], "status") in (
        OrderStatusEnum.PENDING, PaymentStatusEnum.SUCCESSFUL,
    )


@pytest.mark.parametrize("table", ["orders", "payments"])
@pytest.mark.parametrize("status", ["invalid-status", None])
def test_database_rejects_invalid_status_inserts_without_orm_validation(
    db_session: Session, financial_records: dict[str, Base],
    table: str, status: str | None,
) -> None:
    record_id = getattr(financial_records[table], "id")
    sql = {
        "orders": (
            "INSERT INTO orders (user_id, status) "
            "SELECT user_id, :status FROM orders WHERE id = :id"
        ),
        "payments": (
            "INSERT INTO payments (user_id, order_id, status, amount) "
            "SELECT user_id, order_id, :status, amount "
            "FROM payments WHERE id = :id"
        ),
    }
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text(sql[table]), {
                "status": status, "id": record_id,
            })


@pytest.mark.parametrize("model", [OrderModel, PaymentModel])
def test_enum_binding_also_rejects_unknown_statuses_in_bulk_updates(
    db_session: Session, financial_records: dict[str, Base],
    model: type[OrderModel] | type[PaymentModel],
) -> None:
    record_id = getattr(financial_records[model.__tablename__], "id")
    with pytest.raises(StatementError) as error:
        with db_session.begin_nested():
            db_session.execute(
                update(model).where(model.id == record_id)
                .values(status="invalid-status")
            )
    assert isinstance(error.value.orig, LookupError)


@pytest.mark.parametrize(("table", "column"), MONEY_COLUMNS)
@pytest.mark.parametrize("amount", [
    -0.01, 100_000_000, float("inf"), float("-inf"),
])
def test_database_rejects_out_of_range_money_without_orm_validation(
    db_session: Session, financial_records: dict[str, Base],
    table: str, column: str, amount: float,
) -> None:
    record = financial_records[table]
    record_id = getattr(record, "id")
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text(
                f"UPDATE {table} SET {column} = :amount WHERE id = :id"
            ), {"amount": amount, "id": record_id})
    db_session.expire_all()
    assert getattr(record, column) == Decimal("9.99")


@pytest.mark.parametrize(("table", "column"), MONEY_COLUMNS)
@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("99999999.99")])
def test_money_boundaries_survive_database_round_trip(
    db_session: Session, financial_records: dict[str, Base],
    table: str, column: str, amount: Decimal,
) -> None:
    record = financial_records[table]
    setattr(record, column, amount)
    db_session.commit()
    db_session.expire_all()
    assert getattr(record, column) == amount


@pytest.mark.parametrize(("table", "column"), MONEY_COLUMNS)
def test_database_preserves_money_nullability_from_assignment(
    db_session: Session, financial_records: dict[str, Base],
    table: str, column: str,
) -> None:
    record = financial_records[table]
    if table == "orders":
        setattr(record, column, None)
        db_session.commit()
        db_session.expire_all()
        assert getattr(record, column) is None
    else:
        record_id = getattr(record, "id")
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.execute(text(
                    f"UPDATE {table} SET {column} = NULL WHERE id = :id"
                ), {"id": record_id})

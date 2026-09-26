from datetime import date

import pytest
from sqlalchemy import select

from src.database.models import OrderModel, PaymentModel
from src.repositories.transaction_filters import transaction_filters
from src.schemas.orders import AdminOrderListQuerySchema, OrderListQuerySchema
from src.schemas.payments import AdminPaymentListQuerySchema, PaymentListQuerySchema


@pytest.mark.parametrize(
    "model,schema,transaction_status",
    [
        (OrderModel, AdminOrderListQuerySchema, "paid"),
        (PaymentModel, AdminPaymentListQuerySchema, "successful")
    ]
)
def test_shared_filters_preserve_owner_and_inclusive_dates(
        model, schema, transaction_status
):
    query = schema(
        user_id=2,
        status=transaction_status,
        date_from=date(2030, 1, 1),
        date_to=date(2030, 1, 2)
    )
    stmt = select(model).where(*transaction_filters(model, query, user_id=1))
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    table = model.__tablename__
    assert f"{table}.user_id = 1" in sql and f"{table}.user_id = 2" in sql
    assert f"{table}.status = '{transaction_status}'" in sql
    assert "2030-01-01 00:00:00" in sql
    assert "2030-01-02 23:59:59.999999" in sql


@pytest.mark.parametrize(
    "model,schema",
    [(OrderModel, OrderListQuerySchema), (PaymentModel, PaymentListQuerySchema)]
)
def test_shared_filters_leave_unfiltered_queries_unchanged(model, schema):
    assert transaction_filters(model, schema()) == []

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.database import (
    MovieModel,
    OrderItemModel,
    OrderModel,
    PaymentItemModel,
    PaymentModel,
    PaymentStatusEnum,
    UserModel,
)
from src.schemas.payments import (
    PaymentListResponseSchema, PaymentResponseSchema,
)


@pytest.mark.parametrize("status", list(PaymentStatusEnum))
def test_payment_response_preserves_amounts_after_catalog_and_order_changes(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel], status: PaymentStatusEnum,
) -> None:
    user_id = catalog_users[0].id
    movie_id = catalog_movies[0].id
    order = OrderModel(user_id=user_id, total_amount=Decimal("9.99"))
    order.items = [OrderItemModel(
        movie_id=movie_id, price_at_order=Decimal("9.99"),
    )]
    db_session.add(order)
    db_session.flush()
    order_id = order.id
    order_item_id = order.items[0].id
    payment = PaymentModel(
        user_id=user_id, order_id=order_id, amount=Decimal("9.99"),
        status=status, external_payment_id=None,
    )
    payment.items = [PaymentItemModel(
        order_item_id=order_item_id, price_at_payment=Decimal("9.99"),
    )]
    db_session.add(payment)
    db_session.commit()
    payment_id = payment.id
    catalog_movies[0].price = Decimal("25.00")
    order.total_amount = Decimal("20.00")
    order.items[0].price_at_order = Decimal("20.00")
    db_session.commit()
    db_session.expunge_all()
    stored_payment = db_session.scalars(
        select(PaymentModel).where(PaymentModel.id == payment_id).options(
            selectinload(PaymentModel.items),
        )
    ).one()
    db_session.expunge_all()

    response = PaymentResponseSchema.model_validate(stored_payment)
    assert response.id == payment_id
    assert response.user_id == user_id
    assert response.order_id == order_id
    assert response.created_at is not None
    assert response.status is status
    assert response.amount == Decimal("9.99")
    assert response.external_payment_id is None
    assert len(response.items) == 1
    assert response.items[0].order_item_id == order_item_id
    assert response.items[0].price_at_payment == Decimal("9.99")
    page = PaymentListResponseSchema(
        items=[response], total=1, page=1, per_page=10,
    )
    data = page.model_dump(mode="json")["items"][0]
    assert data["status"] == status.value
    assert data["amount"] == "9.99"
    assert data["currency"] == "usd"
    assert data["external_payment_id"] is None
    assert set(data) == {
        "id", "user_id", "order_id", "created_at", "status", "amount",
        "external_payment_id", "items", "currency",
    }
    assert "email" not in page.model_dump_json()
    assert "hashed_password" not in page.model_dump_json()

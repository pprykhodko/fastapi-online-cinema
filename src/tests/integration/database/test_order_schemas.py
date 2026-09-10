from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.database import (
    MovieModel, OrderItemModel, OrderModel, OrderStatusEnum, UserModel,
)
from src.schemas.orders import OrderListResponseSchema, OrderResponseSchema


def test_order_response_preserves_price_snapshots_after_movie_price_changes(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    user_id = catalog_users[0].id
    first_movie, second_movie = catalog_movies
    first_price = first_movie.price
    second_price = second_movie.price
    order = OrderModel(user_id=user_id, total_amount=Decimal("19.98"))
    order.items = [
        OrderItemModel(movie=first_movie, price_at_order=first_price),
        OrderItemModel(movie=second_movie, price_at_order=second_price),
    ]
    db_session.add(order)
    db_session.commit()
    order_id = order.id
    first_movie.price = Decimal("25.00")
    db_session.commit()
    db_session.expunge_all()
    stored_order = db_session.scalars(
        select(OrderModel).where(OrderModel.id == order_id).options(
            selectinload(OrderModel.items).selectinload(OrderItemModel.movie),
        )
    ).one()
    db_session.expunge_all()

    response = OrderResponseSchema.model_validate(stored_order)
    assert response.id == order_id
    assert response.user_id == user_id
    assert response.created_at is not None
    assert response.status is OrderStatusEnum.PENDING
    assert response.total_amount == Decimal("19.98")
    assert len(response.items) == 2
    for item in response.items:
        assert item.price_at_order == Decimal("9.99")
        assert item.movie.year == 2020
        assert "price" not in item.movie.model_dump()
    page = OrderListResponseSchema(
        items=[response], total=1, page=1, per_page=10,
    )
    data = page.model_dump(mode="json")
    assert data["items"][0]["total_amount"] == "19.98"
    assert data["items"][0]["status"] == "pending"
    assert set(data["items"][0]) == {
        "id", "user_id", "created_at", "status", "total_amount", "items",
    }
    assert "email" not in page.model_dump_json()
    assert "hashed_password" not in page.model_dump_json()


def test_order_response_preserves_null_total_instead_of_returning_zero(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    order = OrderModel(user_id=catalog_users[0].id, total_amount=None)
    order.items = [OrderItemModel(
        movie=catalog_movies[0], price_at_order=Decimal("9.99"),
    )]
    db_session.add(order)
    db_session.commit()
    order_id = order.id
    db_session.expunge_all()
    stored_order = db_session.scalars(
        select(OrderModel).where(OrderModel.id == order_id).options(
            selectinload(OrderModel.items).selectinload(OrderItemModel.movie),
        )
    ).one()
    db_session.expunge_all()

    response = OrderResponseSchema.model_validate(stored_order)
    assert response.total_amount is None
    assert response.model_dump(mode="json")["total_amount"] is None
    assert response.items[0].price_at_order == Decimal("9.99")

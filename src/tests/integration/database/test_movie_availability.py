from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.database import (
    CartItemModel,
    CartModel,
    MovieFavoriteModel,
    MovieModel,
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
    UserModel
)
from src.schemas.cart import CartResponseSchema
from src.schemas.interactions import MovieFavoriteResponseSchema
from src.schemas.movies import (
    MovieDetailResponseSchema, MovieListItemResponseSchema
)
from src.schemas.orders import OrderResponseSchema


@pytest.mark.parametrize(("price", "deleted", "available"), [
    (None, False, False), (Decimal("0.00"), False, True),
    (Decimal("9.99"), False, True), (Decimal("9.99"), True, False)
])
def test_movie_availability_survives_storage_and_schema_serialization(
        db_session: Session, catalog_movies: tuple[MovieModel, MovieModel],
        price: Decimal | None, deleted: bool, available: bool
) -> None:
    movie = catalog_movies[0]
    movie_id = movie.id
    assert movie.is_deleted is False
    movie.price = price
    movie.is_deleted = deleted
    db_session.commit()
    db_session.expunge_all()
    stored = db_session.scalars(
        select(MovieModel).where(MovieModel.id == movie_id).options(
            selectinload(MovieModel.genres), selectinload(MovieModel.stars),
            selectinload(MovieModel.directors),
            selectinload(MovieModel.certification)
        )
    ).one()
    db_session.expunge_all()
    for schema in (MovieListItemResponseSchema, MovieDetailResponseSchema):
        response = schema.model_validate(stored)
        assert response.price == price
        assert response.is_available_for_purchase is available
        assert "is_deleted" not in response.model_dump()
    if price is None:
        assert response.model_dump(mode="json")["price"] is None


@pytest.mark.parametrize("status", [
    OrderStatusEnum.PENDING, OrderStatusEnum.CANCELED
])
def test_logical_deletion_preserves_cart_and_unpaid_order_history(
        db_session: Session, catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel], status: OrderStatusEnum
) -> None:
    user_id = catalog_users[0].id
    movie = catalog_movies[0]
    movie_id = movie.id
    cart = CartModel(user_id=user_id)
    cart.items = [CartItemModel(movie_id=movie_id)]
    order = OrderModel(
        user_id=user_id, status=status, total_amount=Decimal("9.99")
    )
    order.items = [OrderItemModel(
        movie_id=movie_id, price_at_order=Decimal("9.99")
    )]
    db_session.add_all([cart, order])
    db_session.commit()
    cart_id, order_id = cart.id, order.id
    movie.is_deleted = True
    db_session.commit()
    db_session.expunge_all()

    stored_cart = db_session.scalars(
        select(CartModel).where(CartModel.id == cart_id).options(
            selectinload(CartModel.items).selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres)
        )
    ).one()
    stored_order = db_session.scalars(
        select(OrderModel).where(OrderModel.id == order_id).options(
            selectinload(OrderModel.items).selectinload(OrderItemModel.movie)
        )
    ).one()
    visible_ids = db_session.scalars(
        select(MovieModel.id).where(MovieModel.is_deleted.is_(False))
    ).all()
    db_session.expunge_all()

    cart_response = CartResponseSchema.model_validate(stored_cart)
    assert cart_response.items[0].movie.is_available_for_purchase is False
    assert cart_response.items[0].movie.name == "First movie"
    order_response = OrderResponseSchema.model_validate(stored_order)
    assert order_response.items[0].price_at_order == Decimal("9.99")
    assert order_response.items[0].movie.id == movie_id
    assert order_response.status is status
    assert movie_id not in visible_ids


def test_physical_deletion_cannot_remove_purchased_movie_history(
        db_session: Session, catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel]
) -> None:
    movie_id = catalog_movies[0].id
    order = OrderModel(
        user_id=catalog_users[0].id, status=OrderStatusEnum.PAID,
        total_amount=Decimal("9.99")
    )
    order.items = [OrderItemModel(
        movie_id=movie_id, price_at_order=Decimal("9.99")
    )]
    db_session.add(order)
    db_session.commit()
    with pytest.raises(IntegrityError):
        db_session.delete(catalog_movies[0])
        db_session.commit()
    db_session.rollback()
    assert db_session.get(MovieModel, movie_id) is not None


def test_favorite_and_cart_responses_allow_withdrawn_movie_price(
        db_session: Session, catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel]
) -> None:
    user_id = catalog_users[0].id
    movie = catalog_movies[0]
    movie_id = movie.id
    movie.price = None
    favorite = MovieFavoriteModel(user_id=user_id, movie_id=movie_id)
    cart = CartModel(user_id=user_id)
    cart.items = [CartItemModel(movie_id=movie_id)]
    db_session.add_all([favorite, cart])
    db_session.commit()
    response = MovieFavoriteResponseSchema.model_validate(favorite)
    assert response.movie.price is None
    assert response.movie.is_available_for_purchase is False
    cart_response = CartResponseSchema.model_validate(cart)
    assert cart_response.items[0].movie.price is None
    assert cart_response.items[0].movie.is_available_for_purchase is False

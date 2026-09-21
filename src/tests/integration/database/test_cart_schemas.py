from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.database import (
    CartItemModel, CartModel, GenreModel, MovieModel, UserModel,
)
from src.schemas.cart import (
    CartItemCreateRequestSchema, CartItemResponseSchema, CartResponseSchema,
)


def test_empty_cart_can_be_serialized_without_a_session(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
) -> None:
    user_id = catalog_users[0].id
    cart = CartModel(user_id=user_id)
    db_session.add(cart)
    db_session.commit()
    cart_id = cart.id
    db_session.expunge_all()
    stored_cart = db_session.scalars(
        select(CartModel).where(CartModel.id == cart_id)
        .options(selectinload(CartModel.items))
    ).one()
    db_session.expunge_all()

    response = CartResponseSchema.model_validate(stored_cart)
    assert response.model_dump() == {
        "id": cart_id, "user_id": user_id, "items": [],
    }


def test_cart_schema_loads_multiple_movies_and_their_genres(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    user_id = catalog_users[0].id
    first_movie, second_movie = catalog_movies
    first_movie.genres = [GenreModel(name="Action"), GenreModel(name="Fantasy")]
    cart = CartModel(user_id=user_id)
    cart.items = [
        CartItemModel(movie=first_movie),
        CartItemModel(movie=second_movie),
    ]
    db_session.add(cart)
    db_session.commit()
    cart_id = cart.id
    db_session.expunge_all()
    stored_cart = db_session.scalars(
        select(CartModel).where(CartModel.id == cart_id).options(
            selectinload(CartModel.items)
            .selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres),
        )
    ).one()
    db_session.expunge_all()

    response = CartResponseSchema.model_validate(stored_cart)
    assert response.user_id == user_id
    assert len(response.items) == 2
    items = {item.movie.name: item for item in response.items}
    first_item = items["First movie"]
    assert first_item.added_at is not None
    assert first_item.movie.price == Decimal("9.99")
    assert first_item.movie.year == 2020
    assert {genre.name for genre in first_item.movie.genres} == {
        "Action", "Fantasy",
    }
    assert items["Second movie"].movie.genres == []
    assert set(response.model_dump()) == {"id", "user_id", "items"}
    assert "email" not in response.model_dump_json()
    assert "hashed_password" not in response.model_dump_json()


def test_cart_item_request_builds_a_record_and_response_uses_current_price(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    movie = catalog_movies[0]
    request = CartItemCreateRequestSchema(movie_id=movie.id)
    cart = CartModel(user_id=catalog_users[0].id)
    item = CartItemModel(cart=cart, **request.model_dump())
    db_session.add(item)
    db_session.commit()
    item_id = item.id
    movie.price = Decimal("12.50")
    db_session.commit()
    db_session.expunge_all()
    stored_item = db_session.scalars(
        select(CartItemModel).where(CartItemModel.id == item_id).options(
            selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres),
        )
    ).one()
    db_session.expunge_all()

    response = CartItemResponseSchema.model_validate(stored_item)
    assert response.id == item_id
    assert response.movie.id == request.movie_id
    assert response.movie.price == Decimal("12.50")

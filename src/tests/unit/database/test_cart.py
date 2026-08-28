from typing import cast

from sqlalchemy import Table, UniqueConstraint

from src.database.models.accounts import UserModel
from src.database.models.cart import CartItemModel, CartModel
from src.database.models.movies import MovieModel


def _unique_column_sets(table: Table) -> set[tuple[str, ...]]:
    return {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_cart_allows_only_one_cart_per_user() -> None:
    table = cast(Table, CartModel.__table__)

    assert ("user_id",) in _unique_column_sets(table)


def test_cart_item_prevents_duplicate_movie_in_cart() -> None:
    table = cast(Table, CartItemModel.__table__)

    assert ("cart_id", "movie_id") in _unique_column_sets(table)


def test_user_and_cart_have_one_to_one_relationship() -> None:
    assert UserModel.cart.property.uselist is False
    assert UserModel.cart.property.back_populates == "user"
    assert CartModel.user.property.back_populates == "cart"


def test_cart_and_items_have_one_to_many_relationship() -> None:
    assert CartModel.items.property.uselist is True
    assert CartModel.items.property.back_populates == "cart"
    assert CartItemModel.cart.property.back_populates == "items"


def test_cart_item_references_movie() -> None:
    assert CartItemModel.movie.property.back_populates == "cart_items"
    assert MovieModel.cart_items.property.back_populates == "movie"


def test_cart_foreign_keys_define_required_delete_behavior() -> None:
    cart_table = cast(Table, CartModel.__table__)
    cart_item_table = cast(Table, CartItemModel.__table__)

    cart_user_fk = next(iter(cart_table.c.user_id.foreign_keys))
    item_cart_fk = next(iter(cart_item_table.c.cart_id.foreign_keys))
    item_movie_fk = next(iter(cart_item_table.c.movie_id.foreign_keys))

    assert cart_user_fk.ondelete == "CASCADE"
    assert item_cart_fk.ondelete == "CASCADE"
    assert item_movie_fk.ondelete == "RESTRICT"


def test_cart_item_added_at_has_database_default() -> None:
    table = cast(Table, CartItemModel.__table__)

    assert table.c.added_at.server_default is not None

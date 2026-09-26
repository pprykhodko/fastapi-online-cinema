from decimal import Decimal

import pytest
from sqlalchemy import select

from src.database import (
    ActivationTokenModel,
    Base,
    CartItemModel,
    CartModel,
    CertificationModel,
    DirectorModel,
    GenreModel,
    MovieModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    StarModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel
)


@pytest.mark.parametrize("model", [
    UserGroupModel(id=1, name=UserGroupEnum.USER),
    UserModel(id=1, email="user@example.com", _hashed_password="private-hash"),
    UserProfileModel(id=1, user_id=1, first_name="Alex", last_name="Smith"),
    ActivationTokenModel(id=1, user_id=1, token="private-activation"),
    PasswordResetTokenModel(id=1, user_id=1, token="private-reset"),
    RefreshTokenModel(id=1, user_id=1, token="private-refresh"),
    CartModel(id=1, user_id=1),
    CartItemModel(id=1, cart_id=1, movie_id=1),
    GenreModel(id=1, name="Action"),
    StarModel(id=1, name="Actor"),
    DirectorModel(id=1, name="Director"),
    CertificationModel(id=1, name="PG-13"),
    MovieModel(id=1, name="Film", year=2020, price=Decimal("9.99"))
])
def test_model_representations_identify_records_without_secrets(
        model: Base
) -> None:
    result = repr(model)
    assert type(model).__name__ in result
    assert "id=1" in result
    assert "private-" not in result


def test_base_has_no_default_ordering() -> None:
    assert Base.default_order_by() is None


def test_movies_default_to_descending_id() -> None:
    query = select(MovieModel).order_by(*MovieModel.default_order_by())
    assert str(query).endswith("ORDER BY movies.id DESC")

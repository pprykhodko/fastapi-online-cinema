from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from sqlalchemy import String, Table

from src.database.models.accounts import (
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
)
from src.database.validators.accounts import (
    validate_email,
    validate_password_strength,
)
from src.security.utils import generate_secure_token


@pytest.mark.parametrize(
    "password",
    [
        "Short1!",
        "lowercase1!",
        "UPPERCASE1!",
        "NoDigits!",
        "NoSpecial1",
    ],
)
def test_validate_password_strength_rejects_weak_passwords(
    password: str,
) -> None:
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_validate_password_strength_accepts_strong_password() -> None:
    password = "StrongPassword1!"

    assert validate_password_strength(password) == password


def test_validate_email_normalizes_address() -> None:
    assert validate_email("User@Example.COM") == "user@example.com"


def test_validate_email_rejects_invalid_address() -> None:
    with pytest.raises(ValueError):
        validate_email("not-an-email")


def test_user_create_normalizes_email_and_hashes_password() -> None:
    raw_password = "StrongPassword1!"

    user = UserModel.create("User@Example.COM", raw_password, group_id=1)

    assert user.email == "user@example.com"
    assert user._hashed_password != raw_password
    assert user.verify_password(raw_password) is True
    assert user.verify_password("WrongPassword1!") is False


def test_user_password_is_write_only() -> None:
    user = UserModel.create(
        "user@example.com",
        "StrongPassword1!",
        group_id=1,
    )

    with pytest.raises(AttributeError):
        _ = user.password


def test_user_has_group() -> None:
    user = UserModel.create(
        "user@example.com",
        "StrongPassword1!",
        group_id=1,
    )
    user.group = UserGroupModel(name=UserGroupEnum.MODERATOR)

    assert user.has_group(UserGroupEnum.MODERATOR) is True
    assert user.has_group(UserGroupEnum.ADMIN) is False


def test_refresh_token_create_sets_expiration() -> None:
    before_creation = datetime.now(timezone.utc)

    refresh_token = RefreshTokenModel.create(
        user_id=1,
        days_valid=7,
        token="refresh-token",
    )

    expected_expiration = before_creation + timedelta(days=7)
    assert refresh_token.expires_at >= expected_expiration
    assert refresh_token.token == "refresh-token"
    assert refresh_token.user_id == 1


def test_generate_secure_token_returns_unique_hex_values() -> None:
    first_token = generate_secure_token()
    second_token = generate_secure_token()

    assert len(first_token) == 64
    assert len(second_token) == 64
    assert first_token != second_token
    int(first_token, 16)
    int(second_token, 16)


def test_token_columns_match_assignment_schema() -> None:
    for model in (
        ActivationTokenModel,
        PasswordResetTokenModel,
        RefreshTokenModel,
    ):
        table = cast(Table, model.__table__)
        token_type = cast(String, table.c.token.type)
        assert token_type.length == 255

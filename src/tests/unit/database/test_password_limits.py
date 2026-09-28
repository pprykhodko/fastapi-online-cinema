import subprocess
import sys
from pathlib import Path

import pytest

from src.database import UserModel
from src.database.validators.accounts import validate_password_strength
from src.security.passwords import hash_password, verify_password


def test_password_module_can_be_imported_before_database_models() -> None:
    subprocess.run(
        [sys.executable, "-c", "import src.security.passwords"],
        cwd=Path(__file__).resolve().parents[4],
        check=True,
        capture_output=True,
        text=True
    )


@pytest.mark.parametrize("password", [
    "Aa1!" + "a" * 68,
    "Aa1!" + "\u044f" * 34,
    "Aa1!" + "\U0001f600" * 17
])
def test_passwords_at_utf8_byte_limit_can_be_hashed(password: str) -> None:
    assert len(password.encode("utf-8")) == 72
    assert validate_password_strength(password) == password
    user = UserModel.create("user@example.com", password, group_id=1)
    assert user.verify_password(password) is True
    assert user.verify_password(password[:-1] + "b") is False


@pytest.mark.parametrize("password", [
    "Aa1!" + "a" * 69,
    "Aa1!" + "\u044f" * 35,
    "Aa1!" + "\U0001f600" * 18
])
def test_passwords_above_utf8_byte_limit_are_rejected(password: str) -> None:
    assert len(password.encode("utf-8")) > 72
    with pytest.raises(ValueError, match="72 bytes"):
        validate_password_strength(password)
    with pytest.raises(ValueError, match="72 bytes"):
        UserModel.create("user@example.com", password, group_id=1)
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password(password)


def test_password_verification_does_not_accept_truncated_suffixes() -> None:
    password = "Aa1!" + "a" * 68
    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True
    assert verify_password(password + "X", hashed_password) is False
    assert verify_password(password + "Y", hashed_password) is False


def test_failed_password_change_preserves_previous_hash() -> None:
    user = UserModel.create("user@example.com", "StrongPassword1!", 1)
    previous_hash = user._hashed_password

    with pytest.raises(ValueError):
        user.password = "Aa1!" + "a" * 69

    assert user._hashed_password == previous_hash
    assert user.verify_password("StrongPassword1!") is True


def test_null_bytes_are_rejected_without_breaking_verification() -> None:
    password = "StrongPassword1!"
    invalid_password = password + "\x00"
    with pytest.raises(ValueError, match="null bytes"):
        validate_password_strength(invalid_password)
    with pytest.raises(ValueError, match="null bytes"):
        hash_password(invalid_password)
    assert verify_password(invalid_password, hash_password(password)) is False

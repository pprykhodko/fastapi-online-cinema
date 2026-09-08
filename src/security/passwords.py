from passlib.context import CryptContext


password_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=True,
)


def validate_password_for_bcrypt(password: str) -> str:
    """Reject inputs bcrypt cannot hash in full, including multibyte text."""
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 bytes in UTF-8.")
    if "\x00" in password:
        raise ValueError("Password must not contain null bytes.")
    return password


def hash_password(raw_password: str) -> str:
    validate_password_for_bcrypt(raw_password)
    return password_context.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    try:
        validate_password_for_bcrypt(raw_password)
    except ValueError:
        return False
    return password_context.verify(raw_password, hashed_password)

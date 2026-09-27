from passlib.context import CryptContext


password_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=True
)


def validate_password_for_bcrypt(password: str) -> str:
    """
    Reject null bytes and plaintext passwords longer than 72 UTF-8 bytes.

    Args:
        password (str): Plaintext password to validate; never log this value.

    Returns:
        str: Original password after checking bcrypt input limits.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 bytes in UTF-8")

    if "\x00" in password:
        raise ValueError("Password must not contain null bytes")

    return password


def hash_password(raw_password: str) -> str:
    """
    Validate bcrypt input limits and generate a salted password hash.

    Args:
        raw_password (str): Plaintext password; never log this value.

    Returns:
        str: Salted bcrypt password hash.

    Raises:
        ValueError: The password contains a null byte or exceeds 72 UTF-8 bytes.
    """
    validate_password_for_bcrypt(raw_password)

    return password_context.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    """
    Check a plaintext password against its stored bcrypt hash.

    Args:
        raw_password (str): Plaintext password; never log this value.
        hashed_password (str): Stored bcrypt hash to compare against.

    Returns:
        bool: Whether the password matches; inputs exceeding bcrypt limits return False.
    """
    try:
        validate_password_for_bcrypt(raw_password)

    except ValueError:
        return False

    return password_context.verify(raw_password, hashed_password)

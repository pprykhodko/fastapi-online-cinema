import re

import email_validator

from src.security.passwords import validate_password_for_bcrypt


def validate_password_strength(password: str) -> str:
    """
    Check bcrypt limits and require a strong password with mixed character types.

    Args:
        password (str): Plaintext password to validate; never log this value.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    validate_password_for_bcrypt(password)
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain an uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain a lowercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain a digit.")
    if not re.search(r"[@$!%*?&#]", password):
        raise ValueError(
            "Password must contain a special character: @, $, !, %, *, "
            "?, #, or &."
        )
    return password


def validate_email(user_email: str) -> str:
    """
    Validate the email syntax and return its normalized lowercase form.

    Args:
        user_email (str): Email address to validate and normalize.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    try:
        email_info = email_validator.validate_email(
            user_email,
            check_deliverability=False,
        )
    except email_validator.EmailNotValidError as error:
        raise ValueError(str(error)) from error
    return email_info.normalized.lower()

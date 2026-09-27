import re
from decimal import Decimal
from math import isfinite
from typing import Optional

from src.database.validators.money import validate_money


def validate_name(name: str) -> str:
    """
    Strip surrounding whitespace and reject an empty name.

    Args:
        name (str): Name to validate and normalize.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Name must not be empty")
    return normalized_name


def validate_genre_name(name: str) -> str:
    """
    Allow only English letters and spaces in a nonempty genre name.

    Args:
        name (str): Name to validate and normalize.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    name = validate_name(name)
    letters = name.replace(" ", "")

    if not letters.isascii() or not letters.isalpha():
        raise ValueError("Genre name must contain only English letters and spaces")

    return name


def validate_star_name(name: str) -> str:
    """
    Allow English name parts separated by a single space or hyphen.

    Args:
        name (str): Name to validate and normalize.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    name = validate_name(name)

    if not re.fullmatch(r"[A-Za-z]+(?:[ -][A-Za-z]+)*", name):
        raise ValueError(
            "Actor name must contain English letters separated by spaces or hyphens"
        )

    return name


def validate_director_name(name: str) -> str:
    """
    Allow English letters, spaces and hyphens in a nonempty director name.

    Args:
        name (str): Name to validate and normalize.

    Returns:
        str: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    name = validate_name(name)
    letters = name.replace(" ", "").replace("-", "")

    if not letters.isascii() or not letters.isalpha():
        raise ValueError(
            "Director name must contain English letters and may include "
            "spaces and hyphens"
        )

    return name


def validate_duration(duration: int) -> int:
    """
    Require a positive movie duration in minutes.

    Args:
        duration (int): Movie running time in minutes.

    Returns:
        int: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if duration <= 0:
        raise ValueError("Movie duration must be greater than zero")

    return duration


def validate_imdb_rating(rating: float) -> float:
    """
    Require an IMDb rating between 0 and 10 inclusive.

    Args:
        rating (float): IMDb rating to validate.

    Returns:
        float: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if not 0 <= rating <= 10:
        raise ValueError("IMDb rating must be between 0 and 10")

    return rating


def validate_votes(votes: int) -> int:
    """
    Reject a negative IMDb vote count.

    Args:
        votes (int): IMDb vote count to validate.

    Returns:
        int: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if votes < 0:
        raise ValueError("Votes must not be negative")

    return votes


def validate_meta_score(score: Optional[float]) -> Optional[float]:
    """
    Allow a missing Metascore or a score between 0 and 100 inclusive.

    Args:
        score (Optional[float]): Numeric score to validate.

    Returns:
        Optional[float]: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if score is not None and not 0 <= score <= 100:
        raise ValueError("Metascore must be between 0 and 100")

    return score


def validate_non_negative_decimal(
    value: Optional[Decimal],
    field_name: str,
) -> Optional[Decimal]:
    """
    Allow no price or a valid nonnegative monetary Decimal.

    Args:
        value (Optional[Decimal]): Field value to validate or normalize.
        field_name (str): Human-readable field name used in validation errors.

    Returns:
        Optional[Decimal]: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if value is None:
        return None

    return validate_money(value, field_name)


def validate_non_negative_float(
    value: Optional[float],
    field_name: str,
) -> Optional[float]:
    """
    Allow no value or a finite nonnegative numeric value.

    Args:
        value (Optional[float]): Field value to validate or normalize.
        field_name (str): Human-readable field name used in validation errors.

    Returns:
        Optional[float]: Validated value, normalized when applicable.

    Raises:
        ValueError: The value does not satisfy the validation rules.
    """
    if value is not None and (not isfinite(value) or value < 0):
        raise ValueError(
            f"{field_name.capitalize()} must be finite and non-negative"
        )

    return value

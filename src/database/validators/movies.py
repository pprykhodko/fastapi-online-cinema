from decimal import Decimal
from math import isfinite
from typing import Optional

from src.database.validators.money import validate_money


def validate_name(name: str) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Name must not be empty.")
    return normalized_name


def validate_genre_name(name: str) -> str:
    name = validate_name(name)
    if not name.isascii() or not name.isalpha():
        raise ValueError("Genre name must contain only English letters.")
    return name


def validate_duration(duration: int) -> int:
    if duration <= 0:
        raise ValueError("Movie duration must be greater than zero.")
    return duration


def validate_imdb_rating(rating: float) -> float:
    if not 0 <= rating <= 10:
        raise ValueError("IMDb rating must be between 0 and 10.")
    return rating


def validate_votes(votes: int) -> int:
    if votes < 0:
        raise ValueError("Votes must not be negative.")
    return votes


def validate_meta_score(score: Optional[float]) -> Optional[float]:
    if score is not None and not 0 <= score <= 100:
        raise ValueError("Metascore must be between 0 and 100.")
    return score


def validate_non_negative_decimal(
    value: Optional[Decimal],
    field_name: str,
) -> Optional[Decimal]:
    if value is None:
        return None
    return validate_money(value, field_name)


def validate_non_negative_float(
    value: Optional[float],
    field_name: str,
) -> Optional[float]:
    if value is not None and (not isfinite(value) or value < 0):
        raise ValueError(
            f"{field_name.capitalize()} must be finite and non-negative."
        )
    return value

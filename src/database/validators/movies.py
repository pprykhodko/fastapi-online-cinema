from decimal import Decimal
from typing import Optional


def validate_name(name: str) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Name must not be empty.")
    return normalized_name


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
    if value is not None and value < 0:
        raise ValueError(f"{field_name.capitalize()} must not be negative.")
    return value


def validate_non_negative_float(
    value: Optional[float],
    field_name: str,
) -> Optional[float]:
    if value is not None and value < 0:
        raise ValueError(f"{field_name.capitalize()} must not be negative.")
    return value

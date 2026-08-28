from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional


EARLIEST_MOVIE_YEAR = 1888
FUTURE_RELEASE_YEAR_LIMIT = 5


def validate_name(name: str) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Name must not be empty.")
    return normalized_name


def validate_release_year(year: int) -> int:
    latest_year = datetime.now(timezone.utc).year + FUTURE_RELEASE_YEAR_LIMIT
    if not EARLIEST_MOVIE_YEAR <= year <= latest_year:
        raise ValueError(
            f"Year must be between {EARLIEST_MOVIE_YEAR} and {latest_year}."
        )
    return year


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

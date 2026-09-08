from typing import Any

import pytest

from src.database import MovieRatingModel
from src.database.validators import validate_user_rating


@pytest.mark.parametrize("score", [1, 5, 10])
def test_user_rating_accepts_integer_scores(score: int) -> None:
    assert validate_user_rating(score) == score
    rating = MovieRatingModel(user_id=1, movie_id=2, score=score)
    assert rating.score == score


@pytest.mark.parametrize("score", [0, -1, 11, 1.5, "8", True, None])
def test_user_rating_rejects_invalid_scores(score: Any) -> None:
    with pytest.raises(ValueError, match="Rating must"):
        validate_user_rating(score)
    with pytest.raises(ValueError, match="Rating must"):
        MovieRatingModel(user_id=1, movie_id=2, score=score)


def test_score_validation_also_applies_to_updates() -> None:
    rating = MovieRatingModel(user_id=1, movie_id=2, score=5)
    with pytest.raises(ValueError):
        rating.score = 11
    assert rating.score == 5


def test_rating_representation() -> None:
    rating = MovieRatingModel(id=1, user_id=2, movie_id=3, score=8)
    assert repr(rating) == (
        "<MovieRatingModel(id=1, user_id=2, movie_id=3, score=8)>"
    )

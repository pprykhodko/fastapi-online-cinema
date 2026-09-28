from typing import Any

import pytest

from src.database import MovieReactionEnum, MovieReactionModel
from src.database.validators import validate_movie_reaction


@pytest.mark.parametrize(
    "reaction",
    ["like", "dislike", MovieReactionEnum.LIKE, MovieReactionEnum.DISLIKE]
)
def test_reaction_accepts_strings_and_enum_members(reaction: str) -> None:
    assert validate_movie_reaction(reaction) == reaction
    model = MovieReactionModel(user_id=1, movie_id=2, reaction=reaction)
    assert isinstance(model.reaction, MovieReactionEnum)
    assert model.reaction.value == reaction


@pytest.mark.parametrize("reaction", ["love", "LIKE", "", " like ", 1, None])
def test_reaction_rejects_unknown_values(reaction: Any) -> None:
    with pytest.raises(ValueError, match="Movie reaction must"):
        validate_movie_reaction(reaction)
    with pytest.raises(ValueError, match="Movie reaction must"):
        MovieReactionModel(user_id=1, movie_id=2, reaction=reaction)


def test_reaction_validation_also_applies_to_updates() -> None:
    model = MovieReactionModel(user_id=1, movie_id=2, reaction="like")
    with pytest.raises(ValueError):
        model.reaction = "love"  # type: ignore[assignment]
    assert model.reaction == MovieReactionEnum.LIKE


def test_reaction_representation() -> None:
    model = MovieReactionModel(id=1, user_id=2, movie_id=3, reaction="like")
    assert repr(model) == (
        f"<MovieReactionModel(id=1, user_id=2, movie_id=3, "
        f"reaction={MovieReactionEnum.LIKE})>"
    )

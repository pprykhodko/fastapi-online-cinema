import pytest

from src.database.models.movies import GenreModel, StarModel
from src.schemas.movies import (
    GenreCreateRequestSchema, GenreUpdateRequestSchema,
    StarCreateRequestSchema,
)


@pytest.mark.parametrize("factory", [
    GenreModel, GenreCreateRequestSchema, GenreUpdateRequestSchema,
])
@pytest.mark.parametrize("name", [
    "123", "Drama2", "!", "Sci-Fi", "Драма", "Comédie", "   ",
    "Dra\nma", "Dra\tma", "🎬", "",
])
def test_genre_requires_english_letters(factory, name):
    with pytest.raises(ValueError):
        factory(name=name)


@pytest.mark.parametrize("factory", [
    GenreModel, GenreCreateRequestSchema, GenreUpdateRequestSchema,
])
@pytest.mark.parametrize("name", [
    "Drama", "action", "SF", "  Fantasy  ", "Science Fiction", " Romantic Comedy ",
])
def test_genre_accepts_english_letters(factory, name):
    assert factory(name=name).name == name.strip()


def test_genre_rule_does_not_restrict_actor_names():
    name = "Jean-Claude Van Damme"
    assert StarModel(name=name).name == name
    assert StarCreateRequestSchema(name=name).name == name

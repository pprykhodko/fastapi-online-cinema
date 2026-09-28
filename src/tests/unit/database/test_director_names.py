import pytest

from src.database.models.movies import DirectorModel, StarModel
from src.schemas.movies import (
    DirectorCreateRequestSchema, DirectorUpdateRequestSchema
)


@pytest.mark.parametrize("factory", [
    DirectorModel, DirectorCreateRequestSchema, DirectorUpdateRequestSchema
])
@pytest.mark.parametrize("name", [
    "123", "Nolan2", "!", "---", " - - ", "Кристофер", "José",
    "O'Connor", "John\tSmith", "John\nSmith", "🎬", ""
])
def test_invalid_director_names(factory, name):
    with pytest.raises(ValueError):
        factory(name=name)


@pytest.mark.parametrize("factory", [
    DirectorModel, DirectorCreateRequestSchema, DirectorUpdateRequestSchema
])
@pytest.mark.parametrize("name", [
    "Nolan", "Wes Anderson", "Jean-Luc Godard", "  Christopher Nolan  "
])
def test_valid_director_names(factory, name):
    assert factory(name=name).name == name.strip()


def test_actor_and_director_accept_hyphenated_names():
    assert StarModel(name="Jean-Claude Van Damme").name == "Jean-Claude Van Damme"

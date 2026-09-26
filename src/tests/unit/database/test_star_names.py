import pytest

from src.database.models.movies import StarModel
from src.schemas.movies import StarCreateRequestSchema, StarUpdateRequestSchema


@pytest.mark.parametrize(
    "factory", [StarModel, StarCreateRequestSchema, StarUpdateRequestSchema]
)
@pytest.mark.parametrize(
    "name",
    [
        "Tom Hanks",
        "Jean-Claude Van Damme",
        " Mary Smith-Jones ",
        "Keanu"
    ]
)
def test_valid_star_names(factory, name):
    assert factory(name=name).name == name.strip()


@pytest.mark.parametrize(
    "factory", [StarModel, StarCreateRequestSchema, StarUpdateRequestSchema]
)
@pytest.mark.parametrize(
    "name",
    [
        "123",
        "Tom2",
        "Том",
        "Penélope Cruz",
        "Tom!",
        "Tom?",
        "O'Connor",
        "—-",
        "---",
        " - - ",
        "",
        "   ",
        "Tom\tHanks",
        "Tom\nHanks",
        "Tom—Hanks",
        "-Tom",
        "Tom-",
        "Tom--Hanks",
        "Tom - Hanks"
    ]
)
def test_invalid_star_names(factory, name):
    with pytest.raises(ValueError):
        factory(name=name)

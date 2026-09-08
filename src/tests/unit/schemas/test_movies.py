from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.schemas.favorites import MovieFavoriteListQuerySchema
from src.schemas.movies import (
    GenreCreateRequestSchema,
    GenreUpdateRequestSchema,
    GenreWithMovieCountResponseSchema,
    MovieCreateRequestSchema,
    MovieListQuerySchema,
    MovieListResponseSchema,
    MovieUpdateRequestSchema,
    StarCreateRequestSchema,
    StarUpdateRequestSchema,
)


@pytest.fixture
def movie_data() -> dict[str, Any]:
    return {
        "name": "  The Matrix  ", "year": 1999, "time": 136,
        "imdb": 8.7, "votes": 2_000_000,
        "description": "A hacker discovers the nature of reality.",
        "price": "9.99", "certification_id": 1,
        "genre_ids": [1, 2], "star_ids": [3], "director_ids": [4],
    }


@pytest.mark.parametrize("schema", [
    MovieCreateRequestSchema, MovieUpdateRequestSchema,
])
def test_movie_requests_normalize_names_and_parse_decimal_prices(
    schema: type[BaseModel], movie_data: dict[str, Any],
) -> None:
    data = schema.model_validate(movie_data).model_dump()
    assert data["name"] == "The Matrix"
    assert data["price"] == Decimal("9.99")
    assert isinstance(data["price"], Decimal)
    assert data["genre_ids"] == [1, 2]
    assert data["meta_score"] is None
    assert data["gross"] is None


@pytest.mark.parametrize("schema", [
    MovieCreateRequestSchema, MovieUpdateRequestSchema,
])
@pytest.mark.parametrize(("field", "value"), [
    ("name", ""), ("name", "   "), ("name", "a" * 251),
    ("year", 1999.5), ("year", True), ("time", 0), ("time", -1),
    ("time", 1.5), ("time", True), ("votes", -1), ("votes", True),
    ("imdb", -0.1), ("imdb", 10.1), ("imdb", float("nan")),
    ("meta_score", -1), ("meta_score", 101),
    ("gross", -0.01), ("gross", float("inf")),
    ("price", "-0.01"), ("price", "100000000"), ("price", "9.999"),
    ("price", "NaN"), ("price", "Infinity"),
    ("certification_id", 0), ("certification_id", True),
    ("id", 1), ("uuid", "client-selected-uuid"), ("user_id", 1),
])
def test_movie_requests_reject_invalid_fields(
    schema: type[BaseModel], movie_data: dict[str, Any],
    field: str, value: Any,
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({**movie_data, field: value})


@pytest.mark.parametrize("field", [
    "name", "year", "time", "imdb", "votes", "description", "price",
    "certification_id", "genre_ids", "star_ids", "director_ids",
])
def test_movie_update_does_not_allow_null_for_required_columns_or_lists(
    movie_data: dict[str, Any], field: str,
) -> None:
    with pytest.raises(ValidationError):
        MovieUpdateRequestSchema.model_validate({**movie_data, field: None})


@pytest.mark.parametrize("field", ["genre_ids", "star_ids", "director_ids"])
@pytest.mark.parametrize("ids", [[0], [-1], [1, 1], [True], [1.5], ["1"], "1"])
def test_movie_related_ids_must_be_unique_positive_integer_lists(
    movie_data: dict[str, Any], field: str, ids: Any,
) -> None:
    with pytest.raises(ValidationError):
        MovieCreateRequestSchema.model_validate({**movie_data, field: ids})


def test_movie_update_uses_full_replacement(
    movie_data: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        MovieUpdateRequestSchema.model_validate({"price": "4.99"})
    updated = MovieUpdateRequestSchema.model_validate({
        **movie_data, "meta_score": None, "gross": None,
        "genre_ids": [], "star_ids": [], "director_ids": [],
    })
    assert updated.meta_score is None
    assert updated.gross is None
    assert updated.genre_ids == []


def test_optional_movie_lists_are_not_shared(
    movie_data: dict[str, Any],
) -> None:
    for field in ("genre_ids", "star_ids", "director_ids"):
        movie_data.pop(field)
    first = MovieCreateRequestSchema.model_validate(movie_data)
    second = MovieCreateRequestSchema.model_validate(movie_data)
    first.genre_ids.append(1)
    assert second.genre_ids == []
    assert first.star_ids == []
    assert second.director_ids == []


@pytest.mark.parametrize("price", ["0", "0.01", "99999999.99", "9.9900"])
def test_movie_prices_accept_valid_boundaries(
    movie_data: dict[str, Any], price: str,
) -> None:
    request = MovieCreateRequestSchema.model_validate({
        **movie_data, "price": price,
    })
    assert request.price == Decimal(price)


@pytest.mark.parametrize("schema", [
    GenreCreateRequestSchema, GenreUpdateRequestSchema,
    StarCreateRequestSchema, StarUpdateRequestSchema,
])
def test_named_entity_requests_validate_and_normalize(
    schema: type[BaseModel],
) -> None:
    assert schema.model_validate({"name": "  Action  "}).model_dump() == {
        "name": "Action",
    }
    data = schema.model_validate({"name": "a" * 100}).model_dump()
    assert len(data["name"]) == 100
    for data in (
        {"name": "   "}, {"name": "a" * 101}, {"name": "A", "id": 1},
    ):
        with pytest.raises(ValidationError):
            schema.model_validate(data)


@pytest.mark.parametrize("schema", [
    MovieListQuerySchema, MovieFavoriteListQuerySchema,
])
def test_catalog_and_favorites_share_query_parameters(
    schema: type[BaseModel],
) -> None:
    query = schema.model_validate({
        "page": "2", "per_page": "20", "year": "1999", "min_imdb": "8.0",
        "genre_id": "1", "search": "  Keanu Reeves  ",
        "sort_by": "popularity", "sort_order": "desc",
    }).model_dump()
    assert query["page"] == 2
    assert query["year"] == 1999
    assert query["min_imdb"] == 8.0
    assert query["search"] == "Keanu Reeves"
    defaults = schema.model_validate({"search": None}).model_dump()
    assert defaults["page"] == 1
    assert defaults["per_page"] == 10
    assert defaults["search"] is None


@pytest.mark.parametrize("schema", [
    MovieListQuerySchema, MovieFavoriteListQuerySchema,
])
@pytest.mark.parametrize(("field", "value"), [
    ("page", 0), ("per_page", 0), ("per_page", 101), ("genre_id", -1),
    ("min_imdb", -1), ("min_imdb", 11), ("min_imdb", "NaN"),
    ("search", "   "), ("sort_by", "id; DROP TABLE movies"),
    ("sort_order", "random"), ("user_id", 1),
])
def test_catalog_query_rejects_invalid_values(
    schema: type[BaseModel], field: str, value: Any,
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({field: value})


def test_movie_list_and_genre_count_responses() -> None:
    response = MovieListResponseSchema(items=[], total=0, page=1, per_page=10)
    assert response.model_dump()["items"] == []
    genre = GenreWithMovieCountResponseSchema(
        id=1, name="Action", movie_count=2,
    )
    assert genre.movie_count == 2
    with pytest.raises(ValidationError):
        GenreWithMovieCountResponseSchema.model_validate({
            "id": 1, "name": "A",
        })
    with pytest.raises(ValidationError):
        MovieListResponseSchema(items=[], total=-1, page=1, per_page=10)


def test_movie_request_json_schema_contains_constraints() -> None:
    schema = MovieCreateRequestSchema.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["name"]["maxLength"] == 250
    assert schema["properties"]["imdb"]["maximum"] == 10
    assert "price" in schema["required"]

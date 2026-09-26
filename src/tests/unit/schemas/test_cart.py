from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from src.schemas.cart import (
    CartItemCreateRequestSchema,
    CartItemResponseSchema,
    CartResponseSchema
)


@pytest.fixture
def cart_item_data() -> dict[str, Any]:
    return {
        "id": 3,
        "added_at": datetime(2026, 9, 10, tzinfo=timezone.utc),
        "movie": {
            "id": 5,
            "name": "The Matrix",
            "year": 1999,
            "time": 136,
            "imdb": 8.7,
            "price": Decimal("9.99"),
            "is_available_for_purchase": True,
            "genres": [{"id": 1, "name": "Action"}]
        }
    }


def test_add_to_cart_request_accepts_a_positive_movie_id() -> None:
    request = CartItemCreateRequestSchema(movie_id=5)
    assert request.model_dump() == {"movie_id": 5}


@pytest.mark.parametrize("movie_id", [
    0, -1, True, False, 1.5, 1.0, "1", None, []
])
def test_add_to_cart_request_rejects_invalid_movie_ids(movie_id: Any) -> None:
    with pytest.raises(ValidationError):
        CartItemCreateRequestSchema.model_validate({"movie_id": movie_id})


def test_add_to_cart_request_requires_a_movie_id() -> None:
    with pytest.raises(ValidationError):
        CartItemCreateRequestSchema.model_validate({})


@pytest.mark.parametrize("field", [
    "user_id", "cart_id", "id", "price", "quantity", "added_at"
])
def test_add_to_cart_request_rejects_client_supplied_server_fields(
        field: str
) -> None:
    with pytest.raises(ValidationError) as error:
        CartItemCreateRequestSchema.model_validate({"movie_id": 5, field: 1})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_cart_item_contains_required_movie_details(
        cart_item_data: dict[str, Any]
) -> None:
    item = CartItemResponseSchema.model_validate(cart_item_data)
    assert item.movie.name == "The Matrix"
    assert item.movie.price == Decimal("9.99")
    assert item.movie.year == 1999
    assert item.movie.genres[0].name == "Action"
    data = item.model_dump(mode="json")
    assert data["movie"]["price"] == "9.99"
    assert data["added_at"] == "2026-09-10T00:00:00Z"
    assert set(data) == {"id", "movie", "added_at"}


def test_cart_response_supports_empty_and_populated_carts(
        cart_item_data: dict[str, Any]
) -> None:
    empty = CartResponseSchema(id=1, user_id=2, items=[])
    assert empty.model_dump() == {"id": 1, "user_id": 2, "items": []}
    cart = CartResponseSchema.model_validate({
        "id": 1, "user_id": 2, "items": [cart_item_data]
    })
    assert len(cart.items) == 1
    assert cart.items[0].movie.id == 5


@pytest.mark.parametrize("items", [None, "not-a-list", [{}]])
def test_cart_response_rejects_invalid_items(items: Any) -> None:
    with pytest.raises(ValidationError):
        CartResponseSchema.model_validate({
            "id": 1, "user_id": 2, "items": items
        })


def test_cart_response_requires_items_instead_of_assuming_empty_cart() -> None:
    with pytest.raises(ValidationError):
        CartResponseSchema.model_validate({"id": 1, "user_id": 2})


@pytest.mark.parametrize("field", ["id", "user_id"])
@pytest.mark.parametrize("value", [0, -1])
def test_cart_response_rejects_non_positive_ids(
        field: str, value: int
) -> None:
    with pytest.raises(ValidationError):
        CartResponseSchema.model_validate({
            "id": 1, "user_id": 2, "items": [], field: value
        })


def test_cart_json_schema_documents_request_and_nested_items() -> None:
    request = CartItemCreateRequestSchema.model_json_schema()
    assert request["additionalProperties"] is False
    assert request["required"] == ["movie_id"]
    assert request["properties"]["movie_id"]["exclusiveMinimum"] == 0
    response = CartResponseSchema.model_json_schema()
    assert response["properties"]["items"]["type"] == "array"
    assert "CartItemResponseSchema" in response["$defs"]
    assert "MovieListItemResponseSchema" in response["$defs"]

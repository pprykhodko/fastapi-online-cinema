from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.schemas.interactions import (
    MovieCommentListResponseSchema, MovieFavoriteListResponseSchema,
)
from src.schemas.movies import MovieListResponseSchema
from src.schemas.orders import OrderListResponseSchema
from src.schemas.payments import PaymentListResponseSchema


@pytest.fixture(params=[
    MovieCommentListResponseSchema,
    MovieFavoriteListResponseSchema,
    MovieListResponseSchema,
    OrderListResponseSchema,
    PaymentListResponseSchema,
])
def list_schema(request: pytest.FixtureRequest) -> type[BaseModel]:
    return request.param


def test_list_responses_preserve_pagination_fields(
    list_schema: type[BaseModel],
) -> None:
    data = {"items": [], "total": 0, "page": 1, "per_page": 100}
    assert list_schema.model_validate(data).model_dump() == data


@pytest.mark.parametrize("field", ["items", "total", "page", "per_page"])
def test_list_responses_still_require_all_fields(
    list_schema: type[BaseModel], field: str,
) -> None:
    data = {"items": [], "total": 0, "page": 1, "per_page": 10}
    data.pop(field)
    with pytest.raises(ValidationError) as error:
        list_schema.model_validate(data)
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(("field", "value"), [
    ("total", -1), ("page", 0), ("per_page", 0), ("per_page", 101),
])
def test_list_responses_keep_pagination_limits(
    list_schema: type[BaseModel], field: str, value: Any,
) -> None:
    data = {"items": [], "total": 0, "page": 1, "per_page": 10}
    with pytest.raises(ValidationError) as error:
        list_schema.model_validate({**data, field: value})
    assert error.value.errors()[0]["loc"] == (field,)

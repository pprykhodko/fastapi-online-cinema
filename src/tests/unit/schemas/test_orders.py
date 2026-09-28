from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.database import OrderStatusEnum
from src.schemas.orders import (
    AdminOrderListQuerySchema,
    OrderCreateResponseSchema,
    OrderExcludedItemSchema,
    OrderItemResponseSchema,
    OrderListQuerySchema,
    OrderListResponseSchema,
    OrderResponseSchema
)


@pytest.fixture
def order_data() -> dict[str, Any]:
    return {
        "id": 1,
        "user_id": 2,
        "created_at": datetime(2026, 9, 10, tzinfo=timezone.utc),
        "status": "pending",
        "total_amount": "9.99",
        "items": [{
            "id": 3,
            "movie": {"id": 4, "name": "The Matrix", "year": 1999},
            "price_at_order": "9.99"
        }]
    }


def test_order_response_contains_movie_and_price_snapshot(
        order_data: dict[str, Any]
) -> None:
    response = OrderResponseSchema.model_validate(order_data)
    assert response.status is OrderStatusEnum.PENDING
    assert response.total_amount == Decimal("9.99")
    assert response.items[0].price_at_order == Decimal("9.99")
    data = response.model_dump(mode="json")
    assert data["status"] == "pending"
    assert data["total_amount"] == "9.99"
    assert data["items"][0]["movie"]["name"] == "The Matrix"
    assert "price" not in data["items"][0]["movie"]


@pytest.mark.parametrize("status", list(OrderStatusEnum))
def test_order_response_accepts_all_assignment_statuses(
        order_data: dict[str, Any], status: OrderStatusEnum
) -> None:
    response = OrderResponseSchema.model_validate({
        **order_data, "status": status.value
    })
    assert response.status is status


@pytest.mark.parametrize("status", ["invalid", "PAID", "", 1, None])
def test_order_response_rejects_unknown_statuses(
        order_data: dict[str, Any], status: Any
) -> None:
    with pytest.raises(ValidationError):
        OrderResponseSchema.model_validate({**order_data, "status": status})


@pytest.mark.parametrize("amount", [
    "0", "0.01", "9.9900", "99999999.99"
])
def test_order_amounts_accept_valid_decimal_values(
        order_data: dict[str, Any], amount: str
) -> None:
    response = OrderResponseSchema.model_validate({
        **order_data, "total_amount": amount
    })
    item = OrderItemResponseSchema.model_validate({
        **order_data["items"][0], "price_at_order": amount
    })
    assert response.total_amount == Decimal(amount)
    assert item.price_at_order == Decimal(amount)


@pytest.mark.parametrize("amount", [
    "-0.01", "100000000", "0.001", "NaN", "sNaN", "Infinity",
    "-Infinity", True, "not-a-price"
])
def test_order_amounts_reject_invalid_decimal_values(
        order_data: dict[str, Any], amount: Any
) -> None:
    with pytest.raises(ValidationError):
        OrderResponseSchema.model_validate({
            **order_data, "total_amount": amount
        })
    with pytest.raises(ValidationError):
        OrderItemResponseSchema.model_validate({
            **order_data["items"][0], "price_at_order": amount
        })


def test_only_order_total_can_be_null(order_data: dict[str, Any]) -> None:
    response = OrderResponseSchema.model_validate({
        **order_data, "total_amount": None
    })
    assert response.total_amount is None
    with pytest.raises(ValidationError):
        OrderItemResponseSchema.model_validate({
            **order_data["items"][0], "price_at_order": None
        })


@pytest.mark.parametrize("field", ["total_amount", "items", "status"])
def test_order_response_requires_fields_instead_of_guessing_defaults(
        order_data: dict[str, Any], field: str
) -> None:
    order_data.pop(field)
    with pytest.raises(ValidationError):
        OrderResponseSchema.model_validate(order_data)


@pytest.mark.parametrize(("field", "value"), [
    ("id", 0), ("user_id", -1), ("items", None), ("created_at", "not-a-date")
])
def test_order_response_rejects_invalid_fields(
        order_data: dict[str, Any], field: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        OrderResponseSchema.model_validate({**order_data, field: value})


@pytest.mark.parametrize("schema", [
    OrderListQuerySchema, AdminOrderListQuerySchema
])
def test_order_list_queries_parse_pagination(schema: type[BaseModel]) -> None:
    defaults = schema.model_validate({}).model_dump()
    assert defaults["page"] == 1
    assert defaults["per_page"] == 10
    query = schema.model_validate({"page": "2", "per_page": "25"})
    assert query.model_dump()["page"] == 2
    assert query.model_dump()["per_page"] == 25


@pytest.mark.parametrize("schema", [
    OrderListQuerySchema, AdminOrderListQuerySchema
])
@pytest.mark.parametrize(("field", "value"), [
    ("page", 0), ("page", "invalid"), ("per_page", 0), ("per_page", 101)
])
def test_order_list_queries_reject_invalid_pagination(
        schema: type[BaseModel], field: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({field: value})


@pytest.mark.parametrize("field", [
    "user_id", "cart_id", "status", "total_amount", "date_from"
])
def test_regular_order_list_does_not_accept_admin_or_server_fields(
        field: str
) -> None:
    with pytest.raises(ValidationError) as error:
        OrderListQuerySchema.model_validate({field: 1})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_admin_order_query_parses_filters() -> None:
    query = AdminOrderListQuerySchema.model_validate({
        "user_id": "2", "status": "paid",
        "date_from": "2026-09-01", "date_to": "2026-09-10"
    })
    assert query.user_id == 2
    assert query.status is OrderStatusEnum.PAID
    assert query.date_from == date(2026, 9, 1)
    assert query.date_to == date(2026, 9, 10)


@pytest.mark.parametrize("filters", [
    {"date_from": "2026-09-10", "date_to": "2026-09-10"},
    {"date_from": "2026-09-10", "date_to": None},
    {"date_to": "2026-09-10"},
    {"date_from": None, "date_to": None}
])
def test_admin_date_filters_allow_equal_and_open_ended_ranges(
        filters: dict[str, Any]
) -> None:
    query = AdminOrderListQuerySchema.model_validate(filters)
    assert query.model_dump(exclude_unset=True).keys() == filters.keys()


@pytest.mark.parametrize("filters", [
    {"date_from": "2026-09-10", "date_to": "2026-09-01"},
    {"date_from": "2026-02-30"}, {"date_to": "invalid"},
    {"user_id": 0}, {"status": "successful"}, {"total_amount": "0"}
])
def test_admin_order_query_rejects_invalid_filters(
        filters: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        AdminOrderListQuerySchema.model_validate(filters)


def test_order_list_response_handles_empty_and_populated_pages(
        order_data: dict[str, Any]
) -> None:
    empty = OrderListResponseSchema(items=[], total=0, page=1, per_page=10)
    assert empty.items == []
    response = OrderListResponseSchema.model_validate({
        "items": [order_data], "total": 1, "page": 1, "per_page": 10
    })
    assert response.items[0].id == 1
    with pytest.raises(ValidationError):
        OrderListResponseSchema(items=[], total=-1, page=1, per_page=10)


def test_order_schemas_expose_status_and_date_metadata() -> None:
    schema = AdminOrderListQuerySchema.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["OrderStatusEnum"]["enum"] == [
        "pending", "paid", "canceled"
    ]
    date_options = schema["properties"]["date_from"]["anyOf"]
    assert {"type": "string", "format": "date"} in date_options
    response = OrderResponseSchema.model_json_schema()
    assert "total_amount" in response["required"]
    assert "OrderItemResponseSchema" in response["$defs"]


def test_order_creation_response_includes_order_and_exclusion_reasons(
        order_data: dict[str, Any]
) -> None:
    response = OrderCreateResponseSchema.model_validate({
        "message": "Order created. Some movies were excluded.",
        "order": order_data,
        "excluded_items": [
            {"movie_id": 5, "reason": "Movie has already been purchased."},
            {"movie_id": 6, "reason": "Movie is unavailable in your region."},
            {"movie_id": 7, "reason": "Movie no longer exists."}
        ]
    })
    assert response.order is not None
    assert response.order.id == 1
    assert response.model_dump(mode="json")["order"]["total_amount"] == "9.99"
    assert [item.movie_id for item in response.excluded_items] == [5, 6, 7]
    assert "already been purchased" in response.excluded_items[0].reason


def test_order_creation_response_allows_no_exclusions(
        order_data: dict[str, Any]
) -> None:
    response = OrderCreateResponseSchema.model_validate({
        "message": "Order created.", "order": order_data, "excluded_items": []
    })
    assert response.excluded_items == []


def test_order_creation_response_handles_all_movies_excluded() -> None:
    response = OrderCreateResponseSchema.model_validate({
        "message": "No order was created: no movies available for purchase.",
        "order": None,
        "excluded_items": [{"movie_id": 1, "reason": "Already purchased."}]
    })
    assert response.model_dump(mode="json")["order"] is None
    assert response.excluded_items[0].movie_id == 1


@pytest.mark.parametrize("field", ["message", "order", "excluded_items"])
def test_order_creation_response_requires_explicit_result(field: str) -> None:
    data: dict[str, Any] = {
        "message": "No order created.", "order": None, "excluded_items": []
    }
    data.pop(field)
    with pytest.raises(ValidationError) as error:
        OrderCreateResponseSchema.model_validate(data)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("data", [
    {"movie_id": 0, "reason": "Unavailable."},
    {"movie_id": 1, "reason": ""}, {"movie_id": 1},
    {"movie_id": 1, "reason": None}
])
def test_excluded_movie_requires_id_and_reason(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        OrderExcludedItemSchema.model_validate(data)


def test_order_creation_metadata_includes_exclusions() -> None:
    schema = OrderCreateResponseSchema.model_json_schema()
    assert {"type": "null"} in schema["properties"]["order"]["anyOf"]
    assert set(schema["required"]) == {"message", "order", "excluded_items"}
    assert "OrderExcludedItemSchema" in schema["$defs"]

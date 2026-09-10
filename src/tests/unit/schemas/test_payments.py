from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.database import PaymentStatusEnum
from src.schemas.payments import (
    AdminPaymentListQuerySchema,
    PaymentCheckoutResponseSchema,
    PaymentCreateRequestSchema,
    PaymentItemResponseSchema,
    PaymentListQuerySchema,
    PaymentListResponseSchema,
    PaymentResponseSchema,
)


@pytest.fixture
def payment_data() -> dict[str, Any]:
    return {
        "id": 1, "user_id": 2, "order_id": 3,
        "created_at": datetime(2026, 9, 10, tzinfo=timezone.utc),
        "status": "successful", "amount": "9.99",
        "external_payment_id": "pi_test_123",
        "items": [{"id": 4, "order_item_id": 5, "price_at_payment": "9.99"}],
    }


def test_payment_creation_accepts_only_order_id() -> None:
    request = PaymentCreateRequestSchema(order_id=3)
    assert request.model_dump() == {"order_id": 3}


@pytest.mark.parametrize("order_id", [0, -1, True, "3", 3.0, None])
def test_payment_creation_rejects_invalid_order_id(order_id: Any) -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequestSchema(order_id=order_id)


def test_payment_creation_requires_order_id() -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequestSchema.model_validate({})


@pytest.mark.parametrize("field", [
    "user_id", "amount", "status", "items", "external_payment_id",
    "success_url", "cancel_url",
])
def test_payment_creation_rejects_server_controlled_fields(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        PaymentCreateRequestSchema.model_validate({"order_id": 3, field: 1})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_checkout_response_serializes_payment_page_url() -> None:
    response = PaymentCheckoutResponseSchema.model_validate({
        "order_id": 3,
        "checkout_url": "https://checkout.stripe.com/c/pay/test",
    })
    assert response.model_dump(mode="json") == {
        "order_id": 3,
        "checkout_url": "https://checkout.stripe.com/c/pay/test",
    }


@pytest.mark.parametrize("url", ["not-a-url", "/pay", "javascript:alert(1)"])
def test_checkout_response_rejects_invalid_url(url: str) -> None:
    with pytest.raises(ValidationError):
        PaymentCheckoutResponseSchema.model_validate({
            "order_id": 3, "checkout_url": url,
        })


def test_payment_response_serializes_amounts_and_items(
    payment_data: dict[str, Any],
) -> None:
    response = PaymentResponseSchema.model_validate(payment_data)
    assert response.amount == Decimal("9.99")
    assert response.items[0].price_at_payment == Decimal("9.99")
    data = response.model_dump(mode="json")
    assert data["amount"] == "9.99"
    assert data["status"] == "successful"
    assert data["items"][0] == {
        "id": 4, "order_item_id": 5, "price_at_payment": "9.99",
    }


@pytest.mark.parametrize("status", list(PaymentStatusEnum))
def test_payment_response_accepts_assignment_statuses(
    payment_data: dict[str, Any], status: PaymentStatusEnum,
) -> None:
    response = PaymentResponseSchema.model_validate({
        **payment_data, "status": status.value,
    })
    assert response.status is status


@pytest.mark.parametrize("status", ["pending", "paid", "SUCCESSFUL", "", None])
def test_payment_response_rejects_invalid_status(
    payment_data: dict[str, Any], status: Any,
) -> None:
    with pytest.raises(ValidationError):
        PaymentResponseSchema.model_validate({
            **payment_data, "status": status,
        })


@pytest.mark.parametrize("amount", ["0", "0.01", "9.9900", "99999999.99"])
def test_payment_amounts_accept_valid_values(
    payment_data: dict[str, Any], amount: str,
) -> None:
    response = PaymentResponseSchema.model_validate({
        **payment_data, "amount": amount,
    })
    item = PaymentItemResponseSchema.model_validate({
        **payment_data["items"][0], "price_at_payment": amount,
    })
    assert response.amount == Decimal(amount)
    assert item.price_at_payment == Decimal(amount)


@pytest.mark.parametrize("amount", [
    "-0.01", "100000000", "0.001", "NaN", "sNaN", "Infinity",
    "-Infinity", True, None, "not-a-price",
])
def test_payment_amounts_reject_invalid_values(
    payment_data: dict[str, Any], amount: Any,
) -> None:
    with pytest.raises(ValidationError):
        PaymentResponseSchema.model_validate({
            **payment_data, "amount": amount,
        })
    with pytest.raises(ValidationError):
        PaymentItemResponseSchema.model_validate({
            **payment_data["items"][0], "price_at_payment": amount,
        })


@pytest.mark.parametrize("external_id", [None, "pi_test_123", "x" * 255])
def test_payment_external_id_can_be_null_or_string(
    payment_data: dict[str, Any], external_id: str | None,
) -> None:
    response = PaymentResponseSchema.model_validate({
        **payment_data, "external_payment_id": external_id,
    })
    assert response.external_payment_id == external_id


@pytest.mark.parametrize("field", [
    "status", "amount", "external_payment_id", "items",
])
def test_payment_response_does_not_invent_missing_values(
    payment_data: dict[str, Any], field: str,
) -> None:
    payment_data.pop(field)
    with pytest.raises(ValidationError):
        PaymentResponseSchema.model_validate(payment_data)


@pytest.mark.parametrize(("field", "value"), [
    ("id", 0), ("user_id", -1), ("order_id", 0),
    ("created_at", "not-a-date"), ("external_payment_id", "x" * 256),
    ("items", None),
])
def test_payment_response_rejects_invalid_fields(
    payment_data: dict[str, Any], field: str, value: Any,
) -> None:
    with pytest.raises(ValidationError):
        PaymentResponseSchema.model_validate({**payment_data, field: value})


@pytest.mark.parametrize("field", ["id", "order_item_id"])
def test_payment_item_requires_positive_ids(
    payment_data: dict[str, Any], field: str,
) -> None:
    with pytest.raises(ValidationError):
        PaymentItemResponseSchema.model_validate({
            **payment_data["items"][0], field: 0,
        })


@pytest.mark.parametrize("schema", [
    PaymentListQuerySchema, AdminPaymentListQuerySchema,
])
def test_payment_queries_parse_pagination(schema: type[BaseModel]) -> None:
    defaults = schema.model_validate({}).model_dump()
    assert defaults["page"] == 1
    assert defaults["per_page"] == 10
    query = schema.model_validate({"page": "2", "per_page": "25"}).model_dump()
    assert query["page"] == 2
    assert query["per_page"] == 25


@pytest.mark.parametrize("schema", [
    PaymentListQuerySchema, AdminPaymentListQuerySchema,
])
@pytest.mark.parametrize(("field", "value"), [
    ("page", 0), ("page", "invalid"), ("per_page", 0), ("per_page", 101),
])
def test_payment_queries_reject_invalid_pagination(
    schema: type[BaseModel], field: str, value: Any,
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({field: value})


@pytest.mark.parametrize("field", ["user_id", "status", "date_from", "amount"])
def test_user_payment_query_rejects_extra_filters(field: str) -> None:
    with pytest.raises(ValidationError) as error:
        PaymentListQuerySchema.model_validate({field: 1})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_admin_payment_query_parses_filters() -> None:
    query = AdminPaymentListQuerySchema.model_validate({
        "user_id": "2", "status": "refunded",
        "date_from": "2026-09-01", "date_to": "2026-09-10",
    })
    assert query.user_id == 2
    assert query.status is PaymentStatusEnum.REFUNDED
    assert query.date_from == date(2026, 9, 1)
    assert query.date_to == date(2026, 9, 10)


@pytest.mark.parametrize("filters", [
    {"date_from": "2026-09-10", "date_to": "2026-09-10"},
    {"date_from": "2026-09-10", "date_to": None},
    {"date_to": "2026-09-10"}, {"date_from": None, "date_to": None},
])
def test_admin_payment_query_allows_equal_and_open_date_ranges(
    filters: dict[str, Any],
) -> None:
    query = AdminPaymentListQuerySchema.model_validate(filters)
    assert query.model_dump(exclude_unset=True).keys() == filters.keys()


@pytest.mark.parametrize("filters", [
    {"date_from": "2026-09-10", "date_to": "2026-09-01"},
    {"date_from": "2026-02-30"}, {"date_to": "invalid"},
    {"user_id": 0}, {"status": "paid"}, {"amount": "0"},
])
def test_admin_payment_query_rejects_invalid_filters(
    filters: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        AdminPaymentListQuerySchema.model_validate(filters)


def test_payment_list_response_handles_empty_and_populated_pages(
    payment_data: dict[str, Any],
) -> None:
    empty = PaymentListResponseSchema(items=[], total=0, page=1, per_page=10)
    assert empty.items == []
    response = PaymentListResponseSchema.model_validate({
        "items": [payment_data], "total": 1, "page": 1, "per_page": 10,
    })
    assert response.items[0].id == 1
    with pytest.raises(ValidationError):
        PaymentListResponseSchema(items=[], total=-1, page=1, per_page=10)


def test_payment_schemas_expose_required_fields_and_status_metadata() -> None:
    request = PaymentCreateRequestSchema.model_json_schema()
    assert request["additionalProperties"] is False
    assert request["required"] == ["order_id"]
    response = PaymentResponseSchema.model_json_schema()
    assert response["$defs"]["PaymentStatusEnum"]["enum"] == [
        "successful", "canceled", "refunded",
    ]
    assert "status" in response["required"]
    assert "default" not in response["properties"]["status"]

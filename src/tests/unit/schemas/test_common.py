from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from src.schemas.common import ErrorResponseSchema, MessageResponseSchema


def test_message_response_reads_attributes() -> None:
    response = MessageResponseSchema.model_validate(
        SimpleNamespace(message="Operation completed."),
    )
    assert response.model_dump() == {"message": "Operation completed."}


@pytest.mark.parametrize("message", ["", None, 1])
def test_message_response_rejects_invalid_message(message: Any) -> None:
    with pytest.raises(ValidationError):
        MessageResponseSchema(message=message)


def test_error_response_can_include_payment_recommendation() -> None:
    response = ErrorResponseSchema(
        detail="Payment was declined.",
        recommendation="Try a different payment method.",
    )
    assert response.model_dump() == {
        "detail": "Payment was declined.",
        "recommendation": "Try a different payment method.",
    }


def test_error_response_does_not_require_recommendation() -> None:
    response = ErrorResponseSchema(detail="Movie has already been purchased.")
    assert response.recommendation is None
    assert response.model_dump(exclude_none=True) == {
        "detail": "Movie has already been purchased.",
    }


@pytest.mark.parametrize("data", [
    {}, {"detail": ""}, {"detail": None},
    {"detail": "Error.", "recommendation": ""},
])
def test_error_response_requires_non_empty_text(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ErrorResponseSchema.model_validate(data)

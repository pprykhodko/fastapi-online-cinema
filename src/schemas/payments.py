from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from src.database.models.payments import PaymentStatusEnum
from src.database.validators import payments as payments_validators
from src.schemas.common import (
    AdminTransactionListQuerySchema,
    MessageResponseSchema,
    PaginationQuerySchema,
    PaginationResponseSchema
)
from src.schemas.movies import MovieListItemResponseSchema


class PaymentCreateRequestSchema(BaseModel):
    order_id: int = Field(gt=0, le=2**31 - 1, strict=True)

    model_config = {
        "extra": "forbid"
    }


class PaymentCheckoutResponseSchema(BaseModel):
    order_id: int = Field(gt=0)
    checkout_url: HttpUrl


class PaymentRefundRequestSchema(BaseModel):
    payment_id: int = Field(gt=0, le=2**31 - 1, strict=True)

    model_config = {
        "extra": "forbid"
    }


class PaymentRefundResponseSchema(MessageResponseSchema):
    payment_id: int = Field(gt=0)


class PaymentItemResponseSchema(BaseModel):
    id: int = Field(gt=0)
    order_item_id: int = Field(gt=0)
    price_at_payment: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

    model_config = {
        "from_attributes": True
    }

    @field_validator("price_at_payment")
    @classmethod
    def validate_price_at_payment(cls, value: Decimal) -> Decimal:
        return payments_validators.validate_price_at_payment(value)


class PaymentResponseSchema(BaseModel):
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    created_at: datetime
    status: PaymentStatusEnum
    amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    currency: Literal["usd", "eur"] = "usd"
    external_payment_id: str | None = Field(max_length=255)
    items: list[PaymentItemResponseSchema]

    model_config = {
        "from_attributes": True
    }

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        return payments_validators.validate_payment_amount(value)


class PaymentListQuerySchema(PaginationQuerySchema):
    page: int = Field(default=1, ge=1, le=1_000_000)


class AdminPaymentListQuerySchema(AdminTransactionListQuerySchema):
    page: int = Field(default=1, ge=1, le=1_000_000)
    user_id: int | None = Field(default=None, gt=0, le=2**31 - 1)
    status: PaymentStatusEnum | None = None


class PaymentListResponseSchema(PaginationResponseSchema):
    items: list[PaymentResponseSchema]


class PurchasedMovieListResponseSchema(PaginationResponseSchema):
    items: list[MovieListItemResponseSchema]

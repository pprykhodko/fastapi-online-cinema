from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from src.database.models.orders import OrderStatusEnum
from src.database.validators import orders as orders_validators
from src.schemas.pagination import PaginationResponseSchema
from src.schemas.queries import (
    AdminTransactionListQuerySchema, PaginationQuerySchema,
)


class OrderMovieResponseSchema(BaseModel):
    id: int = Field(gt=0)
    name: str
    year: int

    model_config = {
        "from_attributes": True
    }


class OrderItemResponseSchema(BaseModel):
    id: int = Field(gt=0)
    movie: OrderMovieResponseSchema
    price_at_order: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

    model_config = {
        "from_attributes": True
    }

    @field_validator("price_at_order")
    @classmethod
    def validate_price_at_order(cls, value: Decimal) -> Decimal:
        return orders_validators.validate_price_at_order(value)


class OrderResponseSchema(BaseModel):
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Decimal | None = Field(
        ge=0, max_digits=10, decimal_places=2,
    )
    items: list[OrderItemResponseSchema]

    model_config = {
        "from_attributes": True
    }

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, value: Decimal | None) -> Decimal | None:
        return orders_validators.validate_total_amount(value)


class OrderListQuerySchema(PaginationQuerySchema):
    pass


class AdminOrderListQuerySchema(AdminTransactionListQuerySchema):
    status: OrderStatusEnum | None = None


class OrderListResponseSchema(PaginationResponseSchema):
    items: list[OrderResponseSchema]

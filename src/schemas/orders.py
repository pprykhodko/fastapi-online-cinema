from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from src.database.models.orders import OrderStatusEnum
from src.database.validators import orders as orders_validators


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


class OrderListQuerySchema(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=10, ge=1, le=100)

    model_config = {
        "extra": "forbid"
    }


class AdminOrderListQuerySchema(OrderListQuerySchema):
    user_id: int | None = Field(default=None, gt=0)
    status: OrderStatusEnum | None = None
    date_from: date | None = None
    date_to: date | None = None

    @field_validator("date_to")
    @classmethod
    def validate_date_range(
        cls, value: date | None, info: ValidationInfo,
    ) -> date | None:
        date_from = info.data.get("date_from")
        if value is not None and date_from is not None and value < date_from:
            raise ValueError("date_to must not be earlier than date_from.")
        return value


class OrderListResponseSchema(BaseModel):
    items: list[OrderResponseSchema]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

from datetime import date

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class PaginationQuerySchema(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=10, ge=1, le=100)

    model_config = {
        "extra": "forbid"
    }


class PaginationResponseSchema(BaseModel):
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)


class AdminTransactionListQuerySchema(PaginationQuerySchema):
    user_id: int | None = Field(default=None, gt=0)
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

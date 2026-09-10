from pydantic import BaseModel, Field

from src.schemas.movies import (
    BaseMovieIdRequestSchema, BaseMovieItemResponseSchema,
)


class CartItemCreateRequestSchema(BaseMovieIdRequestSchema):
    pass


class CartItemResponseSchema(BaseMovieItemResponseSchema):
    pass


class CartResponseSchema(BaseModel):
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    items: list[CartItemResponseSchema]

    model_config = {
        "from_attributes": True
    }

from datetime import datetime

from pydantic import BaseModel, Field

from src.schemas.movies import (
    MovieListItemResponseSchema, MovieListQuerySchema,
)


class MovieFavoriteCreateRequestSchema(BaseModel):
    movie_id: int = Field(gt=0, strict=True)

    model_config = {
        "extra": "forbid"
    }


class MovieFavoriteResponseSchema(BaseModel):
    id: int = Field(gt=0)
    movie: MovieListItemResponseSchema
    added_at: datetime

    model_config = {
        "from_attributes": True
    }


class MovieFavoriteListQuerySchema(MovieListQuerySchema):
    pass


class MovieFavoriteListResponseSchema(BaseModel):
    items: list[MovieFavoriteResponseSchema]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

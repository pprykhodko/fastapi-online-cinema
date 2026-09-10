from pydantic import BaseModel, Field

from src.schemas.movies import (
    BaseMovieIdRequestSchema,
    BaseMovieItemResponseSchema,
    MovieListQuerySchema,
)


class MovieFavoriteCreateRequestSchema(BaseMovieIdRequestSchema):
    pass


class MovieFavoriteResponseSchema(BaseMovieItemResponseSchema):
    pass


class MovieFavoriteListQuerySchema(MovieListQuerySchema):
    pass


class MovieFavoriteListResponseSchema(BaseModel):
    items: list[MovieFavoriteResponseSchema]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

from src.schemas.movies import (
    BaseMovieIdRequestSchema,
    BaseMovieItemResponseSchema,
    MovieListQuerySchema,
)
from src.schemas.pagination import PaginationResponseSchema


class MovieFavoriteCreateRequestSchema(BaseMovieIdRequestSchema):
    pass


class MovieFavoriteResponseSchema(BaseMovieItemResponseSchema):
    pass


class MovieFavoriteListQuerySchema(MovieListQuerySchema):
    pass


class MovieFavoriteListResponseSchema(PaginationResponseSchema):
    items: list[MovieFavoriteResponseSchema]

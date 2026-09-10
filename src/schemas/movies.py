from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.database.validators import movies as movies_validators
from src.database.validators.money import validate_money
from src.schemas.pagination import PaginationResponseSchema
from src.schemas.queries import PaginationQuerySchema


class BaseMovieIdRequestSchema(BaseModel):
    movie_id: int = Field(gt=0, strict=True)

    model_config = {
        "extra": "forbid"
    }


class BaseNameRequestSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    model_config = {
        "extra": "forbid"
    }

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return movies_validators.validate_name(value)


class GenreCreateRequestSchema(BaseNameRequestSchema):
    pass


class GenreUpdateRequestSchema(GenreCreateRequestSchema):
    pass


class StarCreateRequestSchema(BaseNameRequestSchema):
    pass


class StarUpdateRequestSchema(StarCreateRequestSchema):
    pass


class NamedEntityResponseSchema(BaseModel):
    id: int = Field(gt=0)
    name: str

    model_config = {
        "from_attributes": True
    }


class GenreResponseSchema(NamedEntityResponseSchema):
    pass


class GenreWithMovieCountResponseSchema(GenreResponseSchema):
    movie_count: int = Field(ge=0)


class StarResponseSchema(NamedEntityResponseSchema):
    pass


class DirectorResponseSchema(NamedEntityResponseSchema):
    pass


class CertificationResponseSchema(NamedEntityResponseSchema):
    pass


class BaseMovieSchema(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    year: int = Field(strict=True)
    time: int = Field(gt=0, strict=True)
    imdb: float = Field(ge=0, le=10, allow_inf_nan=False)
    votes: int = Field(ge=0, strict=True)
    description: str
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    meta_score: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False,
    )
    gross: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return movies_validators.validate_name(value)

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: Decimal) -> Decimal:
        return validate_money(value, "price")


class MovieCreateRequestSchema(BaseMovieSchema):
    certification_id: int = Field(gt=0, strict=True)
    genre_ids: list[int] = Field(default_factory=list)
    star_ids: list[int] = Field(default_factory=list)
    director_ids: list[int] = Field(default_factory=list)

    model_config = {
        "extra": "forbid"
    }

    @field_validator(
        "genre_ids",
        "star_ids",
        "director_ids",
        mode="before"
    )
    @classmethod
    def validate_related_ids(cls, values: list[int]) -> list[int]:
        if not isinstance(values, list):
            raise ValueError("Related IDs must be a list.")
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("Related IDs must be integers.")
            if value <= 0:
                raise ValueError("Related IDs must be positive.")
        if len(values) != len(set(values)):
            raise ValueError("Related IDs must not contain duplicates.")
        return values


class MovieUpdateRequestSchema(MovieCreateRequestSchema):
    pass


class MovieListItemResponseSchema(BaseModel):
    id: int = Field(gt=0)
    name: str
    year: int
    time: int
    imdb: float
    price: Decimal
    genres: list[GenreResponseSchema]

    model_config = {
        "from_attributes": True
    }


class BaseMovieItemResponseSchema(BaseModel):
    id: int = Field(gt=0)
    movie: MovieListItemResponseSchema
    added_at: datetime

    model_config = {
        "from_attributes": True
    }


class MovieDetailResponseSchema(BaseMovieSchema):
    id: int = Field(gt=0)
    uuid: UUID
    certification: CertificationResponseSchema
    genres: list[GenreResponseSchema]
    stars: list[StarResponseSchema]
    directors: list[DirectorResponseSchema]

    model_config = {
        "from_attributes": True
    }


class MovieListQuerySchema(PaginationQuerySchema):
    year: int | None = None
    min_imdb: float | None = Field(
        default=None, ge=0, le=10, allow_inf_nan=False,
    )
    genre_id: int | None = Field(default=None, gt=0)
    search: str | None = Field(default=None, min_length=1)
    sort_by: Literal["price", "year", "popularity"] = "year"
    sort_order: Literal["asc", "desc"] = "desc"

    @field_validator("search")
    @classmethod
    def validate_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return movies_validators.validate_name(value)


class MovieListResponseSchema(PaginationResponseSchema):
    items: list[MovieListItemResponseSchema]

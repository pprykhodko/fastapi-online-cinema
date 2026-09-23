from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.database.models.reactions import MovieReactionEnum
from src.database.validators.comments import validate_comment_content
from src.database.validators.ratings import validate_user_rating
from src.schemas.common import PaginationQuerySchema, PaginationResponseSchema
from src.schemas.movies import (
    BaseMovieIdRequestSchema,
    BaseMovieItemResponseSchema,
    MovieListQuerySchema,
)


class MovieCommentCreateRequestSchema(BaseModel):
    content: str = Field(min_length=1)
    parent_id: int | None = Field(
        default=None, gt=0, le=2**31 - 1, strict=True
    )

    model_config = {
        "extra": "forbid"
    }

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return validate_comment_content(value)


class MovieCommentResponseSchema(BaseModel):
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    movie_id: int = Field(gt=0)
    parent_id: int | None
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class MovieCommentListQuerySchema(PaginationQuerySchema):
    page: int = Field(default=1, ge=1, le=2**31 - 1)


class MovieCommentListResponseSchema(PaginationResponseSchema):
    items: list[MovieCommentResponseSchema]


class CommentLikeResponseSchema(BaseModel):
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    comment_id: int = Field(gt=0)
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class MovieReactionRequestSchema(BaseModel):
    reaction: MovieReactionEnum

    model_config = {
        "extra": "forbid"
    }


class MovieReactionResponseSchema(BaseModel):
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    movie_id: int = Field(gt=0)
    reaction: MovieReactionEnum
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class MovieRatingRequestSchema(BaseModel):
    score: int = Field(ge=1, le=10, strict=True)

    model_config = {
        "extra": "forbid"
    }

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: int) -> int:
        return validate_user_rating(value)


class MovieRatingResponseSchema(BaseModel):
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    movie_id: int = Field(gt=0)
    score: int = Field(ge=1, le=10)
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class MovieFavoriteCreateRequestSchema(BaseMovieIdRequestSchema):
    movie_id: int = Field(gt=0, le=2**31 - 1, strict=True)


class MovieFavoriteResponseSchema(BaseMovieItemResponseSchema):
    pass


class MovieFavoriteListQuerySchema(MovieListQuerySchema):
    pass


class MovieFavoriteListResponseSchema(PaginationResponseSchema):
    items: list[MovieFavoriteResponseSchema]

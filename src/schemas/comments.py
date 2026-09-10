from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.database.validators.comments import validate_comment_content
from src.schemas.pagination import PaginationResponseSchema
from src.schemas.queries import PaginationQuerySchema


class MovieCommentCreateRequestSchema(BaseModel):
    content: str = Field(min_length=1)
    parent_id: int | None = Field(default=None, gt=0, strict=True)

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
    pass


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

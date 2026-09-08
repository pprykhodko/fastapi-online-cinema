from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.database.validators.ratings import validate_user_rating


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

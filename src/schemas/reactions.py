from datetime import datetime

from pydantic import BaseModel, Field

from src.database.models.reactions import MovieReactionEnum


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

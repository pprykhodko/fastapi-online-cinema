from pydantic import BaseModel, Field


class PaginationResponseSchema(BaseModel):
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

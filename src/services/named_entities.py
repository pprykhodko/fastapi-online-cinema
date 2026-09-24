from typing import Generic, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

from src.services.database_errors import database_errors


ResponseSchema = TypeVar("ResponseSchema", bound=BaseModel)


class NamedEntityService(Generic[ResponseSchema]):
    """Shared writes for name-only reference entities"""

    entity_name: str
    response_schema: type[ResponseSchema]
    delete_conflict_detail: str | None = None

    def __init__(self, repository):
        self.repository = repository

    async def save(self, entity) -> ResponseSchema:
        async with database_errors(
                self.repository,
                detail=f"The {self.entity_name} could not be saved",
                conflict_detail=f"A {self.entity_name} with this name already exists"
        ):
            await self.repository.save(entity)
            response = self.response_schema.model_validate(entity)
            await self.repository.commit()

        return response

    async def delete(self, entity_id: int) -> None:
        async with database_errors(
                self.repository,
                detail=f"The {self.entity_name} could not be deleted",
                conflict_detail=self.delete_conflict_detail
        ):
            if not await self.repository.delete(entity_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{self.entity_name.capitalize()} not found"
                )

            await self.repository.commit()

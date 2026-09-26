from fastapi import HTTPException, status

from src.services.named_entities import NamedEntityService
from src.services.database_errors import database_errors
from src.database.models import DirectorModel
from src.repositories.directors import DirectorRepository
from src.schemas.movies import (
    DirectorCreateRequestSchema,
    DirectorResponseSchema,
    DirectorUpdateRequestSchema
)


class DirectorService(NamedEntityService[DirectorResponseSchema]):
    entity_name = "director"
    response_schema = DirectorResponseSchema

    def __init__(self, repository: DirectorRepository):
        super().__init__(repository)

    async def list_directors(self) -> list[DirectorResponseSchema]:
        async with database_errors(
                self.repository,
                detail="Directors are temporarily unavailable"
        ):
            directors = await self.repository.list_directors()

        return [
            DirectorResponseSchema.model_validate(director) for director in directors
        ]

    async def get_director(self, director_id: int) -> DirectorModel:
        async with database_errors(
                self.repository,
                detail="Directors are temporarily unavailable"
        ):
            director = await self.repository.get_director(director_id)

        if director is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Director not found"
            )

        return director

    async def create_director(
            self,
            data: DirectorCreateRequestSchema
    ) -> DirectorResponseSchema:
        return await self.save(DirectorModel(name=data.name))

    async def update_director(
            self,
            director_id: int,
            data: DirectorUpdateRequestSchema
    ) -> DirectorResponseSchema:
        director = await self.get_director(director_id)
        director.name = data.name

        return await self.save(director)

    async def delete_director(self, director_id: int) -> None:
        await self.delete(director_id)

from fastapi import HTTPException, status

from src.services.named_entities import NamedEntityService
from src.services.database_errors import database_errors
from src.database.models import StarModel
from src.repositories.stars import StarRepository
from src.schemas.movies import (
    StarCreateRequestSchema,
    StarResponseSchema,
    StarUpdateRequestSchema
)


class StarService(NamedEntityService[StarResponseSchema]):
    entity_name = "star"
    response_schema = StarResponseSchema

    def __init__(self, repository: StarRepository):
        super().__init__(repository)

    async def list_stars(self) -> list[StarResponseSchema]:
        async with database_errors(
                self.repository,
                detail="Actors are temporarily unavailable"
        ):
            stars = await self.repository.list_stars()

        return [StarResponseSchema.model_validate(star) for star in stars]

    async def get_star(self, star_id: int) -> StarModel:
        async with database_errors(
                self.repository,
                detail="Stars are temporarily unavailable"
        ):
            star = await self.repository.get_star(star_id)

        if star is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Star not found"
            )

        return star

    async def create_star(self, data: StarCreateRequestSchema) -> StarResponseSchema:
        return await self.save(StarModel(name=data.name))

    async def update_star(
            self,
            star_id: int,
            data: StarUpdateRequestSchema
    ) -> StarResponseSchema:
        star = await self.get_star(star_id)
        star.name = data.name

        return await self.save(star)

    async def delete_star(self, star_id: int) -> None:
        await self.delete(star_id)

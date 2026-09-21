from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import StarModel
from src.repositories.stars import StarRepository
from src.schemas.movies import (
    StarCreateRequestSchema, StarResponseSchema, StarUpdateRequestSchema,
)


class StarService:
    def __init__(self, repository: StarRepository):
        self.repository = repository

    async def list_stars(self) -> list[StarResponseSchema]:
        try:
            stars = await self.repository.list_stars()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Actors are temporarily unavailable.",
            ) from error

        return [StarResponseSchema.model_validate(star) for star in stars]

    async def get_star(self, star_id: int) -> StarModel:
        try:
            star = await self.repository.get_star(star_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Stars are temporarily unavailable.",
            ) from error

        if star is None:
            raise HTTPException(404, "Star not found.")

        return star

    async def save(self, star: StarModel) -> StarResponseSchema:
        try:
            await self.repository.save(star)

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "A star with this name already exists.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The star could not be saved.",
            ) from error

        return StarResponseSchema.model_validate(star)

    async def create_star(
        self, data: StarCreateRequestSchema,
    ) -> StarResponseSchema:
        return await self.save(StarModel(name=data.name))

    async def update_star(
        self, star_id: int, data: StarUpdateRequestSchema,
    ) -> StarResponseSchema:
        star = await self.get_star(star_id)
        star.name = data.name

        return await self.save(star)

    async def delete_star(self, star_id: int) -> None:
        try:
            deleted = await self.repository.delete(star_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The star could not be deleted.",
            ) from error

        if not deleted:
            raise HTTPException(404, "Star not found.")

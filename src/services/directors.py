from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import DirectorModel
from src.repositories.directors import DirectorRepository
from src.schemas.movies import (
    DirectorCreateRequestSchema, DirectorResponseSchema,
    DirectorUpdateRequestSchema,
)


class DirectorService:
    def __init__(self, repository: DirectorRepository):
        self.repository = repository

    async def list_directors(self) -> list[DirectorResponseSchema]:
        try:
            directors = await self.repository.list_directors()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Directors are temporarily unavailable.",
            ) from error

        return [
            DirectorResponseSchema.model_validate(director)
            for director in directors
        ]

    async def get_director(self, director_id: int) -> DirectorModel:
        try:
            director = await self.repository.get_director(director_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Directors are temporarily unavailable.",
            ) from error

        if director is None:
            raise HTTPException(404, "Director not found.")

        return director

    async def save(self, director: DirectorModel) -> DirectorResponseSchema:
        try:
            await self.repository.save(director)

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "A director with this name already exists.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The director could not be saved.",
            ) from error

        return DirectorResponseSchema.model_validate(director)

    async def create_director(
        self, data: DirectorCreateRequestSchema,
    ) -> DirectorResponseSchema:
        return await self.save(DirectorModel(name=data.name))

    async def update_director(
        self, director_id: int, data: DirectorUpdateRequestSchema,
    ) -> DirectorResponseSchema:
        director = await self.get_director(director_id)
        director.name = data.name

        return await self.save(director)

    async def delete_director(self, director_id: int) -> None:
        try:
            deleted = await self.repository.delete(director_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The director could not be deleted.",
            ) from error

        if not deleted:
            raise HTTPException(404, "Director not found.")

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import GenreModel
from src.repositories.genres import GenreRepository
from src.schemas.movies import (
    GenreCreateRequestSchema, GenreResponseSchema, GenreUpdateRequestSchema,
    GenreWithMovieCountResponseSchema,
)


class GenreService:
    def __init__(self, repository: GenreRepository):
        self.repository = repository

    async def list_genres(self) -> list[GenreWithMovieCountResponseSchema]:
        try:
            rows = await self.repository.list_genres()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Genres are temporarily unavailable.",
            ) from error

        return [
            GenreWithMovieCountResponseSchema(
                id=genre.id, name=genre.name, movie_count=count,
            )
            for genre, count in rows
        ]

    async def get_genre(self, genre_id: int) -> GenreModel:
        try:
            genre = await self.repository.get_genre(genre_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Genres are temporarily unavailable.",
            ) from error

        if genre is None:
            raise HTTPException(404, "Genre not found.")

        return genre

    async def save(self, genre: GenreModel) -> GenreResponseSchema:
        try:
            await self.repository.save(genre)

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "A genre with this name already exists.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The genre could not be saved.",
            ) from error

        return GenreResponseSchema.model_validate(genre)

    async def create_genre(
        self, data: GenreCreateRequestSchema,
    ) -> GenreResponseSchema:
        return await self.save(GenreModel(name=data.name))

    async def update_genre(
        self, genre_id: int, data: GenreUpdateRequestSchema,
    ) -> GenreResponseSchema:
        genre = await self.get_genre(genre_id)
        genre.name = data.name

        return await self.save(genre)

    async def delete_genre(self, genre_id: int) -> None:
        try:
            deleted = await self.repository.delete(genre_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The genre could not be deleted.",
            ) from error

        if not deleted:
            raise HTTPException(404, "Genre not found.")

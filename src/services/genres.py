from fastapi import HTTPException, status

from src.services.named_entities import NamedEntityService
from src.services.database_errors import database_errors
from src.database.models import GenreModel
from src.repositories.genres import GenreRepository
from src.schemas.movies import (
    GenreCreateRequestSchema,
    GenreResponseSchema,
    GenreUpdateRequestSchema,
    GenreWithMovieCountResponseSchema
)


class GenreService(NamedEntityService[GenreResponseSchema]):
    entity_name = "genre"
    response_schema = GenreResponseSchema

    def __init__(self, repository: GenreRepository):
        super().__init__(repository)

    async def list_genres(self) -> list[GenreWithMovieCountResponseSchema]:
        async with database_errors(
                self.repository,
                detail="Genres are temporarily unavailable"
        ):
            rows = await self.repository.list_genres()

        return [
            GenreWithMovieCountResponseSchema(
                id=genre.id,
                name=genre.name,
                movie_count=count
            ) for genre, count in rows
        ]

    async def get_genre(self, genre_id: int) -> GenreModel:
        async with database_errors(
                self.repository,
                detail="Genres are temporarily unavailable"
        ):
            genre = await self.repository.get_genre(genre_id)

        if genre is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Genre not found"
            )

        return genre

    async def create_genre(self, data: GenreCreateRequestSchema) -> GenreResponseSchema:
        return await self.save(GenreModel(name=data.name))

    async def update_genre(
            self,
            genre_id: int,
            data: GenreUpdateRequestSchema
    ) -> GenreResponseSchema:
        genre = await self.get_genre(genre_id)
        genre.name = data.name

        return await self.save(genre)

    async def delete_genre(self, genre_id: int) -> None:
        await self.delete(genre_id)

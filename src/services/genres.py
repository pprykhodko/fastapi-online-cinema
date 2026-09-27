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
        """
        Initialize GenreService with its required dependencies.

        Args:
            repository (GenreRepository): Repository used for database operations and
                the shared transaction.
        """
        super().__init__(repository)

    async def list_genres(self) -> list[GenreWithMovieCountResponseSchema]:
        """
        List genres with the count of non-deleted movies in each.

        Returns:
            list[GenreWithMovieCountResponseSchema]: Genre IDs, names and non-deleted
                movie counts.

        Raises:
            HTTPException: The requested data cannot be loaded from the database.
        """
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
        """
        Look up the genre by its ID.

        Args:
            genre_id (int): ID of the genre.

        Returns:
            GenreModel: Requested database record(s).

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
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
        """
        Create a genre with the validated unique name.

        Args:
            data (GenreCreateRequestSchema): Validated name for the reference record.

        Returns:
            GenreResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        return await self.save(GenreModel(name=data.name))

    async def update_genre(
            self,
            genre_id: int,
            data: GenreUpdateRequestSchema
    ) -> GenreResponseSchema:
        """
        Change the selected genre name, rejecting duplicate names.

        Args:
            genre_id (int): ID of the genre.
            data (GenreUpdateRequestSchema): Validated name for the reference record.

        Returns:
            GenreResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        genre = await self.get_genre(genre_id)
        genre.name = data.name

        return await self.save(genre)

    async def delete_genre(self, genre_id: int) -> None:
        """
        Delete the selected genre according to database relationship constraints.

        Args:
            genre_id (int): ID of the genre.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
        await self.delete(genre_id)

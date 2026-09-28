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
        """
        Initialize DirectorService with its required dependencies.

        Args:
            repository (DirectorRepository): Repository used for database operations and
                the shared transaction.
        """
        super().__init__(repository)

    async def list_directors(self) -> list[DirectorResponseSchema]:
        """
        List all director records in ID order.

        Returns:
            list[DirectorResponseSchema]: List of records with their IDs and names.

        Raises:
            HTTPException: The requested data cannot be loaded from the database.
        """
        async with database_errors(
                self.repository,
                detail="Directors are temporarily unavailable"
        ):
            directors = await self.repository.list_directors()

        return [
            DirectorResponseSchema.model_validate(director) for director in directors
        ]

    async def get_director(self, director_id: int) -> DirectorModel:
        """
        Look up the director by its ID.

        Args:
            director_id (int): ID of the director.

        Returns:
            DirectorModel: Requested database record(s).

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
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
        """
        Create a director with the validated unique name.

        Args:
            data (DirectorCreateRequestSchema): Validated name for the reference record.

        Returns:
            DirectorResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        return await self.save(DirectorModel(name=data.name))

    async def update_director(
            self,
            director_id: int,
            data: DirectorUpdateRequestSchema
    ) -> DirectorResponseSchema:
        """
        Change the selected director name, rejecting duplicate names.

        Args:
            director_id (int): ID of the director.
            data (DirectorUpdateRequestSchema): Validated name for the reference record.

        Returns:
            DirectorResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        director = await self.get_director(director_id)
        director.name = data.name

        return await self.save(director)

    async def delete_director(self, director_id: int) -> None:
        """
        Delete the selected director according to database relationship constraints.

        Args:
            director_id (int): ID of the director.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
        await self.delete(director_id)

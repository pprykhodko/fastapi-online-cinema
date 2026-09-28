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
        """
        Initialize StarService with its required dependencies.

        Args:
            repository (StarRepository): Repository used for database operations and the
                shared transaction.
        """
        super().__init__(repository)

    async def list_stars(self) -> list[StarResponseSchema]:
        """
        List all actor records in ID order.

        Returns:
            list[StarResponseSchema]: List of records with their IDs and names.

        Raises:
            HTTPException: The requested data cannot be loaded from the database.
        """
        async with database_errors(
                self.repository,
                detail="Actors are temporarily unavailable"
        ):
            stars = await self.repository.list_stars()

        return [StarResponseSchema.model_validate(star) for star in stars]

    async def get_star(self, star_id: int) -> StarModel:
        """
        Look up the actor by its ID.

        Args:
            star_id (int): ID of the actor.

        Returns:
            StarModel: Requested database record(s).

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
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
        """
        Create a actor with the validated unique name.

        Args:
            data (StarCreateRequestSchema): Validated name for the reference record.

        Returns:
            StarResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        return await self.save(StarModel(name=data.name))

    async def update_star(
            self,
            star_id: int,
            data: StarUpdateRequestSchema
    ) -> StarResponseSchema:
        """
        Change the selected actor name, rejecting duplicate names.

        Args:
            star_id (int): ID of the actor.
            data (StarUpdateRequestSchema): Validated name for the reference record.

        Returns:
            StarResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        star = await self.get_star(star_id)
        star.name = data.name

        return await self.save(star)

    async def delete_star(self, star_id: int) -> None:
        """
        Delete the selected actor according to database relationship constraints.

        Args:
            star_id (int): ID of the actor.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
        await self.delete(star_id)

from fastapi import HTTPException, status

from src.services.named_entities import NamedEntityService
from src.services.database_errors import database_errors
from src.database.models import CertificationModel
from src.repositories.certifications import CertificationRepository
from src.schemas.movies import (
    CertificationCreateRequestSchema, CertificationResponseSchema,
    CertificationUpdateRequestSchema,
)


class CertificationService(NamedEntityService[CertificationResponseSchema]):
    entity_name = "certification"
    response_schema = CertificationResponseSchema
    delete_conflict_detail = "This certification is used by a movie"

    def __init__(self, repository: CertificationRepository):
        """
        Initialize CertificationService with its required dependencies.

        Args:
            repository (CertificationRepository): Repository used for database
                operations and the shared transaction.
        """
        super().__init__(repository)

    async def list_certifications(self) -> list[CertificationResponseSchema]:
        """
        List all certification records in ID order.

        Returns:
            list[CertificationResponseSchema]: List of records with their IDs and names.

        Raises:
            HTTPException: The requested data cannot be loaded from the database.
        """
        async with database_errors(
                self.repository,
                detail="Certifications are temporarily unavailable"
        ):
            certifications = await self.repository.list_certifications()

        return [
            CertificationResponseSchema.model_validate(certification)
            for certification in certifications
        ]

    async def get_certification(self, certification_id: int) -> CertificationModel:
        """
        Look up the certification by its ID.

        Args:
            certification_id (int): ID of the movie certification.

        Returns:
            CertificationModel: Requested database record(s).

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
        async with database_errors(
                self.repository,
                detail="Certifications are temporarily unavailable"
        ):
            certification = await self.repository.get_certification(certification_id)

        if certification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Certification not found"
            )

        return certification

    async def create_certification(
            self,
            data: CertificationCreateRequestSchema
    ) -> CertificationResponseSchema:
        """
        Create a certification with the validated unique name.

        Args:
            data (CertificationCreateRequestSchema): Validated name for the reference
                record.

        Returns:
            CertificationResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        return await self.save(CertificationModel(name=data.name))

    async def update_certification(
            self,
            certification_id: int,
            data: CertificationUpdateRequestSchema
    ) -> CertificationResponseSchema:
        """
        Change the selected certification name, rejecting duplicate names.

        Args:
            certification_id (int): ID of the movie certification.
            data (CertificationUpdateRequestSchema): Validated name for the reference
                record.

        Returns:
            CertificationResponseSchema: Reference record ID and name.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        certification = await self.get_certification(certification_id)
        certification.name = data.name

        return await self.save(certification)

    async def delete_certification(self, certification_id: int) -> None:
        """
        Delete the selected certification according to database relationship
        constraints.

        Args:
            certification_id (int): ID of the movie certification.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
        await self.delete(certification_id)

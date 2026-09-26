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
        super().__init__(repository)

    async def list_certifications(self) -> list[CertificationResponseSchema]:
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
        return await self.save(CertificationModel(name=data.name))

    async def update_certification(
            self,
            certification_id: int,
            data: CertificationUpdateRequestSchema
    ) -> CertificationResponseSchema:
        certification = await self.get_certification(certification_id)
        certification.name = data.name

        return await self.save(certification)

    async def delete_certification(self, certification_id: int) -> None:
        await self.delete(certification_id)

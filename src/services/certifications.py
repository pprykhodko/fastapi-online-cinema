from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import CertificationModel
from src.repositories.certifications import CertificationRepository
from src.schemas.movies import (
    CertificationCreateRequestSchema, CertificationResponseSchema,
    CertificationUpdateRequestSchema,
)


class CertificationService:
    def __init__(self, repository: CertificationRepository):
        self.repository = repository

    async def list_certifications(self) -> list[CertificationResponseSchema]:
        try:
            certifications = await self.repository.list_certifications()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Certifications are temporarily unavailable.",
            ) from error

        return [
            CertificationResponseSchema.model_validate(certification)
            for certification in certifications
        ]

    async def get_certification(
        self, certification_id: int,
    ) -> CertificationModel:
        try:
            certification = await self.repository.get_certification(
                certification_id,
            )

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Certifications are temporarily unavailable.",
            ) from error

        if certification is None:
            raise HTTPException(404, "Certification not found.")

        return certification

    async def save(
        self, certification: CertificationModel,
    ) -> CertificationResponseSchema:
        try:
            await self.repository.save(certification)

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "A certification with this name already exists.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The certification could not be saved.",
            ) from error

        return CertificationResponseSchema.model_validate(certification)

    async def create_certification(
        self, data: CertificationCreateRequestSchema,
    ) -> CertificationResponseSchema:
        return await self.save(CertificationModel(name=data.name))

    async def update_certification(
        self, certification_id: int, data: CertificationUpdateRequestSchema,
    ) -> CertificationResponseSchema:
        certification = await self.get_certification(certification_id)
        certification.name = data.name

        return await self.save(certification)

    async def delete_certification(self, certification_id: int) -> None:
        try:
            deleted = await self.repository.delete(certification_id)

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "This certification is used by a movie.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The certification could not be deleted.",
            ) from error

        if not deleted:
            raise HTTPException(404, "Certification not found.")

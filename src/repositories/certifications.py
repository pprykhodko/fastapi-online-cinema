from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CertificationModel


class CertificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_certifications(self) -> list[CertificationModel]:
        certifications = await self.db.scalars(
            select(CertificationModel).order_by(CertificationModel.id)
        )

        return list(certifications.all())

    async def get_certification(
        self, certification_id: int,
    ) -> CertificationModel | None:
        return await self.db.get(CertificationModel, certification_id)

    async def save(self, certification: CertificationModel) -> None:
        self.db.add(certification)
        await self.db.commit()

    async def delete(self, certification_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(CertificationModel)
            .where(CertificationModel.id == certification_id)
            .returning(CertificationModel.id)
        )
        await self.db.commit()

        return deleted_id is not None

    async def rollback(self) -> None:
        await self.db.rollback()

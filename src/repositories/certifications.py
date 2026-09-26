from sqlalchemy import select

from src.repositories.base import NamedEntityRepository
from src.database.models import CertificationModel


class CertificationRepository(NamedEntityRepository[CertificationModel]):
    model = CertificationModel

    async def list_certifications(self) -> list[CertificationModel]:
        certifications = await self.db.scalars(
            select(CertificationModel)
            .order_by(CertificationModel.id)
        )

        return list(certifications.all())

    async def get_certification(
            self,
            certification_id: int
    ) -> CertificationModel | None:
        return await self.get_by_id(certification_id)

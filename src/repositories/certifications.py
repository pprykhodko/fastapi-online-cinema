from sqlalchemy import select

from src.repositories.base import NamedEntityRepository
from src.database.models import CertificationModel


class CertificationRepository(NamedEntityRepository[CertificationModel]):
    model = CertificationModel

    async def list_certifications(self) -> list[CertificationModel]:
        """
        List all certification records in ID order.

        The caller controls the transaction commit.

        Returns:
            list[CertificationModel]: Requested database record(s).
        """
        certifications = await self.db.scalars(
            select(CertificationModel)
            .order_by(CertificationModel.id)
        )

        return list(certifications.all())

    async def get_certification(
            self,
            certification_id: int
    ) -> CertificationModel | None:
        """
        Look up the certification by its ID.

        The caller controls the transaction commit.

        Args:
            certification_id (int): ID of the movie certification.

        Returns:
            CertificationModel | None: Matching database record(s), or None when allowed
                and not found.
        """
        return await self.get_by_id(certification_id)

from sqlalchemy import select

from src.repositories.base import NamedEntityRepository
from src.database.models import StarModel


class StarRepository(NamedEntityRepository[StarModel]):
    model = StarModel

    async def list_stars(self) -> list[StarModel]:
        """
        List all actor records in ID order.

        The caller controls the transaction commit.

        Returns:
            list[StarModel]: Requested database record(s).
        """
        stars = await self.db.scalars(select(StarModel).order_by(StarModel.id))

        return list(stars.all())

    async def get_star(self, star_id: int) -> StarModel | None:
        """
        Look up the actor by its ID.

        The caller controls the transaction commit.

        Args:
            star_id (int): ID of the actor.

        Returns:
            StarModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        return await self.get_by_id(star_id)

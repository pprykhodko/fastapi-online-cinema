from sqlalchemy import select

from src.repositories.base import NamedEntityRepository
from src.database.models import StarModel


class StarRepository(NamedEntityRepository[StarModel]):
    model = StarModel

    async def list_stars(self) -> list[StarModel]:
        stars = await self.db.scalars(select(StarModel).order_by(StarModel.id))

        return list(stars.all())

    async def get_star(self, star_id: int) -> StarModel | None:
        return await self.get_by_id(star_id)

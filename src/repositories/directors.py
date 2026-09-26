from sqlalchemy import select

from src.repositories.base import NamedEntityRepository
from src.database.models import DirectorModel


class DirectorRepository(NamedEntityRepository[DirectorModel]):
    model = DirectorModel

    async def list_directors(self) -> list[DirectorModel]:
        directors = await self.db.scalars(
            select(DirectorModel)
            .order_by(DirectorModel.id)
        )

        return list(directors.all())

    async def get_director(self, director_id: int) -> DirectorModel | None:
        return await self.get_by_id(director_id)

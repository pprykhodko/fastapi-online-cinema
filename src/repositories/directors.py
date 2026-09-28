from sqlalchemy import select

from src.repositories.base import NamedEntityRepository
from src.database.models import DirectorModel


class DirectorRepository(NamedEntityRepository[DirectorModel]):
    model = DirectorModel

    async def list_directors(self) -> list[DirectorModel]:
        """
        List all director records in ID order.

        The caller controls the transaction commit.

        Returns:
            list[DirectorModel]: Requested database record(s).
        """
        directors = await self.db.scalars(
            select(DirectorModel)
            .order_by(DirectorModel.id)
        )

        return list(directors.all())

    async def get_director(self, director_id: int) -> DirectorModel | None:
        """
        Look up the director by its ID.

        The caller controls the transaction commit.

        Args:
            director_id (int): ID of the director.

        Returns:
            DirectorModel | None: Matching database record(s), or None when allowed and
                not found.
        """
        return await self.get_by_id(director_id)

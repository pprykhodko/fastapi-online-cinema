from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import DirectorModel


class DirectorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_directors(self) -> list[DirectorModel]:
        directors = await self.db.scalars(
            select(DirectorModel).order_by(DirectorModel.id)
        )

        return list(directors.all())

    async def get_director(self, director_id: int) -> DirectorModel | None:
        return await self.db.get(DirectorModel, director_id)

    async def save(self, director: DirectorModel) -> None:
        self.db.add(director)
        await self.db.flush()

    async def delete(self, director_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(DirectorModel).where(DirectorModel.id == director_id)
            .returning(DirectorModel.id)
        )
        return deleted_id is not None

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import StarModel


class StarRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_stars(self) -> list[StarModel]:
        stars = await self.db.scalars(select(StarModel).order_by(StarModel.id))

        return list(stars.all())

    async def get_star(self, star_id: int) -> StarModel | None:
        return await self.db.get(StarModel, star_id)

    async def save(self, star: StarModel) -> None:
        self.db.add(star)
        await self.db.flush()

    async def delete(self, star_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(StarModel).where(StarModel.id == star_id)
            .returning(StarModel.id)
        )
        return deleted_id is not None

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

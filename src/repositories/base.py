from typing import Generic, TypeVar

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.base import Base


class BaseRepository:
    """Share a session; services explicitly choose commit or rollback"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()


ModelType = TypeVar("ModelType", bound=Base)


class NamedEntityRepository(BaseRepository, Generic[ModelType]):
    """Common writes for reference tables with a single integer ID"""

    model: type[ModelType]

    async def get_by_id(self, entity_id: int) -> ModelType | None:
        return await self.db.get(self.model, entity_id)

    async def save(self, entity: ModelType) -> None:
        self.db.add(entity)
        await self.db.flush()

    async def delete(self, entity_id: int) -> bool:
        id_column = self.model.__table__.c.id
        deleted_id = await self.db.scalar(
            delete(self.model)
            .where(id_column == entity_id)
            .returning(id_column)
        )

        return deleted_id is not None

from typing import Generic, TypeVar

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.base import Base


class BaseRepository:
    """Share a session; services explicitly choose commit or rollback"""

    def __init__(self, db: AsyncSession):
        """
        Initialize BaseRepository with its required dependencies.

        Args:
            db (AsyncSession): Shared asynchronous database session.
        """
        self.db = db

    async def commit(self) -> None:
        """
        Commit all pending changes in the shared database session.
        """
        await self.db.commit()

    async def rollback(self) -> None:
        """
        Roll back the current transaction in the shared database session.
        """
        await self.db.rollback()


ModelType = TypeVar("ModelType", bound=Base)


class NamedEntityRepository(BaseRepository, Generic[ModelType]):
    """Common writes for reference tables with a single integer ID"""

    model: type[ModelType]

    async def get_by_id(self, entity_id: int) -> ModelType | None:
        """
        Look up the record by primary key without applying an ownership check.

        The caller controls the transaction commit.

        Args:
            entity_id (int): Primary key of the reference record.

        Returns:
            ModelType | None: Matching record, or None if the ID does not exist.
        """
        return await self.db.get(self.model, entity_id)

    async def save(self, entity: ModelType) -> None:
        """
        Add and flush the supplied record without committing the shared transaction.

        Args:
            entity (ModelType): ORM record supplied for this database operation.
        """
        self.db.add(entity)
        await self.db.flush()

    async def delete(self, entity_id: int) -> bool:
        """
        Delete the matching record without committing and report whether it existed.

        Args:
            entity_id (int): Primary key of the reference record.

        Returns:
            bool: True if a matching record was deleted; otherwise False.
        """
        id_column = self.model.__table__.c.id
        deleted_id = await self.db.scalar(
            delete(self.model)
            .where(id_column == entity_id)
            .returning(id_column)
        )

        return deleted_id is not None

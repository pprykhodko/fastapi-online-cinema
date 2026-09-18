from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import UserModel, UserProfileModel


class ProfileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_profile(self, user_id: int) -> UserProfileModel | None:
        stmt = (
            select(UserProfileModel)
            .join(UserModel)
            .where(
                UserProfileModel.user_id == user_id,
                UserModel.is_active.is_(True),
            )
        )

        return await self.db.scalar(stmt)

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

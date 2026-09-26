from sqlalchemy import select

from src.repositories.base import BaseRepository
from src.database.models import UserModel, UserProfileModel


class ProfileRepository(BaseRepository):
    def add_profile(self, user_id: int) -> None:
        self.db.add(UserProfileModel(user_id=user_id))

    async def get_profile(self, user_id: int) -> UserProfileModel | None:
        stmt = (
            select(UserProfileModel)
            .join(UserModel)
            .where(UserProfileModel.user_id == user_id, UserModel.is_active.is_(True))
        )

        return await self.db.scalar(stmt)

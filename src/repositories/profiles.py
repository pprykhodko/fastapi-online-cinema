from sqlalchemy import select

from src.repositories.base import BaseRepository
from src.database.models import UserModel, UserProfileModel


class ProfileRepository(BaseRepository):
    def add_profile(self, user_id: int) -> None:
        """
        Stage an empty profile for the user without committing.

        Args:
            user_id (int): ID of the account whose data is being accessed.
        """
        self.db.add(UserProfileModel(user_id=user_id))

    async def get_profile(self, user_id: int) -> UserProfileModel | None:
        """
        Look up the profile by user ID.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            UserProfileModel | None: Matching database record(s), or None when allowed
                and not found.
        """
        stmt = (
            select(UserProfileModel)
            .join(UserModel)
            .where(UserProfileModel.user_id == user_id, UserModel.is_active.is_(True))
        )

        return await self.db.scalar(stmt)

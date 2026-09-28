from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.repositories.base import BaseRepository
from src.database.models import (
    UserGroupEnum,
    UserGroupModel,
    UserModel
)


class AccountRepository(BaseRepository):
    async def get_user_by_email(self, email: str) -> UserModel | None:
        """
        Look up an account by its stored normalized email address.

        The caller controls the transaction commit.

        Args:
            email (str): Email address of the account or message recipient.

        Returns:
            UserModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_active_email(self, user_id: int) -> str | None:
        """
        Return the email only when the selected account exists and is active.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            str | None: Account email, or None when no matching account exists.
        """
        return await self.db.scalar(
            select(UserModel.email)
            .where(UserModel.id == user_id, UserModel.is_active.is_(True))
        )

    async def get_user_by_id(self, user_id: int) -> UserModel | None:
        """
        Load an account and its group by user ID.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            UserModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        stmt = (
            select(UserModel)
            .options(joinedload(UserModel.group))
            .where(UserModel.id == user_id)
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_default_group(self) -> UserGroupModel | None:
        """
        Look up the USER group used during registration.

        The caller controls the transaction commit.

        Returns:
            UserGroupModel | None: Matching database record(s), or None when allowed and
                not found.
        """
        stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_group_by_name(self, name: UserGroupEnum) -> UserGroupModel | None:
        """
        Look up a user group by its enum name.

        The caller controls the transaction commit.

        Args:
            name (UserGroupEnum): User group enum to look up.

        Returns:
            UserGroupModel | None: Matching database record(s), or None when allowed and
                not found.
        """
        stmt = select(UserGroupModel).where(UserGroupModel.name == name)
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def add_user(self, user: UserModel) -> None:
        """
        Add and flush an account to assign its ID without committing.

        Args:
            user (UserModel): Account record to add or refresh.
        """
        self.db.add(user)
        await self.db.flush()

    async def refresh_user(self, user: UserModel) -> None:
        """
        Reload the account fields from the database.

        The caller controls the transaction commit.

        Args:
            user (UserModel): Account record to add or refresh.
        """
        await self.db.refresh(user)

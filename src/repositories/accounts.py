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
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_active_email(self, user_id: int) -> str | None:
        return await self.db.scalar(
            select(UserModel.email)
            .where(UserModel.id == user_id, UserModel.is_active.is_(True))
        )

    async def get_user_by_id(self, user_id: int) -> UserModel | None:
        stmt = (
            select(UserModel)
            .options(joinedload(UserModel.group))
            .where(UserModel.id == user_id)
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_default_group(self) -> UserGroupModel | None:
        stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_group_by_name(self, name: UserGroupEnum) -> UserGroupModel | None:
        stmt = select(UserGroupModel).where(UserGroupModel.name == name)
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def add_user(self, user: UserModel) -> None:
        self.db.add(user)
        await self.db.flush()

    async def refresh_user(self, user: UserModel) -> None:
        await self.db.refresh(user)

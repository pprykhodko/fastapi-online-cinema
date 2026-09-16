from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.database.models import (
    ActivationTokenModel, CartModel, RefreshTokenModel,
    UserGroupEnum, UserGroupModel, UserModel,
)


class AccountRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_user_by_id(self, user_id: int) -> UserModel | None:
        stmt = (
            select(UserModel)
            .options(joinedload(UserModel.group))
            .where(UserModel.id == user_id)
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_default_group(self) -> UserGroupModel | None:
        stmt = select(UserGroupModel).where(
            UserGroupModel.name == UserGroupEnum.USER,
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def add_user(self, user: UserModel) -> None:
        self.db.add(user)
        await self.db.flush()

    def add_cart(self, user_id: int) -> None:
        self.db.add(CartModel(user_id=user_id))

    def add_activation_token(self, token: ActivationTokenModel) -> None:
        self.db.add(token)

    def add_refresh_token(self, token: RefreshTokenModel) -> None:
        self.db.add(token)

    async def get_activation_token(
        self, token: str,
    ) -> ActivationTokenModel | None:
        stmt = (
            select(ActivationTokenModel)
            .where(ActivationTokenModel.token == token)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_user_activation_token(
        self, user_id: int,
    ) -> ActivationTokenModel | None:
        stmt = (
            select(ActivationTokenModel)
            .where(ActivationTokenModel.user_id == user_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def refresh_user(self, user: UserModel) -> None:
        await self.db.refresh(user)

    async def delete_activation_token(
        self, token: ActivationTokenModel,
    ) -> None:
        await self.db.delete(token)

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

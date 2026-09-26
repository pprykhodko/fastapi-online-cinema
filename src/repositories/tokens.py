from sqlalchemy import delete, select

from src.database.models import (
    ActivationTokenModel, PasswordResetTokenModel, RefreshTokenModel,
)
from src.repositories.base import BaseRepository


class TokenRepository(BaseRepository):
    def add_activation_token(self, token: ActivationTokenModel) -> None:
        self.db.add(token)

    def add_refresh_token(self, token: RefreshTokenModel) -> None:
        self.db.add(token)

    async def get_refresh_token(self, token: str) -> RefreshTokenModel | None:
        stmt = (
            select(RefreshTokenModel)
            .where(RefreshTokenModel.token == token)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def delete_refresh_token(self, token: RefreshTokenModel) -> None:
        await self.db.delete(token)

    async def delete_user_refresh_tokens(self, user_id: int) -> None:
        await self.db.execute(
            delete(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id)
        )

    def add_password_reset_token(self, token: PasswordResetTokenModel) -> None:
        self.db.add(token)

    async def get_password_reset_token(
            self,
            token_hash: str
    ) -> PasswordResetTokenModel | None:
        stmt = (
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.token == token_hash)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_user_password_reset_token(
            self,
            user_id: int
    ) -> PasswordResetTokenModel | None:
        stmt = (
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def delete_user_password_reset_tokens(self, user_id: int) -> None:
        await self.db.execute(
            delete(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
        )

    async def get_activation_token(self, token: str) -> ActivationTokenModel | None:
        stmt = (
            select(ActivationTokenModel)
            .where(ActivationTokenModel.token == token)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def get_user_activation_token(
            self,
            user_id: int
    ) -> ActivationTokenModel | None:
        stmt = (
            select(ActivationTokenModel)
            .where(ActivationTokenModel.user_id == user_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def delete_activation_token(self, token: ActivationTokenModel) -> None:
        await self.db.delete(token)

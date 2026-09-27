from sqlalchemy import delete, select

from src.database.models import (
    ActivationTokenModel, PasswordResetTokenModel, RefreshTokenModel,
)
from src.repositories.base import BaseRepository


class TokenRepository(BaseRepository):
    def add_activation_token(self, token: ActivationTokenModel) -> None:
        """
        Stage the token record in the shared session without flushing or committing.

        Args:
            token (ActivationTokenModel): Stored token record to add or delete.
        """
        self.db.add(token)

    def add_refresh_token(self, token: RefreshTokenModel) -> None:
        """
        Stage the token record in the shared session without flushing or committing.

        Args:
            token (RefreshTokenModel): Stored token record to add or delete.
        """
        self.db.add(token)

    async def get_refresh_token(self, token: str) -> RefreshTokenModel | None:
        """
        Look up the token record and request a row lock; validity is checked by the
        service.

        The caller controls the transaction commit.

        Args:
            token (str): Plaintext token supplied by the caller; never log this value.

        Returns:
            RefreshTokenModel | None: Matching database record(s), or None when allowed
                and not found.
        """
        stmt = (
            select(RefreshTokenModel)
            .where(RefreshTokenModel.token == token)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def delete_refresh_token(self, token: RefreshTokenModel) -> None:
        """
        Delete the selected token records without committing the shared transaction.

        Args:
            token (RefreshTokenModel): Stored token record to add or delete.
        """
        await self.db.delete(token)

    async def delete_user_refresh_tokens(self, user_id: int) -> None:
        """
        Delete the selected token records without committing the shared transaction.

        Args:
            user_id (int): ID of the account whose data is being accessed.
        """
        await self.db.execute(
            delete(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id)
        )

    def add_password_reset_token(self, token: PasswordResetTokenModel) -> None:
        """
        Stage the token record in the shared session without flushing or committing.

        Args:
            token (PasswordResetTokenModel): Stored token record to add or delete.
        """
        self.db.add(token)

    async def get_password_reset_token(
            self,
            token_hash: str
    ) -> PasswordResetTokenModel | None:
        """
        Look up the token record and request a row lock; validity is checked by the
        service.

        The caller controls the transaction commit.

        Args:
            token_hash (str): SHA-256 hash of the reset token, not its plaintext.

        Returns:
            PasswordResetTokenModel | None: Matching database record(s), or None when
                allowed and not found.
        """
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
        """
        Look up the token record and request a row lock; validity is checked by the
        service.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            PasswordResetTokenModel | None: Matching database record(s), or None when
                allowed and not found.
        """
        stmt = (
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def delete_user_password_reset_tokens(self, user_id: int) -> None:
        """
        Delete the selected token records without committing the shared transaction.

        Args:
            user_id (int): ID of the account whose data is being accessed.
        """
        await self.db.execute(
            delete(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
        )

    async def get_activation_token(self, token: str) -> ActivationTokenModel | None:
        """
        Look up the token record and request a row lock; validity is checked by the
        service.

        The caller controls the transaction commit.

        Args:
            token (str): Plaintext token supplied by the caller; never log this value.

        Returns:
            ActivationTokenModel | None: Matching database record(s), or None when
                allowed and not found.
        """
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
        """
        Look up the token record and request a row lock; validity is checked by the
        service.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            ActivationTokenModel | None: Matching database record(s), or None when
                allowed and not found.
        """
        stmt = (
            select(ActivationTokenModel)
            .where(ActivationTokenModel.user_id == user_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)

        return result.scalars().first()

    async def delete_activation_token(self, token: ActivationTokenModel) -> None:
        """
        Delete the selected token records without committing the shared transaction.

        Args:
            token (ActivationTokenModel): Stored token record to add or delete.
        """
        await self.db.delete(token)

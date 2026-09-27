from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.services.database_errors import database_errors
from src.database.models import (
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserModel
)
from src.notifications.queue import EmailQueueError, EmailQueue
from src.repositories.accounts import AccountRepository
from src.repositories.cart import CartRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.tokens import TokenRepository
from src.schemas.accounts import (
    AccessTokenResponseSchema,
    AccountActivationRequestSchema,
    AccountMessageResponseSchema,
    ActivationResendRequestSchema,
    LogoutRequestSchema,
    PasswordChangeRequestSchema,
    PasswordResetConfirmRequestSchema,
    PasswordResetRequestSchema,
    TokenPairResponseSchema,
    TokenRefreshRequestSchema,
    UserGroupUpdateRequestSchema,
    UserLoginRequestSchema,
    UserRegistrationRequestSchema,
    UserResponseSchema
)
from src.security.tokens import InvalidTokenError, JWTAuthManager
from src.security.passwords import hash_password
from src.security.utils import generate_secure_token, hash_reset_token


class AccountService:
    def __init__(
            self,
            repository: AccountRepository,
            email_queue: EmailQueue,
            token_repository: TokenRepository,
            profile_repository: ProfileRepository,
            cart_repository: CartRepository,
    ):
        """
        Initialize AccountService with its required dependencies.

        Args:
            repository (AccountRepository): Repository used for database operations and
                the shared transaction.
            email_queue (EmailQueue): Publisher used to send email tasks to Celery.
            token_repository (TokenRepository): Repository for token data using the
                shared session.
            profile_repository (ProfileRepository): Repository for profile data using
                the shared session.
            cart_repository (CartRepository): Repository for cart data using the shared
                session.
        """
        self.repository = repository
        self.email_queue = email_queue
        self.token_repository = token_repository
        self.profile_repository = profile_repository
        self.cart_repository = cart_repository

    @staticmethod
    def is_token_expired(expires_at: datetime, now: datetime) -> bool:
        """
        Compare the expiration with the current time, treating naive expiration dates as
        UTC.

        Args:
            expires_at (datetime): Expiration time; naive datetime values are
                interpreted as UTC.
            now (datetime): Current time used for the expiration check.

        Returns:
            bool: True when the token expiration is at or before now.
        """
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return expires_at <= now

    async def register_user(
            self,
            user_data: UserRegistrationRequestSchema
    ) -> UserResponseSchema:
        """
        Create an inactive account, profile, cart and activation token, then queue an
        email.

        Steps:
        - Check email uniqueness and find the default USER group.
        - Create the account, profile, cart and activation token in one transaction.
        - Commit before queueing the activation email.

        Args:
            user_data (UserRegistrationRequestSchema): Email and strong password for the
                new account.

        Returns:
            UserResponseSchema: Public account fields, activation state and group; no
                password hash.

        Raises:
            HTTPException: Email already exists, the USER group is missing, saving fails
                or email queueing fails.
        """
        email = str(user_data.email)
        try:
            existing_user = await self.repository.get_user_by_email(email)

            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this email already exists"
                )

            user_group = await self.repository.get_default_group()

            if not user_group:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Registration is temporarily unavailable"
                )

            new_user = await run_in_threadpool(
                UserModel.create,
                email=email,
                raw_password=user_data.password,
                group_id=user_group.id
            )
            new_user.is_active = False
            new_user.group = user_group
            await self.repository.add_user(new_user)
            self.profile_repository.add_profile(new_user.id)
            self.cart_repository.add_cart(new_user.id)
            activation_token = ActivationTokenModel(user_id=new_user.id)
            self.token_repository.add_activation_token(activation_token)
            await self.repository.commit()

        except IntegrityError:
            await self.repository.rollback()
            existing_user = await self.repository.get_user_by_email(email)

            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this email already exists"
                )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The account could not be saved"
            )

        except SQLAlchemyError:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration is temporarily unavailable"
            )

        try:
            await self.email_queue.send_activation_email(
                new_user.email,
                activation_token.token,
                activation_token.expires_at
            )

        except EmailQueueError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account created, but the activation email could not be queued. "
                       "Please request the activation email again."
            )

        return UserResponseSchema.model_validate(new_user)

    async def activate_account(
            self,
            activation_data: AccountActivationRequestSchema
    ) -> AccountMessageResponseSchema:
        """
        Activate an account with a valid token and queue a confirmation email.

        Args:
            activation_data (AccountActivationRequestSchema): One-use token from the
                activation email.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.

        Raises:
            HTTPException: The activation token is invalid/expired, the account is
                active or the database fails.
        """
        async with database_errors(
                self.repository,
                detail="Account activation is temporarily unavailable"
        ):
            activation_token = await self.token_repository.get_activation_token(
                activation_data.token
            )

            if not activation_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The activation token is invalid or expired"
                )

            if self.is_token_expired(
                    activation_token.expires_at,
                    datetime.now(timezone.utc)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The activation token is invalid or expired"
                )

            user = await self.repository.get_user_by_id(activation_token.user_id)

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The activation token is invalid or expired"
                )

            if user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The account is already active"
                )

            user.is_active = True
            await self.token_repository.delete_activation_token(activation_token)
            await self.repository.commit()

        return await self._send_activation_confirmation(user.email)

    async def _send_activation_confirmation(
            self,
            email: str
    ) -> AccountMessageResponseSchema:
        """
        Queue the activation confirmation without undoing activation if the queue fails.

        Args:
            email (str): Email address of the account or message recipient.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.
        """
        try:
            await self.email_queue.send_activation_complete_email(email)

        except EmailQueueError:
            return AccountMessageResponseSchema(
                message="Account activated successfully, "
                        "but the confirmation email could not be queued"
            )

        return AccountMessageResponseSchema(message="Account activated successfully")

    async def change_user_group(
            self,
            user_id: int,
            group_data: UserGroupUpdateRequestSchema
    ) -> UserResponseSchema:
        """
        Assign the requested existing group to the selected account.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            group_data (UserGroupUpdateRequestSchema): Requested user, moderator or
                admin group.

        Returns:
            UserResponseSchema: Public account fields, activation state and group; no
                password hash.

        Raises:
            HTTPException: The account or group is missing, or the database fails.
        """
        async with database_errors(
                self.repository,
                detail="User group update is temporarily unavailable"
        ):
            user = await self.repository.get_user_by_id(user_id)

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            group = await self.repository.get_group_by_name(group_data.group)

            if group is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="The requested user group is not configured"
                )

            user.group = group
            await self.repository.commit()
            await self.repository.refresh_user(user)

        return UserResponseSchema.model_validate(user)

    async def activate_user_manually(
            self,
            user_id: int
    ) -> AccountMessageResponseSchema:
        """
        Activate the selected account without a token and queue a confirmation email.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.

        Raises:
            HTTPException: The account is missing, already active or the database fails.
        """
        async with database_errors(
                self.repository,
                detail="Account activation is temporarily unavailable"
        ):
            activation_token = await self.token_repository.get_user_activation_token(
                user_id
            )
            user = await self.repository.get_user_by_id(user_id)

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            if user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The account is already active"
                )

            user.is_active = True

            if activation_token is not None:
                await self.token_repository.delete_activation_token(activation_token)

            await self.repository.commit()

        return await self._send_activation_confirmation(user.email)

    async def resend_activation_link(
            self,
            email_data: ActivationResendRequestSchema
    ) -> AccountMessageResponseSchema:
        """
        Queue an activation link, replacing the token only if it is missing or expired.

        Args:
            email_data (ActivationResendRequestSchema): Email address requesting another
                activation link.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.

        Raises:
            HTTPException: The database or activation email queue is unavailable.
        """
        response = AccountMessageResponseSchema(
            message="If an inactive account exists for this email, "
                    "an activation email will be queued"
        )

        async with database_errors(
                self.repository,
                detail="Activation email resend is temporarily unavailable"
        ):
            user = await self.repository.get_user_by_email(str(email_data.email))

            if not user or user.is_active:
                return response

            activation_token = await self.token_repository.get_user_activation_token(
                user.id
            )
            await self.repository.refresh_user(user)

            if user.is_active:
                return response

            now = datetime.now(timezone.utc)

            if activation_token is None:
                activation_token = ActivationTokenModel(user_id=user.id)
                self.token_repository.add_activation_token(activation_token)

            elif self.is_token_expired(activation_token.expires_at, now):
                activation_token.token = generate_secure_token()
                activation_token.expires_at = now + timedelta(hours=24)

            await self.repository.commit()

        try:
            await self.email_queue.send_activation_email(
                user.email,
                activation_token.token,
                activation_token.expires_at
            )

        except EmailQueueError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The activation email could not be queued. Please try again."
            )

        return response

    async def login(
            self,
            login_data: UserLoginRequestSchema,
            jwt_manager: JWTAuthManager
    ) -> TokenPairResponseSchema:
        """
        Check account credentials and activation, then issue and save authentication
        tokens.

        Args:
            login_data (UserLoginRequestSchema): Email and plaintext password supplied
                for login.
            jwt_manager (JWTAuthManager): Manager used to sign or validate access and
                refresh JWTs.

        Returns:
            TokenPairResponseSchema: Access and refresh JWTs with bearer token type.

        Raises:
            HTTPException: Credentials are incorrect, the account is inactive or the
                database fails.
        """
        async with database_errors(
                self.repository,
                detail="Login is temporarily unavailable. Please try again later."
        ):
            user = await self.repository.get_user_by_email(str(login_data.email))

            if user is None or not await run_in_threadpool(
                    user.verify_password,
                    login_data.password
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password",
                    headers={"WWW-Authenticate": "Bearer"}
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Activate your account before logging in"
                )

            jwt_access_token = jwt_manager.create_access_token(user.id)
            jwt_refresh_token = jwt_manager.create_refresh_token(user.id)

            refresh_payload = jwt_manager.decode_refresh_token(jwt_refresh_token)
            expires_at = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)
            refresh_token = RefreshTokenModel(
                user_id=user.id,
                token=jwt_refresh_token,
                expires_at=expires_at
            )
            self.token_repository.add_refresh_token(refresh_token)
            await self.repository.commit()

        return TokenPairResponseSchema(
            access_token=jwt_access_token,
            refresh_token=jwt_refresh_token
        )

    async def _get_valid_refresh_token(
            self,
            raw_token: str,
            jwt_manager: JWTAuthManager
    ) -> RefreshTokenModel:
        """
        Validate a refresh JWT against its stored token record and expiration.

        Args:
            raw_token (str): Refresh JWT supplied by the client.
            jwt_manager (JWTAuthManager): Manager used to sign or validate access and
                refresh JWTs.

        Returns:
            RefreshTokenModel: Requested database record(s).

        Raises:
            HTTPException: The refresh token is invalid, expired, revoked or belongs to
                a different account.
        """
        token_error = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )

        try:
            payload = jwt_manager.decode_refresh_token(raw_token)

        except InvalidTokenError:
            raise token_error

        token = await self.token_repository.get_refresh_token(raw_token)

        if token is None:
            raise token_error

        if token.user_id != int(payload["sub"]):
            raise token_error

        if self.is_token_expired(token.expires_at, datetime.now(timezone.utc)):
            raise token_error

        return token

    async def refresh_access_token(
            self,
            token_data: TokenRefreshRequestSchema,
            jwt_manager: JWTAuthManager
    ) -> AccessTokenResponseSchema:
        """
        Issue a new access token without rotating or extending the refresh token.

        Args:
            token_data (TokenRefreshRequestSchema): Refresh JWT used to obtain another
                access token.
            jwt_manager (JWTAuthManager): Manager used to sign or validate access and
                refresh JWTs.

        Returns:
            AccessTokenResponseSchema: New access JWT with bearer token type.

        Raises:
            HTTPException: The refresh token/account is invalid or inactive, or the
                database fails.
        """
        async with database_errors(
                self.repository,
                detail="Token refresh is temporarily unavailable"
        ):
            token = await self._get_valid_refresh_token(
                token_data.refresh_token,
                jwt_manager
            )
            user = await self.repository.get_user_by_id(token.user_id)

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token",
                    headers={"WWW-Authenticate": "Bearer"}
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is not active"
                )

            access_token = jwt_manager.create_access_token(user.id)
            await self.repository.commit()

        return AccessTokenResponseSchema(access_token=access_token)

    async def logout(
            self,
            logout_data: LogoutRequestSchema,
            jwt_manager: JWTAuthManager
    ) -> AccountMessageResponseSchema:
        """
        Delete the supplied refresh token while leaving other sessions unchanged.

        Args:
            logout_data (LogoutRequestSchema): Refresh JWT identifying the session to
                revoke.
            jwt_manager (JWTAuthManager): Manager used to sign or validate access and
                refresh JWTs.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.

        Raises:
            HTTPException: The refresh token is invalid or the database fails.
        """
        async with database_errors(
                self.repository,
                detail="Logout is temporarily unavailable"
        ):
            token = await self._get_valid_refresh_token(
                logout_data.refresh_token,
                jwt_manager
            )
            await self.token_repository.delete_refresh_token(token)
            await self.repository.commit()

        return AccountMessageResponseSchema(message="Logged out successfully")

    async def change_password(
            self,
            current_user: UserModel,
            password_data: PasswordChangeRequestSchema
    ) -> AccountMessageResponseSchema:
        """
        Check the old password, save a different strong password and revoke reset and
        refresh tokens.

        Args:
            current_user (UserModel): Authenticated account supplied by the access-token
                dependency.
            password_data (PasswordChangeRequestSchema): Current password and the
                requested new password.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.

        Raises:
            HTTPException: The old password is wrong, the new one is unchanged or the
                database fails.
        """
        if not await run_in_threadpool(
                current_user.verify_password,
                password_data.old_password
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect current password"
            )

        if password_data.old_password == password_data.new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must differ from the current password"
            )

        async with database_errors(
                self.repository,
                detail="Password change is temporarily unavailable"
        ):
            current_user._hashed_password = await run_in_threadpool(
                hash_password,
                password_data.new_password
            )
            await self.token_repository.delete_user_refresh_tokens(current_user.id)
            await self.token_repository.delete_user_password_reset_tokens(
                current_user.id
            )
            await self.repository.commit()

        return AccountMessageResponseSchema(
            message="Password changed successfully. Please log in again."
        )

    async def request_password_reset(
            self,
            email_data: PasswordResetRequestSchema
    ) -> AccountMessageResponseSchema:
        """
        Queue a one-use reset link for an active account without exposing account
        existence.

        Args:
            email_data (PasswordResetRequestSchema): Email address requesting password
                recovery.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.

        Raises:
            HTTPException: The database cannot store the reset token.
        """
        response = AccountMessageResponseSchema(
            message="If an active account exists for this email, "
                    "you will receive password reset instructions"
        )

        async with database_errors(
                self.repository,
                detail="Password reset is temporarily unavailable"
        ):
            user = await self.repository.get_user_by_email(str(email_data.email))

            if user is None or not user.is_active:
                return response

            reset_token = await self.token_repository.get_user_password_reset_token(
                user.id
            )
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            token = generate_secure_token()
            token_hash = hash_reset_token(token)

            if reset_token is None:
                reset_token = PasswordResetTokenModel(
                    user_id=user.id,
                    token=token_hash,
                    expires_at=expires_at
                )
                self.token_repository.add_password_reset_token(reset_token)

            else:
                reset_token.token = token_hash
                reset_token.expires_at = expires_at

            await self.repository.commit()

        await self.email_queue.send_password_reset_email(
            user.email,
            token,
            expires_at
        )

        return response

    async def reset_password(
            self,
            reset_data: PasswordResetConfirmRequestSchema
    ) -> AccountMessageResponseSchema:
        """
        Use a valid reset token to change the password and revoke reset and refresh
        tokens.

        Steps:
        - Find and validate the token by its stored hash.
        - Reject a password equal to the current one.
        - Commit the new hash and deletion of reset and refresh tokens together.

        Args:
            reset_data (PasswordResetConfirmRequestSchema): One-use reset token and the
                requested new password.

        Returns:
            AccountMessageResponseSchema: Account-operation status, including any
                nonfatal email-queue warning.

        Raises:
            HTTPException: The token/account is invalid, the new password is unchanged
                or the database fails.
        """
        token_error = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )

        async with database_errors(
                self.repository,
                detail="Password reset is temporarily unavailable"
        ):
            reset_token = await self.token_repository.get_password_reset_token(
                hash_reset_token(reset_data.token)
            )

            if reset_token is None or self.is_token_expired(
                    reset_token.expires_at,
                    datetime.now(timezone.utc)
            ):
                raise token_error

            user = await self.repository.get_user_by_id(reset_token.user_id)

            if user is None or not user.is_active:
                raise token_error

            if await run_in_threadpool(user.verify_password, reset_data.new_password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="New password must differ from the current password"
                )

            user._hashed_password = await run_in_threadpool(
                hash_password,
                reset_data.new_password
            )
            await self.token_repository.delete_user_password_reset_tokens(user.id)
            await self.token_repository.delete_user_refresh_tokens(user.id)
            await self.repository.commit()

        return AccountMessageResponseSchema(
            message="Password reset successfully. Please log in again"
        )

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import (
    ActivationTokenModel, PasswordResetTokenModel,
    RefreshTokenModel, UserModel,
)
from src.notifications.emails import EmailDeliveryError, EmailSender
from src.repositories.accounts import AccountRepository
from src.schemas.accounts import (
    AccessTokenResponseSchema,
    AccountActivationRequestSchema, AccountMessageResponseSchema,
    ActivationResendRequestSchema, LogoutRequestSchema,
    PasswordChangeRequestSchema, PasswordResetConfirmRequestSchema,
    PasswordResetRequestSchema,
    TokenPairResponseSchema, TokenRefreshRequestSchema,
    UserLoginRequestSchema, UserRegistrationRequestSchema, UserResponseSchema,
)
from src.security.tokens import InvalidTokenError, JWTAuthManager
from src.security.passwords import hash_password
from src.security.utils import generate_secure_token


class AccountService:
    def __init__(
        self, repository: AccountRepository, email_sender: EmailSender,
    ):
        self.repository = repository
        self.email_sender = email_sender

    @staticmethod
    def is_token_expired(expires_at: datetime, now: datetime) -> bool:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= now

    async def register_user(
        self, user_data: UserRegistrationRequestSchema,
    ) -> UserResponseSchema:
        try:
            existing_user = await self.repository.get_user_by_email(
                user_data.email,
            )

            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this email already exists.",
                )

            user_group = await self.repository.get_default_group()

            if not user_group:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Registration is temporarily unavailable.",
                )

            new_user = await run_in_threadpool(
                UserModel.create,
                email=str(user_data.email),
                raw_password=user_data.password,
                group_id=user_group.id,
            )
            new_user.is_active = False
            new_user.group = user_group
            await self.repository.add_user(new_user)
            self.repository.add_cart(new_user.id)
            activation_token = ActivationTokenModel(user_id=new_user.id)
            self.repository.add_activation_token(activation_token)
            await self.repository.commit()

        except IntegrityError as error:
            await self.repository.rollback()
            existing_user = await self.repository.get_user_by_email(
                user_data.email,
            )

            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this email already exists.",
                ) from error

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The account could not be saved.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration is temporarily unavailable.",
            ) from error

        try:
            await self.email_sender.send_activation_email(
                new_user.email,
                activation_token.token,
                activation_token.expires_at,
            )

        except EmailDeliveryError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Account created, but the activation email could not be "
                    "sent. Please request the activation email again."
                ),
            ) from error

        return UserResponseSchema.model_validate(new_user)

    async def activate_account(
        self, activation_data: AccountActivationRequestSchema,
    ) -> AccountMessageResponseSchema:
        try:
            activation_token = await self.repository.get_activation_token(
                activation_data.token,
            )

            if not activation_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The activation token is invalid or expired.",
                )

            if self.is_token_expired(
                activation_token.expires_at, datetime.now(timezone.utc),
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The activation token is invalid or expired.",
                )

            user = await self.repository.get_user_by_id(
                activation_token.user_id,
            )

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The activation token is invalid or expired.",
                )

            if user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The account is already active.",
                )

            user.is_active = True
            await self.repository.delete_activation_token(activation_token)
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account activation is temporarily unavailable.",
            ) from error

        try:
            await self.email_sender.send_activation_complete_email(user.email)

        except EmailDeliveryError:
            return AccountMessageResponseSchema(
                message=(
                    "Account activated successfully, but the confirmation "
                    "email could not be sent."
                ),
            )

        return AccountMessageResponseSchema(
            message="Account activated successfully.",
        )

    async def resend_activation_link(
        self, email_data: ActivationResendRequestSchema,
    ) -> AccountMessageResponseSchema:
        response = AccountMessageResponseSchema(
            message=(
                "If an inactive account exists for this email, "
                "an activation email has been sent."
            ),
        )
        try:
            user = await self.repository.get_user_by_email(email_data.email)

            if not user or user.is_active:
                return response

            activation_token = await self.repository.get_user_activation_token(
                user.id,
            )
            await self.repository.refresh_user(user)

            if user.is_active:
                return response

            now = datetime.now(timezone.utc)

            if activation_token is None:
                activation_token = ActivationTokenModel(user_id=user.id)
                self.repository.add_activation_token(activation_token)

            elif self.is_token_expired(activation_token.expires_at, now):
                activation_token.token = generate_secure_token()
                activation_token.expires_at = now + timedelta(hours=24)

            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Activation email resend is temporarily unavailable.",
            ) from error

        try:
            await self.email_sender.send_activation_email(
                user.email,
                activation_token.token,
                activation_token.expires_at,
            )
        except EmailDeliveryError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "The activation email could not be sent. Please try again."
                ),
            ) from error

        return response

    async def login(
        self, login_data: UserLoginRequestSchema, jwt_manager: JWTAuthManager,
    ) -> TokenPairResponseSchema:
        try:
            user = await self.repository.get_user_by_email(login_data.email)

            if user is None or not await run_in_threadpool(
                user.verify_password, login_data.password,
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Activate your account before logging in.",
                )

            jwt_access_token = jwt_manager.create_access_token(user.id)
            jwt_refresh_token = jwt_manager.create_refresh_token(user.id)

            refresh_payload = jwt_manager.decode_refresh_token(
                jwt_refresh_token,
            )
            expires_at = datetime.fromtimestamp(
                refresh_payload["exp"], tz=timezone.utc,
            )
            refresh_token = RefreshTokenModel(
                user_id=user.id,
                token=jwt_refresh_token,
                expires_at=expires_at,
            )
            self.repository.add_refresh_token(refresh_token)
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Login is temporarily unavailable. Please try again later."
                ),
            ) from error

        return TokenPairResponseSchema(
            access_token=jwt_access_token,
            refresh_token=jwt_refresh_token,
        )

    async def _get_valid_refresh_token(
        self, raw_token: str, jwt_manager: JWTAuthManager,
    ) -> RefreshTokenModel:
        token_error = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt_manager.decode_refresh_token(raw_token)

        except InvalidTokenError as error:
            raise token_error from error

        token = await self.repository.get_refresh_token(raw_token)

        if token is None:
            raise token_error

        if token.user_id != int(payload["sub"]):
            raise token_error

        if self.is_token_expired(token.expires_at, datetime.now(timezone.utc)):
            raise token_error

        return token

    async def refresh_access_token(
        self, token_data: TokenRefreshRequestSchema,
        jwt_manager: JWTAuthManager,
    ) -> AccessTokenResponseSchema:
        try:
            token = await self._get_valid_refresh_token(
                token_data.refresh_token, jwt_manager,
            )
            user = await self.repository.get_user_by_id(token.user_id)

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is not active.",
                )

            access_token = jwt_manager.create_access_token(user.id)
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Token refresh is temporarily unavailable.",
            ) from error

        return AccessTokenResponseSchema(access_token=access_token)

    async def logout(
        self, logout_data: LogoutRequestSchema, jwt_manager: JWTAuthManager,
    ) -> AccountMessageResponseSchema:
        try:
            token = await self._get_valid_refresh_token(
                logout_data.refresh_token, jwt_manager,
            )
            await self.repository.delete_refresh_token(token)
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Logout is temporarily unavailable.",
            ) from error

        return AccountMessageResponseSchema(message="Logged out successfully.")

    async def change_password(
        self, current_user: UserModel,
        password_data: PasswordChangeRequestSchema,
    ) -> AccountMessageResponseSchema:
        if not await run_in_threadpool(
            current_user.verify_password, password_data.old_password,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect current password.",
            )

        if password_data.old_password == password_data.new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must differ from the current password.",
            )

        try:
            current_user._hashed_password = await run_in_threadpool(
                hash_password, password_data.new_password,
            )
            await self.repository.delete_user_refresh_tokens(current_user.id)
            await self.repository.delete_user_password_reset_tokens(
                current_user.id,
            )
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password change is temporarily unavailable.",
            ) from error

        return AccountMessageResponseSchema(
            message="Password changed successfully. Please log in again.",
        )

    async def request_password_reset(
        self, email_data: PasswordResetRequestSchema,
    ) -> AccountMessageResponseSchema:
        response = AccountMessageResponseSchema(
            message=(
                "If an active account exists for this email, "
                "password reset instructions have been sent."
            ),
        )

        try:
            user = await self.repository.get_user_by_email(email_data.email)

            if user is None or not user.is_active:
                return response

            reset_token = await self.repository.get_user_password_reset_token(
                user.id,
            )
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

            if reset_token is None:
                reset_token = PasswordResetTokenModel(
                    user_id=user.id, expires_at=expires_at,
                )
                self.repository.add_password_reset_token(reset_token)

            else:
                reset_token.token = generate_secure_token()
                reset_token.expires_at = expires_at
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password reset is temporarily unavailable.",
            ) from error

        try:
            await self.email_sender.send_password_reset_email(
                user.email, reset_token.token, reset_token.expires_at,
            )

        except EmailDeliveryError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The reset email could not be sent. Please try again.",
            ) from error

        return response

    async def reset_password(
        self, reset_data: PasswordResetConfirmRequestSchema,
    ) -> AccountMessageResponseSchema:
        token_error = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

        try:
            reset_token = await self.repository.get_password_reset_token(
                reset_data.token,
            )

            if reset_token is None or self.is_token_expired(
                reset_token.expires_at, datetime.now(timezone.utc),
            ):
                raise token_error

            user = await self.repository.get_user_by_id(reset_token.user_id)

            if user is None or not user.is_active:
                raise token_error

            user._hashed_password = await run_in_threadpool(
                hash_password, reset_data.new_password,
            )
            await self.repository.delete_user_password_reset_tokens(user.id)
            await self.repository.delete_user_refresh_tokens(user.id)
            await self.repository.commit()

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password reset is temporarily unavailable.",
            ) from error

        return AccountMessageResponseSchema(
            message="Password reset successfully. Please log in again.",
        )

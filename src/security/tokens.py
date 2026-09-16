from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from jose import (  # type: ignore[import-untyped]
    ExpiredSignatureError, JWTError, jwt,
)

from src.core.config import Settings, get_settings


class InvalidTokenError(ValueError):
    pass


class TokenExpiredError(InvalidTokenError):
    pass


class JWTAuthManager:
    def __init__(self, settings: Settings):
        if (
            settings.JWT_ACCESS_SECRET_KEY is None
            or settings.JWT_REFRESH_SECRET_KEY is None
        ):
            raise ValueError(
                "Set JWT_ACCESS_SECRET_KEY and JWT_REFRESH_SECRET_KEY in .env."
            )
        self._secret_key_access = (
            settings.JWT_ACCESS_SECRET_KEY.get_secret_value()
        )
        self._secret_key_refresh = (
            settings.JWT_REFRESH_SECRET_KEY.get_secret_value()
        )
        self._algorithm = settings.JWT_ALGORITHM
        self._access_lifetime = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        self._refresh_lifetime = timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        )

    def _create_token(
        self, user_id: int, token_type: Literal["access", "refresh"],
        secret_key: str, lifetime: timedelta,
    ) -> str:
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("User ID must be a positive integer.")

        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": token_type,
            "iat": int(now.timestamp()),
            "exp": int((now + lifetime).timestamp()),
            "jti": uuid4().hex,
        }
        token = jwt.encode(payload, secret_key, algorithm=self._algorithm)
        if len(token) > 255:
            raise ValueError("The token exceeds the supported length of 255.")
        return token

    def create_access_token(self, user_id: int) -> str:
        return self._create_token(
            user_id, "access", self._secret_key_access, self._access_lifetime,
        )

    def create_refresh_token(self, user_id: int) -> str:
        return self._create_token(
            user_id, "refresh",
            self._secret_key_refresh, self._refresh_lifetime,
        )

    def _decode_token(
        self, token: str, secret_key: str,
        expected_type: Literal["access", "refresh"],
    ) -> dict[str, Any]:
        try:
            if not isinstance(token, str) or not token or len(token) > 255:
                raise ValueError("Invalid token format.")
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[self._algorithm],
                options={
                    "require_sub": True,
                    "require_exp": True,
                    "require_iat": True,
                    "require_jti": True,
                },
            )
            if payload.get("type") != expected_type:
                raise ValueError("Unexpected token type.")

            user_id = payload["sub"]
            if (
                not user_id.isascii()
                or not user_id.isdecimal()
                or int(user_id) <= 0
            ):
                raise ValueError("Invalid user ID.")
            if not payload["jti"]:
                raise ValueError("Missing token ID.")

            issued_at = payload["iat"]
            expires_at = payload["exp"]
            if type(issued_at) is not int or type(expires_at) is not int:
                raise ValueError("Token timestamps must be integers.")
            now = int(datetime.now(timezone.utc).timestamp())
            if expires_at <= now:
                raise ExpiredSignatureError("Token has expired.")
            if issued_at > now or expires_at <= issued_at:
                raise ValueError("Invalid token lifetime.")
        except ExpiredSignatureError as error:
            raise TokenExpiredError("Token has expired.") from error
        except (JWTError, ValueError, TypeError, OverflowError) as error:
            raise InvalidTokenError("Invalid token.") from error
        return payload

    def decode_access_token(self, token: str) -> dict[str, Any]:
        return self._decode_token(token, self._secret_key_access, "access")

    def decode_refresh_token(self, token: str) -> dict[str, Any]:
        return self._decode_token(token, self._secret_key_refresh, "refresh")


def get_jwt_auth_manager() -> JWTAuthManager:
    return JWTAuthManager(get_settings())

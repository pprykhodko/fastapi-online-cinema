from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.database.models.accounts import GenderEnum, UserGroupEnum
from src.database.validators import accounts as accounts_validators
from src.schemas.common import (
    MessageResponseSchema, PaginationQuerySchema, PaginationResponseSchema,
)
from src.security.passwords import validate_password_for_bcrypt


class BaseEmailSchema(BaseModel):
    email: EmailStr = Field(max_length=255)

    model_config = {
        "extra": "forbid",
        "hide_input_in_errors": True
    }

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return accounts_validators.validate_email(value)


class BaseEmailPasswordSchema(BaseEmailSchema):
    password: str = Field(
        min_length=8, max_length=72, repr=False, exclude=True,
        description="Strong password; at most 72 bytes in UTF-8.",
        json_schema_extra={
            "format": "password",
            "writeOnly": True
        },
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return accounts_validators.validate_password_strength(value)


class UserRegistrationRequestSchema(BaseEmailPasswordSchema):
    pass


class UserLoginRequestSchema(BaseEmailSchema):
    password: str = Field(
        min_length=1, max_length=72, repr=False, exclude=True,
        json_schema_extra={
            "format": "password",
            "writeOnly": True
        },
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_for_bcrypt(value)


class AccountActivationRequestSchema(BaseModel):
    token: str = Field(
        min_length=1, max_length=255, pattern=r"^\S+$", repr=False,
        json_schema_extra={"writeOnly": True},
    )

    model_config = {
        "extra": "forbid",
        "hide_input_in_errors": True
    }


class ActivationResendRequestSchema(BaseEmailSchema):
    pass


class TokenRefreshRequestSchema(BaseModel):
    refresh_token: str = Field(
        min_length=1, max_length=255, pattern=r"^\S+$", repr=False,
        json_schema_extra={"writeOnly": True},
    )

    model_config = {
        "extra": "forbid",
        "hide_input_in_errors": True
    }


class LogoutRequestSchema(TokenRefreshRequestSchema):
    pass


class PasswordChangeRequestSchema(BaseModel):
    old_password: str = Field(
        min_length=1, max_length=72, repr=False, exclude=True,
        json_schema_extra={"format": "password", "writeOnly": True},
    )
    new_password: str = Field(
        min_length=8, max_length=72, repr=False, exclude=True,
        description="Strong password; at most 72 bytes in UTF-8.",
        json_schema_extra={"format": "password", "writeOnly": True},
    )

    model_config = {
        "extra": "forbid",
        "hide_input_in_errors": True
    }

    @field_validator("old_password")
    @classmethod
    def validate_old_password(cls, value: str) -> str:
        return validate_password_for_bcrypt(value)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return accounts_validators.validate_password_strength(value)


class PasswordResetRequestSchema(BaseEmailSchema):
    pass


class PasswordResetConfirmRequestSchema(BaseModel):
    token: str = Field(
        min_length=1, max_length=255, pattern=r"^\S+$", repr=False,
        json_schema_extra={"writeOnly": True},
    )
    new_password: str = Field(
        min_length=8, max_length=72, repr=False, exclude=True,
        description="Strong password; at most 72 bytes in UTF-8.",
        json_schema_extra={"format": "password", "writeOnly": True},
    )

    model_config = {
        "extra": "forbid",
        "hide_input_in_errors": True
    }

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return accounts_validators.validate_password_strength(value)


class AccessTokenResponseSchema(BaseModel):
    access_token: str = Field(min_length=1, pattern=r"^\S+$", repr=False)
    token_type: Literal["bearer"] = "bearer"

    model_config = {"from_attributes": True}


class TokenPairResponseSchema(AccessTokenResponseSchema):
    refresh_token: str = Field(
        min_length=1, max_length=255, pattern=r"^\S+$", repr=False,
    )


class UserGroupResponseSchema(BaseModel):
    id: int = Field(gt=0)
    name: UserGroupEnum

    model_config = {"from_attributes": True}


class UserResponseSchema(BaseModel):
    id: int = Field(gt=0)
    email: EmailStr = Field(max_length=255)
    is_active: bool
    created_at: datetime
    updated_at: datetime
    group: UserGroupResponseSchema

    model_config = {"from_attributes": True}

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return accounts_validators.validate_email(value)


class UserGroupUpdateRequestSchema(BaseModel):
    group: UserGroupEnum

    model_config = {
        "extra": "forbid",
        "hide_input_in_errors": True
    }


class UserProfileUpdateRequestSchema(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    gender: GenderEnum | None = None
    date_of_birth: date | None = None
    info: str | None = None

    model_config = {
        "extra": "forbid",
        "hide_input_in_errors": True
    }


class BaseUserProfileSchema(UserProfileUpdateRequestSchema):
    avatar: str | None = Field(
        default=None, max_length=255,
        description="Avatar URL or storage object key.",
    )


class UserProfileCreateRequestSchema(BaseUserProfileSchema):
    pass


class UserProfileResponseSchema(BaseUserProfileSchema):
    avatar: str | None = Field(
        default=None, description="Temporary signed URL to view the avatar.",
    )
    id: int = Field(gt=0)
    user_id: int = Field(gt=0)

    model_config = {"from_attributes": True}


class AccountMessageResponseSchema(MessageResponseSchema):
    pass


class UserListQuerySchema(PaginationQuerySchema):
    pass


class UserListResponseSchema(PaginationResponseSchema):
    items: list[UserResponseSchema]

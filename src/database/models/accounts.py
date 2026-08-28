from __future__ import annotations

import enum
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, NoReturn, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database.models.base import Base
from src.database.validators import accounts as validators
from src.security.passwords import hash_password, verify_password
from src.security.utils import generate_secure_token

if TYPE_CHECKING:
    from src.database.models.cart import CartModel


class UserGroupEnum(str, enum.Enum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class GenderEnum(str, enum.Enum):
    MAN = "man"
    WOMAN = "woman"


class UserGroupModel(Base):
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[UserGroupEnum] = mapped_column(
        Enum(UserGroupEnum, name="user_group_enum"),
        nullable=False,
        unique=True,
    )

    users: Mapped[List[UserModel]] = relationship(back_populates="group")

    def __repr__(self) -> str:
        return f"<UserGroupModel(id={self.id}, name={self.name})>"


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    _hashed_password: Mapped[str] = mapped_column(
        "hashed_password",
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("user_groups.id", ondelete="RESTRICT"),
        nullable=False,
    )

    group: Mapped[UserGroupModel] = relationship(back_populates="users")
    activation_token: Mapped[Optional[ActivationTokenModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    password_reset_token: Mapped[
        Optional[PasswordResetTokenModel]
    ] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    refresh_tokens: Mapped[List[RefreshTokenModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    profile: Mapped[Optional[UserProfileModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    cart: Mapped[Optional[CartModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    @classmethod
    def create(
        cls,
        email: str,
        raw_password: str,
        group_id: int,
    ) -> UserModel:
        user = cls(email=email, group_id=group_id)
        user.password = raw_password
        return user

    @property
    def password(self) -> NoReturn:
        raise AttributeError("Password is write-only.")

    @password.setter
    def password(self, raw_password: str) -> None:
        validators.validate_password_strength(raw_password)
        self._hashed_password = hash_password(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        return verify_password(raw_password, self._hashed_password)

    def has_group(self, group_name: UserGroupEnum) -> bool:
        return self.group.name == group_name

    @validates("email")
    def validate_email(self, _key: str, value: str) -> str:
        return validators.validate_email(value)

    def __repr__(self) -> str:
        return (
            f"<UserModel(id={self.id}, email={self.email}, "
            f"is_active={self.is_active})>"
        )


class UserProfileModel(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    avatar: Mapped[Optional[str]] = mapped_column(String(255))
    gender: Mapped[Optional[GenderEnum]] = mapped_column(
        Enum(GenderEnum, name="gender_enum")
    )
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    info: Mapped[Optional[str]] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    user: Mapped[UserModel] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return (
            f"<UserProfileModel(id={self.id}, "
            f"first_name={self.first_name}, last_name={self.last_name})>"
        )


class TokenBaseModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        default=generate_secure_token,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=1),
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


class ActivationTokenModel(TokenBaseModel):
    __tablename__ = "activation_tokens"
    __table_args__ = (UniqueConstraint("user_id"),)

    user: Mapped[UserModel] = relationship(back_populates="activation_token")

    def __repr__(self) -> str:
        return (
            f"<ActivationTokenModel(id={self.id}, "
            f"expires_at={self.expires_at})>"
        )


class PasswordResetTokenModel(TokenBaseModel):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (UniqueConstraint("user_id"),)

    user: Mapped[UserModel] = relationship(
        back_populates="password_reset_token"
    )

    def __repr__(self) -> str:
        return (
            f"<PasswordResetTokenModel(id={self.id}, "
            f"expires_at={self.expires_at})>"
        )


class RefreshTokenModel(TokenBaseModel):
    __tablename__ = "refresh_tokens"

    token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    user: Mapped[UserModel] = relationship(back_populates="refresh_tokens")

    @classmethod
    def create(
        cls,
        user_id: int,
        days_valid: int,
        token: str,
    ) -> RefreshTokenModel:
        expires_at = datetime.now(timezone.utc) + timedelta(days=days_valid)
        return cls(user_id=user_id, expires_at=expires_at, token=token)

    def __repr__(self) -> str:
        return (
            f"<RefreshTokenModel(id={self.id}, "
            f"expires_at={self.expires_at})>"
        )

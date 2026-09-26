from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import (
    EmailStr,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
    model_validator
)
from pydantic_settings import BaseSettings
from sqlalchemy import URL


class BaseAppSettings(BaseSettings):

    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[2]
    DATABASE_TYPE: Literal["sqlite", "postgresql"] = "sqlite"
    PATH_TO_DB: str = Field(default="db.sqlite3", min_length=1)
    DATABASE_ECHO: bool = False

    model_config = {
        "env_file": BASE_DIR / ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "hide_input_in_errors": True
    }

    @property
    def SQLITE_DATABASE_URL(self) -> URL:
        if self.PATH_TO_DB == ":memory:":
            database = self.PATH_TO_DB

        else:
            database = str((self.BASE_DIR / self.PATH_TO_DB).resolve())

        return URL.create("sqlite+aiosqlite", database=database)


class Settings(BaseAppSettings):

    STRIPE_SECRET_KEY: SecretStr = SecretStr("")
    STRIPE_WEBHOOK_SECRET: SecretStr = SecretStr("")
    STRIPE_CURRENCY: Literal["usd", "eur"] = "usd"
    STRIPE_LIVE_MODE: bool = False
    PAYMENT_RETURN_URL: HttpUrl = HttpUrl(
        "http://localhost:8000/api/v1/payments/return/"
    )

    POSTGRES_HOST: str = Field(default="localhost", min_length=1)
    POSTGRES_DB_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_DB: str = Field(default="online_cinema", min_length=1)
    POSTGRES_USER: str = Field(default="postgres", min_length=1)
    POSTGRES_PASSWORD: str = Field(default="", repr=False)

    SMTP_HOST: str = Field(default="localhost", min_length=1)
    SMTP_PORT: int = Field(default=1025, ge=1, le=65535)
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = Field(default="", repr=False)
    SMTP_FROM_EMAIL: EmailStr = "noreply@example.com"
    SMTP_USE_TLS: bool = False
    SMTP_START_TLS: bool = False
    SMTP_TIMEOUT: float = Field(default=10, gt=0)
    ACCOUNT_ACTIVATION_URL: HttpUrl = HttpUrl(
        "http://localhost:8000/api/v1/accounts/activate"
    )
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/0",
        min_length=1,
        repr=False
    )

    S3_ENDPOINT_URL: HttpUrl | None = None
    S3_PUBLIC_ENDPOINT_URL: HttpUrl | None = None
    S3_ACCESS_KEY: str = Field(default="", repr=False)
    S3_SECRET_KEY: SecretStr = SecretStr("")
    S3_BUCKET_NAME: str = Field(default="avatars", min_length=1)
    S3_REGION: str = "us-east-1"
    S3_URL_EXPIRE_SECONDS: int = Field(default=3600, ge=60, le=604800)
    AVATAR_MAX_BYTES: int = Field(default=5 * 1024 * 1024, gt=0)

    JWT_ACCESS_SECRET_KEY: SecretStr | None = Field(
        default=None,
        min_length=32,
        repr=False
    )
    JWT_REFRESH_SECRET_KEY: SecretStr | None = Field(
        default=None,
        min_length=32,
        repr=False
    )
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0, le=365)

    @field_validator("JWT_ACCESS_SECRET_KEY", "JWT_REFRESH_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("JWT secret keys must not be blank")

        return value

    @model_validator(mode="after")
    def validate_jwt_keys(self) -> "Settings":
        if (
            self.JWT_ACCESS_SECRET_KEY is not None
            and self.JWT_REFRESH_SECRET_KEY is not None
            and self.JWT_ACCESS_SECRET_KEY == self.JWT_REFRESH_SECRET_KEY
        ):
            raise ValueError("JWT access and refresh keys must be different")

        return self

    @model_validator(mode="after")
    def validate_smtp_tls(self) -> "Settings":
        if self.SMTP_USE_TLS and self.SMTP_START_TLS:
            raise ValueError("Choose SMTP_USE_TLS or SMTP_START_TLS, not both")

        return self

    @property
    def DATABASE_URL(self) -> URL:
        if self.DATABASE_TYPE == "sqlite":
            return self.SQLITE_DATABASE_URL

        return self.POSTGRESQL_DATABASE_URL

    @property
    def POSTGRESQL_DATABASE_URL(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_DB_PORT,
            database=self.POSTGRES_DB
        )


class TestingSettings(BaseAppSettings):

    PATH_TO_DB: str = ":memory:"

    model_config = {"env_file": None}

    def model_post_init(self, __context: Any) -> None:
        self.DATABASE_TYPE = "sqlite"
        self.PATH_TO_DB = ":memory:"


@lru_cache
def get_settings() -> Settings:

    return Settings()

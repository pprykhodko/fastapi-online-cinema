from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import EmailStr, Field, HttpUrl, model_validator
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
        "hide_input_in_errors": True,
    }

    @property
    def SQLITE_DATABASE_URL(self) -> URL:
        if self.PATH_TO_DB == ":memory:":
            database = self.PATH_TO_DB
        else:
            database = str((self.BASE_DIR / self.PATH_TO_DB).resolve())
        return URL.create("sqlite+aiosqlite", database=database)


class Settings(BaseAppSettings):
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
        default="redis://localhost:6379/0", min_length=1, repr=False,
    )

    @model_validator(mode="after")
    def validate_smtp_tls(self) -> "Settings":
        if self.SMTP_USE_TLS and self.SMTP_START_TLS:
            raise ValueError(
                "Choose SMTP_USE_TLS or SMTP_START_TLS, not both."
            )
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
            database=self.POSTGRES_DB,
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

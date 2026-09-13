from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings
from sqlalchemy import URL


class BaseAppSettings(BaseSettings):
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[2]
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
        self.PATH_TO_DB = ":memory:"


@lru_cache
def get_settings() -> Settings:
    return Settings()

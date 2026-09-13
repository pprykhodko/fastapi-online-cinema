from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import URL, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings


settings = get_settings()
SQLITE_DATABASE_URL = settings.SQLITE_DATABASE_URL


def enable_foreign_keys(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_sqlite_engine(database_url: URL) -> AsyncEngine:
    engine = create_async_engine(database_url, echo=settings.DATABASE_ECHO)
    event.listen(engine.sync_engine, "connect", enable_foreign_keys)
    return engine


sqlite_engine = create_sqlite_engine(SQLITE_DATABASE_URL)

AsyncSQLiteSessionLocal = async_sessionmaker(
    bind=sqlite_engine,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_sqlite_db_contextmanager() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSQLiteSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_sqlite_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_sqlite_db_contextmanager() as session:
        yield session

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
    """
    Enable foreign-key enforcement for each new SQLite connection.

    Args:
        dbapi_connection: New SQLite driver connection.
        connection_record: SQLAlchemy pool record; unused by this connection hook.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_sqlite_engine(database_url: URL) -> AsyncEngine:
    """
    Create an async SQLite engine with foreign-key enforcement enabled.

    Args:
        database_url (URL): SQLAlchemy URL pointing to the SQLite database.

    Returns:
        AsyncEngine: Configured object for the selected database or application
            settings.
    """
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
    """
    Open a SQLite session, roll back on errors and close it when finished.

    Yields:
        AsyncSession: Session whose transaction is committed explicitly by the caller.
    """
    async with AsyncSQLiteSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_sqlite_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a SQLite session to FastAPI and close it after the request.

    Yields:
        AsyncSession: Session whose transaction is committed explicitly by the caller.
    """
    async with get_sqlite_db_contextmanager() as session:
        yield session

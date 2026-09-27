from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings


settings = get_settings()
POSTGRESQL_DATABASE_URL = settings.POSTGRESQL_DATABASE_URL

postgresql_engine = create_async_engine(
    POSTGRESQL_DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
)

AsyncPostgresqlSessionLocal = async_sessionmaker(
    bind=postgresql_engine,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_postgresql_db_contextmanager() -> AsyncGenerator[
    AsyncSession, None,
]:
    """
    Open a PostgreSQL session, roll back on errors and close it when finished.

    Yields:
        AsyncSession: Session whose transaction is committed explicitly by the caller.
    """
    async with AsyncPostgresqlSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_postgresql_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a PostgreSQL session to FastAPI and close it after the request.

    Yields:
        AsyncSession: Session whose transaction is committed explicitly by the caller.
    """
    async with get_postgresql_db_contextmanager() as session:
        yield session

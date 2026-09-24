import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.database.models import ActivationTokenModel


async def cleanup_expired_activation_tokens() -> None:
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine)

    try:
        async with sessions.begin() as db:
            await db.execute(
                delete(ActivationTokenModel)
                .where(ActivationTokenModel.expires_at <= datetime.now(timezone.utc))
            )

    finally:
        await engine.dispose()


@celery_app.task(name="accounts.delete_expired_activation_tokens")
def delete_expired_activation_tokens() -> None:
    asyncio.run(cleanup_expired_activation_tokens())

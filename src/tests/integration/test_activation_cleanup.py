from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import URL, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import Settings
from src.database.models import (
    ActivationTokenModel, Base, PasswordResetTokenModel, UserGroupEnum,
    UserGroupModel, UserModel,
)
from src.tasks import accounts


@pytest.mark.asyncio
async def test_cleanup_removes_only_expired_activation_tokens(
    tmp_path, monkeypatch,
):
    database_path = tmp_path / "activation-cleanup.sqlite3"
    settings = Settings(
        _env_file=None, DATABASE_TYPE="sqlite", PATH_TO_DB=str(database_path),
    )
    monkeypatch.setattr(accounts, "get_settings", lambda: settings)
    engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(database_path))
    )
    sessions = async_sessionmaker(engine)
    now = datetime.now(timezone.utc)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions.begin() as db:
            db.add(UserGroupModel(id=42, name=UserGroupEnum.USER))
            await db.flush()
            for index, expiry in enumerate([
                now - timedelta(hours=1), now, now + timedelta(hours=1),
            ], start=1):
                db.add(UserModel(
                    id=index, email=f"user{index}@example.com", group_id=42,
                    _hashed_password="unused-test-hash",
                ))
                await db.flush()
                db.add(ActivationTokenModel(user_id=index, expires_at=expiry))
            db.add(PasswordResetTokenModel(user_id=1, expires_at=now))

        await accounts.cleanup_expired_activation_tokens()
        await accounts.cleanup_expired_activation_tokens()

        async with sessions() as db:
            tokens = (await db.scalars(select(ActivationTokenModel))).all()
            assert len(tokens) == 1
            assert tokens[0].user_id == 3
            assert len((await db.scalars(select(UserModel))).all()) == 3
            reset_token = await db.scalar(select(PasswordResetTokenModel))
            assert reset_token is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_disposes_engine_on_error(monkeypatch):
    engine = AsyncMock()
    monkeypatch.setattr(
        accounts, "create_async_engine", lambda *a, **k: engine,
    )

    def failing_sessions(*args, **kwargs):
        class Sessions:
            def begin(self):
                raise RuntimeError("database unavailable")
        return Sessions()

    monkeypatch.setattr(accounts, "async_sessionmaker", failing_sessions)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await accounts.cleanup_expired_activation_tokens()
    engine.dispose.assert_awaited_once()

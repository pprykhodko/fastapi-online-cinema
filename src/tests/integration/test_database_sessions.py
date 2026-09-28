import pytest
from sqlalchemy import URL, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.database import session_sqlite


@pytest.mark.asyncio
async def test_sqlite_engine_enforces_foreign_keys(tmp_path):
    engine = session_sqlite.create_sqlite_engine(
        URL.create("sqlite+aiosqlite", database=str(tmp_path / "foreign_keys.sqlite3"))
    )
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
            await connection.execute(text(
                "CREATE TABLE parent (id INTEGER PRIMARY KEY)"
            ))
            await connection.execute(text(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parent(id))"
            ))
        async with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                await connection.execute(text(
                    "INSERT INTO child (id, parent_id) VALUES (1, 999)"
                ))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_session_commit_and_rollback(tmp_path, monkeypatch):
    engine = session_sqlite.create_sqlite_engine(
        URL.create("sqlite+aiosqlite", database=str(tmp_path / "sessions.sqlite3"))
    )
    monkeypatch.setattr(
        session_sqlite, "AsyncSQLiteSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE item (id INTEGER PRIMARY KEY)"))
        async with session_sqlite.get_sqlite_db_contextmanager() as session:
            await session.execute(text("INSERT INTO item (id) VALUES (1)"))
            await session.commit()
        with pytest.raises(RuntimeError, match="abort transaction"):
            async with session_sqlite.get_sqlite_db_contextmanager() as session:
                await session.execute(text("INSERT INTO item (id) VALUES (2)"))
                raise RuntimeError("abort transaction")
        async with session_sqlite.get_sqlite_db_contextmanager() as session:
            await session.execute(text("INSERT INTO item (id) VALUES (3)"))
        async with session_sqlite.get_sqlite_db_contextmanager() as session:
            result = await session.scalars(text("SELECT id FROM item ORDER BY id"))
            assert list(result) == [1]
    finally:
        await engine.dispose()

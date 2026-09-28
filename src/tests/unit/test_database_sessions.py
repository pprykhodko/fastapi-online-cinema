from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession


DATABASE_DIR = Path(__file__).resolve().parents[2] / "database"


@pytest.fixture(params=["sqlite", "postgresql"])
def session_module(request, monkeypatch):
    backend = request.param
    settings = SimpleNamespace(
        DATABASE_ECHO=True,
        SQLITE_DATABASE_URL=URL.create("sqlite+aiosqlite", database=":memory:"),
        POSTGRESQL_DATABASE_URL=URL.create(
            "postgresql+asyncpg", username="test", password="test",
            host="unused-host", database="test"
        )
    )
    engine = Mock()
    session = AsyncMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    factory = Mock(return_value=session)
    create_engine = Mock(return_value=engine)
    create_factory = Mock(return_value=factory)
    listen = Mock()
    monkeypatch.setattr("src.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", create_engine)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.async_sessionmaker", create_factory)
    monkeypatch.setattr("sqlalchemy.event.listen", listen)
    module = runpy.run_path(str(DATABASE_DIR / f"session_{backend}.py"))
    return SimpleNamespace(
        backend=backend, settings=settings, engine=engine, session=session,
        factory=factory, create_engine=create_engine, create_factory=create_factory,
        listen=listen, module=module
    )


def test_engine_and_factory_configuration(session_module):
    data = session_module
    expected = {"echo": True}
    if data.backend == "postgresql":
        expected["pool_pre_ping"] = True
    url = getattr(data.settings, f"{data.backend.upper()}_DATABASE_URL")
    data.create_engine.assert_called_once_with(url, **expected)
    data.create_factory.assert_called_once_with(
        bind=data.engine, expire_on_commit=False
    )
    if data.backend == "sqlite":
        data.listen.assert_called_once_with(
            data.engine.sync_engine, "connect", data.module["enable_foreign_keys"]
        )
    else:
        data.listen.assert_not_called()


@pytest.mark.asyncio
async def test_context_manager_closes_session_without_committing(session_module):
    data = session_module
    context = data.module[f"get_{data.backend}_db_contextmanager"]
    async with context() as session:
        assert session is data.session
        data.session.__aexit__.assert_not_awaited()
    data.factory.assert_called_once_with()
    data.session.__aenter__.assert_awaited_once_with()
    data.session.__aexit__.assert_awaited_once_with(None, None, None)
    data.session.commit.assert_not_awaited()
    data.session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_manager_rolls_back_and_preserves_error(session_module):
    data = session_module
    context = data.module[f"get_{data.backend}_db_contextmanager"]
    error = RuntimeError("operation failed")
    with pytest.raises(RuntimeError) as caught:
        async with context():
            raise error
    assert caught.value is error
    data.session.rollback.assert_awaited_once_with()
    data.session.commit.assert_not_awaited()
    data.session.__aexit__.assert_awaited_once()
    assert data.session.__aexit__.call_args.args[1] is error


@pytest.mark.asyncio
async def test_dependency_yields_one_session_and_closes_it(session_module):
    data = session_module
    dependency = data.module[f"get_{data.backend}_db"]()
    assert await anext(dependency) is data.session
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    data.session.__aexit__.assert_awaited_once_with(None, None, None)
    data.session.commit.assert_not_awaited()
    data.session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_dependency_closes_session_when_consumer_stops(session_module):
    data = session_module
    dependency = data.module[f"get_{data.backend}_db"]()
    assert await anext(dependency) is data.session
    await dependency.aclose()
    data.session.__aexit__.assert_awaited_once()
    data.session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_dependency_rolls_back_when_consumer_raises(session_module):
    data = session_module
    dependency = data.module[f"get_{data.backend}_db"]()
    assert await anext(dependency) is data.session
    error = RuntimeError("request failed")
    with pytest.raises(RuntimeError) as caught:
        await dependency.athrow(error)
    assert caught.value is error
    data.session.rollback.assert_awaited_once_with()
    data.session.__aexit__.assert_awaited_once()
    data.session.commit.assert_not_awaited()


@pytest.mark.parametrize("fails", [False, True])
def test_sqlite_foreign_key_hook_always_closes_cursor(fails):
    from src.database.session_sqlite import enable_foreign_keys

    connection = Mock()
    cursor = connection.cursor.return_value
    if fails:
        cursor.execute.side_effect = RuntimeError("pragma failed")
        with pytest.raises(RuntimeError, match="pragma failed"):
            enable_foreign_keys(connection, None)
    else:
        enable_foreign_keys(connection, None)
    cursor.execute.assert_called_once_with("PRAGMA foreign_keys=ON")
    cursor.close.assert_called_once_with()

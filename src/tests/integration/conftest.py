import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.config import Settings
from src.database import get_db
from src.database.models import Base, UserGroupEnum, UserGroupModel, UserModel
from src.database.session_sqlite import create_sqlite_engine
from src.main import app
from src.security.passwords import hash_password
from src.security.tokens import JWTAuthManager, get_jwt_auth_manager


PASSWORD = "StrongPassword1!"


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(PASSWORD)


@pytest_asyncio.fixture
async def login_api(monkeypatch, password_hash):
    engine = create_sqlite_engine(
        URL.create("sqlite+aiosqlite", database=":memory:")
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        group = UserGroupModel(name=UserGroupEnum.USER)
        db.add(group)
        await db.flush()
        user = UserModel(
            email="user@example.com", group_id=group.id,
            _hashed_password=password_hash, is_active=True
        )
        db.add(user)
        await db.commit()
        user_id = user.id

    manager = JWTAuthManager(Settings(
        _env_file=None,
        JWT_ACCESS_SECRET_KEY="test-access-key-for-login-endpoint-only",
        JWT_REFRESH_SECRET_KEY="test-refresh-key-for-login-endpoint-only",
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=15,
        REFRESH_TOKEN_EXPIRE_DAYS=7
    ))

    async def override_db():
        async with sessions() as db:
            try:
                yield db
            except Exception:
                await db.rollback()
                raise

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    monkeypatch.setitem(
        app.dependency_overrides, get_jwt_auth_manager, lambda: manager
    )
    try:
        async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, sessions, manager, user_id
    finally:
        await engine.dispose()

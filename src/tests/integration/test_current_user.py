from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt  # type: ignore[import-untyped]
from sqlalchemy import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.v1.routers.accounts import router as accounts_router
from src.core.config import Settings
from src.database import get_db
from src.database.models import Base, UserGroupEnum, UserGroupModel, UserModel
from src.database.session_sqlite import create_sqlite_engine
from src.main import app
from src.schemas.accounts import UserResponseSchema
from src.security.dependencies import get_current_user
from src.security.passwords import hash_password
from src.security.tokens import JWTAuthManager, get_jwt_auth_manager


PROTECTED_URL = "/auth-check"
PASSWORD = "StrongPassword1!"
ACCESS_KEY = "test-access-key-for-current-user-only"


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(PASSWORD)


@pytest_asyncio.fixture
async def current_user_api(monkeypatch, password_hash):
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
            _hashed_password=password_hash, is_active=True,
        )
        db.add(user)
        await db.commit()
        user_id = user.id
        group_id = group.id

    manager = JWTAuthManager(Settings(
        _env_file=None,
        JWT_ACCESS_SECRET_KEY=ACCESS_KEY,
        JWT_REFRESH_SECRET_KEY="test-refresh-key-for-current-user-only",
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=15,
        REFRESH_TOKEN_EXPIRE_DAYS=7,
    ))

    async def override_db():
        async with sessions() as db:
            try:
                yield db
            except Exception:
                await db.rollback()
                raise

    test_app = FastAPI()
    test_app.include_router(accounts_router, prefix="/api/v1/accounts")

    @test_app.get(PROTECTED_URL, response_model=UserResponseSchema)
    async def protected_route(user: UserModel = Depends(get_current_user)):
        return user

    monkeypatch.setitem(test_app.dependency_overrides, get_db, override_db)
    monkeypatch.setitem(
        test_app.dependency_overrides, get_jwt_auth_manager, lambda: manager,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test",
        ) as client:
            yield client, sessions, manager, user_id, group_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_login_access_token_returns_current_user(current_user_api):
    client, _, _, user_id, group_id = current_user_api
    login = await client.post("/api/v1/accounts/login/", json={
        "email": "user@example.com", "password": PASSWORD,
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    response = await client.get(PROTECTED_URL, headers={
        "Authorization": f"Bearer {token}",
    })
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id", "email", "is_active", "created_at", "updated_at", "group",
    }
    assert body["id"] == user_id
    assert body["email"] == "user@example.com"
    assert body["is_active"] is True
    assert body["group"] == {"id": group_id, "name": "user"}
    assert body["created_at"]
    assert body["updated_at"]
    assert PASSWORD not in response.text
    assert token not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [
    None, "", "Bearer", "Bearer ", "Basic abc", "Bearer invalid-token",
])
async def test_authentication_rejects_missing_or_malformed_credentials(
    current_user_api, authorization,
):
    client, _, _, _, _ = current_user_api
    headers = {}
    if authorization is not None:
        headers["Authorization"] = authorization
    response = await client.get(PROTECTED_URL, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
@pytest.mark.parametrize("token_case", [
    "expired", "wrong_key", "refresh", "wrong_type", "missing_sub",
    "unknown_user", "oversized_user_id",
])
async def test_authentication_rejects_invalid_tokens(
    current_user_api, token_case,
):
    client, _, manager, user_id, _ = current_user_api
    token = manager.create_access_token(user_id)
    payload = manager.decode_access_token(token)
    key = ACCESS_KEY
    if token_case == "expired":
        now = int(datetime.now(timezone.utc).timestamp())
        payload["iat"] = now - 120
        payload["exp"] = now - 60
    elif token_case == "wrong_key":
        key = "another-access-key-that-cannot-be-trusted"
    elif token_case == "wrong_type":
        payload["type"] = "refresh"
    elif token_case == "missing_sub":
        del payload["sub"]
    elif token_case == "unknown_user":
        payload["sub"] = str(user_id + 100)
    elif token_case == "oversized_user_id":
        payload["sub"] = str(2**63)

    if token_case == "refresh":
        token = manager.create_refresh_token(user_id)
    else:
        token = jwt.encode(payload, key, algorithm="HS256")

    response = await client.get(PROTECTED_URL, headers={
        "Authorization": f"Bearer {token}",
    })
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid or missing access token."}


@pytest.mark.asyncio
@pytest.mark.parametrize("account_change", ["deactivate", "delete"])
async def test_authentication_checks_current_account_state(
    current_user_api, account_change,
):
    client, sessions, manager, user_id, _ = current_user_api
    token = manager.create_access_token(user_id)
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        if account_change == "delete":
            await db.delete(user)
        else:
            user.is_active = False
        await db.commit()

    response = await client.get(PROTECTED_URL, headers={
        "Authorization": f"Bearer {token}",
    })
    if account_change == "delete":
        assert response.status_code == 401
    else:
        assert response.status_code == 403
        assert response.json() == {"detail": "Your account is not active."}


@pytest.mark.asyncio
async def test_authentication_database_failure(current_user_api, monkeypatch):
    client, _, manager, user_id, _ = current_user_api
    error = OperationalError("private database details", {}, Exception())
    monkeypatch.setattr(
        AsyncSession, "execute", AsyncMock(side_effect=error),
    )
    response = await client.get(PROTECTED_URL, headers={
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    })
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Authentication is temporarily unavailable.",
    }


@pytest.mark.asyncio
async def test_accounts_me_is_not_available():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/accounts/me")
    assert response.status_code == 404
    assert "/api/v1/accounts/me" not in app.openapi()["paths"]

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from jose import jwt  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RefreshTokenModel, UserModel
from src.main import app


REFRESH_URL = "/api/v1/accounts/token/refresh/"
LOGOUT_URL = "/api/v1/accounts/logout/"


@pytest_asyncio.fixture
async def refresh_session(login_api):
    client, sessions, manager, user_id = login_api
    token = manager.create_refresh_token(user_id)
    payload = manager.decode_refresh_token(token)
    async with sessions() as db:
        db.add(RefreshTokenModel(
            user_id=user_id, token=token,
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        ))
        await db.commit()
    return client, sessions, manager, user_id, token


@pytest.mark.asyncio
async def test_login_refresh_logout_lifecycle(login_api):
    client, sessions, manager, user_id = login_api
    login = await client.post("/api/v1/accounts/login/", json={
        "email": "user@example.com", "password": "StrongPassword1!",
    })
    assert login.status_code == 200
    pair = login.json()
    token_data = {"refresh_token": pair["refresh_token"]}

    async with sessions() as db:
        original = await db.scalar(select(RefreshTokenModel))
        original_expiry = original.expires_at
        original_id = original.id

    response = await client.post(REFRESH_URL, json=token_data)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    body = response.json()
    assert set(body) == {"access_token", "token_type"}
    assert body["token_type"] == "bearer"
    assert body["access_token"] != pair["access_token"]
    payload = manager.decode_access_token(body["access_token"])
    assert payload["sub"] == str(user_id)
    assert payload["exp"] - payload["iat"] == 15 * 60

    repeated = await client.post(REFRESH_URL, json=token_data)
    assert repeated.status_code == 200
    assert repeated.json()["access_token"] != body["access_token"]
    async with sessions() as db:
        records = (await db.scalars(select(RefreshTokenModel))).all()
        assert len(records) == 1
        assert records[0].id == original_id
        assert records[0].token == pair["refresh_token"]
        assert records[0].expires_at == original_expiry

    logout = await client.post(LOGOUT_URL, json=token_data)
    assert logout.status_code == 200
    assert logout.json() == {"message": "Logged out successfully."}
    async with sessions() as db:
        assert await db.scalar(select(RefreshTokenModel)) is None
    assert (await client.post(REFRESH_URL, json=token_data)).status_code == 401
    assert (await client.post(LOGOUT_URL, json=token_data)).status_code == 401
    # Logout revokes refresh, not the already issued access JWT.
    manager.decode_access_token(body["access_token"])


@pytest.mark.asyncio
async def test_logout_does_not_affect_other_sessions(refresh_session):
    client, sessions, manager, user_id, token = refresh_session
    other_token = manager.create_refresh_token(user_id)
    payload = manager.decode_refresh_token(other_token)
    async with sessions() as db:
        db.add(RefreshTokenModel(
            user_id=user_id, token=other_token,
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        ))
        await db.commit()

    response = await client.post(LOGOUT_URL, json={"refresh_token": token})
    assert response.status_code == 200
    response = await client.post(
        REFRESH_URL, json={"refresh_token": other_token},
    )
    assert response.status_code == 200
    async with sessions() as db:
        records = (await db.scalars(select(RefreshTokenModel))).all()
        assert [record.token for record in records] == [other_token]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REFRESH_URL, LOGOUT_URL])
@pytest.mark.parametrize("token_case", [
    "malformed", "access", "expired", "wrong_key", "wrong_type", "not_saved",
])
async def test_rejects_invalid_refresh_jwt(
    refresh_session, path, token_case,
):
    client, sessions, manager, user_id, token = refresh_session
    candidate = token
    if token_case == "malformed":
        candidate = "not-a-jwt"
    elif token_case == "access":
        candidate = manager.create_access_token(user_id)
    elif token_case == "not_saved":
        candidate = manager.create_refresh_token(user_id)
    else:
        payload = manager.decode_refresh_token(token)
        key = "test-refresh-key-for-login-endpoint-only"
        if token_case == "expired":
            now = int(datetime.now(timezone.utc).timestamp())
            payload["iat"] = now - 120
            payload["exp"] = now - 60
        elif token_case == "wrong_type":
            payload["type"] = "access"
        else:
            key = "a-different-key-for-negative-test-only"
        candidate = jwt.encode(payload, key, algorithm="HS256")

    # Even a stored token must pass JWT validation, not just a database lookup.
    stored_token = token
    if token_case != "not_saved":
        async with sessions() as db:
            record = await db.scalar(select(RefreshTokenModel))
            record.token = candidate
            await db.commit()
        stored_token = candidate

    response = await client.post(path, json={"refresh_token": candidate})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired refresh token."}
    assert response.headers["www-authenticate"] == "Bearer"
    async with sessions() as db:
        record = await db.scalar(select(RefreshTokenModel))
        assert record.token == stored_token


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REFRESH_URL, LOGOUT_URL])
@pytest.mark.parametrize("record_case", ["expired", "wrong_user", "deleted"])
async def test_rejects_invalid_refresh_record(
    refresh_session, path, record_case,
):
    client, sessions, _, user_id, token = refresh_session
    async with sessions() as db:
        record = await db.scalar(select(RefreshTokenModel))
        if record_case == "expired":
            record.expires_at = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            )
        elif record_case == "deleted":
            await db.delete(record)
        else:
            user = await db.get(UserModel, user_id)
            other_user = UserModel(
                email="other@example.com", group_id=user.group_id,
                _hashed_password="unused-test-hash", is_active=True,
            )
            db.add(other_user)
            await db.flush()
            record.user_id = other_user.id
        await db.commit()

    response = await client.post(path, json={"refresh_token": token})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired refresh token."}
    async with sessions() as db:
        records = (await db.scalars(select(RefreshTokenModel))).all()
        assert len(records) == (0 if record_case == "deleted" else 1)


@pytest.mark.asyncio
async def test_inactive_user_cannot_refresh_but_can_logout(refresh_session):
    client, sessions, _, user_id, token = refresh_session
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()

    response = await client.post(REFRESH_URL, json={"refresh_token": token})
    assert response.status_code == 403
    assert response.json() == {"detail": "Your account is not active."}
    response = await client.post(LOGOUT_URL, json={"refresh_token": token})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_deleted_user_cannot_refresh(refresh_session):
    client, sessions, _, user_id, token = refresh_session
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        await db.delete(user)
        await db.commit()
    response = await client.post(REFRESH_URL, json={"refresh_token": token})
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REFRESH_URL, LOGOUT_URL])
@pytest.mark.parametrize("payload", [
    {}, {"refresh_token": ""}, {"refresh_token": "a b"},
    {"refresh_token": "a" * 256}, {"refresh_token": None},
    {"refresh_token": "token", "user_id": 1},
])
async def test_request_validation(refresh_session, path, payload):
    client, sessions, _, _, token = refresh_session
    response = await client.post(path, json=payload)
    assert response.status_code == 422
    async with sessions() as db:
        assert (await db.scalar(select(RefreshTokenModel))).token == token


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REFRESH_URL, LOGOUT_URL])
@pytest.mark.parametrize("failure_point", ["query", "commit"])
async def test_database_errors_preserve_session(
    refresh_session, monkeypatch, path, failure_point,
):
    client, sessions, _, _, token = refresh_session
    error = OperationalError("private database details", {}, Exception())

    async def fail_commit(db):
        # Flush the DELETE first to verify that rollback restores the record.
        await db.flush()
        raise error

    with monkeypatch.context() as patch:
        if failure_point == "query":
            patch.setattr(
                AsyncSession, "execute", AsyncMock(side_effect=error),
            )
        else:
            patch.setattr(AsyncSession, "commit", fail_commit)
        response = await client.post(path, json={"refresh_token": token})

    assert response.status_code == 503
    message = "Token refresh" if path == REFRESH_URL else "Logout"
    assert response.json() == {
        "detail": f"{message} is temporarily unavailable.",
    }
    async with sessions() as db:
        assert (await db.scalar(select(RefreshTokenModel))).token == token


@pytest.mark.parametrize("path,schema_name", [
    (REFRESH_URL, "TokenRefreshRequestSchema"),
    (LOGOUT_URL, "LogoutRequestSchema"),
])
def test_openapi_contract(path, schema_name):
    operation = app.openapi()["paths"][path]["post"]
    assert {"200", "401", "422", "503"} <= operation["responses"].keys()
    assert not operation.get("security")
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith(f"/{schema_name}")

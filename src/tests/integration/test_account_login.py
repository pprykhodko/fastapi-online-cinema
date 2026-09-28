from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RefreshTokenModel, UserModel
from src.main import app


LOGIN_URL = "/api/v1/accounts/login/"
PASSWORD = "StrongPassword1!"


@pytest.mark.asyncio
async def test_login_returns_jwts_and_saves_refresh_token(login_api):
    client, sessions, manager, user_id = login_api
    response = await client.post(LOGIN_URL, json={
        "email": "USER@EXAMPLE.COM", "password": PASSWORD
    })
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    body = response.json()
    assert set(body) == {"access_token", "refresh_token", "token_type"}
    assert body["token_type"] == "bearer"
    assert PASSWORD not in response.text

    access = manager.decode_access_token(body["access_token"])
    refresh = manager.decode_refresh_token(body["refresh_token"])
    assert access["sub"] == refresh["sub"] == str(user_id)
    assert access["exp"] - access["iat"] == 15 * 60
    assert refresh["exp"] - refresh["iat"] == 7 * 24 * 60 * 60
    async with sessions() as db:
        records = (await db.scalars(select(RefreshTokenModel))).all()
        assert len(records) == 1
        assert records[0].token == body["refresh_token"]
        assert records[0].user_id == user_id
        assert records[0].expires_at.replace(tzinfo=timezone.utc) == (
            datetime.fromtimestamp(refresh["exp"], tz=timezone.utc)
        )


@pytest.mark.asyncio
async def test_repeated_login_creates_independent_sessions(login_api):
    client, sessions, manager, _ = login_api
    responses = [await client.post(LOGIN_URL, json={
        "email": "user@example.com", "password": PASSWORD
    }) for _ in range(2)]
    assert all(response.status_code == 200 for response in responses)
    bodies = [response.json() for response in responses]
    assert bodies[0]["access_token"] != bodies[1]["access_token"]
    assert bodies[0]["refresh_token"] != bodies[1]["refresh_token"]
    async with sessions() as db:
        records = (await db.scalars(select(RefreshTokenModel))).all()
        assert {record.token for record in records} == {
            body["refresh_token"] for body in bodies
        }
        for record in records:
            manager.decode_refresh_token(record.token)


@pytest.mark.asyncio
@pytest.mark.parametrize("email,password,active,expected_status", [
    ("unknown@example.com", PASSWORD, True, 401),
    ("user@example.com", "WrongPassword1!", True, 401),
    ("user@example.com", "x", True, 401),
    ("user@example.com", "WrongPassword1!", False, 401),
    ("user@example.com", PASSWORD, False, 403)
])
async def test_login_rejects_invalid_credentials_or_inactive_account(
        login_api, email, password, active, expected_status
):
    client, sessions, _, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = active
        await db.commit()

    response = await client.post(LOGIN_URL, json={
        "email": email, "password": password
    })
    assert response.status_code == expected_status
    if expected_status == 401:
        assert response.json() == {"detail": "Incorrect email or password"}
        assert response.headers["www-authenticate"] == "Bearer"
    else:
        assert response.json() == {
            "detail": "Activate your account before logging in"
        }
    async with sessions() as db:
        assert await db.scalar(select(RefreshTokenModel)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {},
    {"email": "user@example.com"},
    {"password": PASSWORD},
    {"email": "invalid", "password": PASSWORD},
    {"email": "user@example.com", "password": ""},
    {"email": "user@example.com", "password": "a" * 73},
    {"email": "user@example.com", "password": "я" * 37},
    {"email": "user@example.com", "password": "null\u0000byte"},
    {"email": "user@example.com", "password": None},
    {"email": "user@example.com", "password": PASSWORD, "is_active": True}
])
async def test_login_validates_request(login_api, payload):
    client, sessions, _, _ = login_api
    response = await client.post(LOGIN_URL, json=payload)
    assert response.status_code == 422
    async with sessions() as db:
        assert await db.scalar(select(RefreshTokenModel)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["query", "commit"])
async def test_login_database_failure_does_not_save_token(
        login_api, monkeypatch, failure_point
):
    client, sessions, _, _ = login_api
    error = OperationalError("private database details", {}, Exception())

    async def fail_commit(db):
        # The INSERT succeeds, but the transaction must still be rolled back.
        await db.flush()
        raise error

    with monkeypatch.context() as patch:
        if failure_point == "query":
            patch.setattr(
                AsyncSession, "execute", AsyncMock(side_effect=error)
            )
        else:
            patch.setattr(AsyncSession, "commit", fail_commit)
        response = await client.post(LOGIN_URL, json={
            "email": "user@example.com", "password": PASSWORD
        })

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Login is temporarily unavailable. Please try again later."
    }
    async with sessions() as db:
        assert await db.scalar(select(RefreshTokenModel)) is None


def test_login_is_documented_in_openapi():
    operation = app.openapi()["paths"][LOGIN_URL]["post"]
    assert operation["summary"] == "Log in to an activated account"
    assert {"200", "401", "403", "422", "503"} <= (
        operation["responses"].keys()
    )
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/UserLoginRequestSchema")

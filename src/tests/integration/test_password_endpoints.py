from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    PasswordResetTokenModel, RefreshTokenModel, UserModel,
)
from src.main import app
from src.notifications.queue import EmailQueueError, EmailQueue
from src.security.utils import hash_reset_token


PREFIX = "/api/v1/accounts"
CHANGE = f"{PREFIX}/password/change/"
FORGOT = f"{PREFIX}/password/forgot/"
RESET = f"{PREFIX}/password/reset/"
OLD_PASSWORD = "StrongPassword1!"
NEW_PASSWORD = "AnotherPassword2!"


@pytest.fixture
def reset_email(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(EmailQueue, "send_password_reset_email", send)
    return send


async def create_reset_token(sessions, user_id, *, expired=False):
    async with sessions() as db:
        db.add(PasswordResetTokenModel(
            user_id=user_id, token=hash_reset_token("reset-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(
                hours=-1 if expired else 1,
            ),
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_change_password_revokes_tokens_and_updates_login(login_api):
    client, sessions, manager, user_id = login_api
    login = await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": OLD_PASSWORD,
    })
    pair = login.json()
    await create_reset_token(sessions, user_id)

    response = await client.patch(CHANGE, json={
        "old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD,
    }, headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert response.status_code == 200
    assert response.json() == {
        "message": "Password changed successfully. Please log in again.",
    }
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        assert user.verify_password(NEW_PASSWORD)
        assert not user.verify_password(OLD_PASSWORD)
        assert user._hashed_password != NEW_PASSWORD
        assert await db.scalar(select(RefreshTokenModel)) is None
        assert await db.scalar(select(PasswordResetTokenModel)) is None
    assert (await client.post(f"{PREFIX}/token/refresh/", json={
        "refresh_token": pair["refresh_token"],
    })).status_code == 401
    assert (await client.post(RESET, json={
        "token": "reset-token", "new_password": OLD_PASSWORD,
    })).status_code == 400
    assert (await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": OLD_PASSWORD,
    })).status_code == 401
    assert (await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": NEW_PASSWORD,
    })).status_code == 200
    manager.decode_access_token(pair["access_token"])


@pytest.mark.asyncio
@pytest.mark.parametrize("old,new,status_code", [
    ("WrongPassword1!", NEW_PASSWORD, 400),
    (OLD_PASSWORD, OLD_PASSWORD, 400),
    (OLD_PASSWORD, "weak", 422),
])
async def test_change_rejects_bad_passwords(login_api, old, new, status_code):
    client, sessions, manager, user_id = login_api
    await create_reset_token(sessions, user_id)
    response = await client.patch(CHANGE, json={
        "old_password": old, "new_password": new,
    }, headers={
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    })
    assert response.status_code == status_code
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
        assert await db.scalar(select(PasswordResetTokenModel)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_case", ["missing", "refresh", "inactive"])
async def test_change_requires_active_user(login_api, auth_case):
    client, sessions, manager, user_id = login_api
    headers = {}
    if auth_case == "refresh":
        headers["Authorization"] = (
            f"Bearer {manager.create_refresh_token(user_id)}"
        )
    elif auth_case == "inactive":
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            user.is_active = False
            await db.commit()
        headers["Authorization"] = (
            f"Bearer {manager.create_access_token(user_id)}"
        )
    response = await client.patch(CHANGE, headers=headers, json={
        "old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == (403 if auth_case == "inactive" else 401)


@pytest.mark.asyncio
async def test_reset_password_full_flow(login_api, reset_email):
    client, sessions, _, user_id = login_api
    await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": OLD_PASSWORD,
    })
    response = await client.post(FORGOT, json={"email": "USER@example.com"})
    assert response.status_code == 202
    email, token, expires_at = reset_email.call_args.args
    assert email == "user@example.com"
    assert token not in response.text
    assert len(token) == 64
    assert datetime.now(timezone.utc) + timedelta(hours=23) < expires_at
    async with sessions() as db:
        reset_token = await db.scalar(select(PasswordResetTokenModel))
        assert reset_token.token == hash_reset_token(token)
        assert reset_token.token != token
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
        assert await db.scalar(select(RefreshTokenModel)) is not None

    response = await client.post(RESET, json={
        "token": token, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 200
    assert NEW_PASSWORD not in response.text
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(NEW_PASSWORD)
        assert await db.scalar(select(PasswordResetTokenModel)) is None
        assert await db.scalar(select(RefreshTokenModel)) is None
    assert (await client.post(RESET, json={
        "token": token, "new_password": OLD_PASSWORD,
    })).status_code == 400
    assert (await client.post(f"{PREFIX}/login/", json={
        "email": email, "password": NEW_PASSWORD,
    })).status_code == 200


@pytest.mark.asyncio
async def test_reset_rejects_current_password_without_consuming_tokens(
    login_api, reset_email,
):
    client, sessions, _, user_id = login_api
    login = await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": OLD_PASSWORD,
    })
    refresh_token = login.json()["refresh_token"]
    await client.post(FORGOT, json={"email": "user@example.com"})
    token = reset_email.call_args.args[1]
    async with sessions() as db:
        original_hash = (await db.get(UserModel, user_id))._hashed_password
        original_expiry = (
            await db.scalar(select(PasswordResetTokenModel))
        ).expires_at

    response = await client.post(RESET, json={
        "token": token, "new_password": OLD_PASSWORD,
    })
    assert response.status_code == 400
    assert response.json() == {
        "detail": "New password must differ from the current password",
    }
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        assert user._hashed_password == original_hash
        reset_record = await db.scalar(select(PasswordResetTokenModel))
        assert reset_record.token == hash_reset_token(token)
        assert reset_record.expires_at == original_expiry
        refresh_record = await db.scalar(select(RefreshTokenModel))
        assert refresh_record.token == refresh_token

    response = await client.post(RESET, json={
        "token": token, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 200
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(NEW_PASSWORD)
        assert await db.scalar(select(PasswordResetTokenModel)) is None
        assert await db.scalar(select(RefreshTokenModel)) is None
    old_login = await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": OLD_PASSWORD,
    })
    assert old_login.status_code == 401


@pytest.mark.asyncio
async def test_reset_unknown_inactive_and_active_have_same_response(
    login_api, reset_email,
):
    client, sessions, _, user_id = login_api
    unknown = await client.post(FORGOT, json={"email": "unknown@example.com"})
    reset_email.assert_not_awaited()
    active = await client.post(FORGOT, json={"email": "user@example.com"})
    reset_email.assert_awaited_once()
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()
    inactive = await client.post(FORGOT, json={"email": "user@example.com"})
    assert unknown.status_code == active.status_code == 202
    assert inactive.status_code == 202
    assert unknown.json() == active.json() == inactive.json()
    reset_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_reset_request_replaces_old_token(login_api, reset_email):
    client, sessions, _, _ = login_api
    await client.post(FORGOT, json={"email": "user@example.com"})
    old_token = reset_email.call_args.args[1]
    await client.post(FORGOT, json={"email": "user@example.com"})
    new_token = reset_email.call_args.args[1]
    assert old_token != new_token
    async with sessions() as db:
        tokens = (await db.scalars(select(PasswordResetTokenModel))).all()
        assert len(tokens) == 1
        assert tokens[0].token == hash_reset_token(new_token)
    response = await client.post(RESET, json={
        "token": old_token, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["unknown", "expired", "inactive", "deleted"])
async def test_reset_rejects_invalid_token_or_account(login_api, case):
    client, sessions, _, user_id = login_api
    await create_reset_token(sessions, user_id, expired=case == "expired")
    if case in {"inactive", "deleted"}:
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            if case == "inactive":
                user.is_active = False
            else:
                await db.delete(user)
            await db.commit()
    response = await client.post(RESET, json={
        "token": "unknown-token" if case == "unknown" else "reset-token",
        "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Invalid or expired password reset token",
    }


@pytest.mark.asyncio
async def test_reset_email_failure_can_be_retried(
    login_api, monkeypatch, caplog,
):
    client, sessions, _, user_id = login_api
    enqueue = AsyncMock(side_effect=EmailQueueError("private broker error"))
    monkeypatch.setattr(EmailQueue, "_enqueue", enqueue)
    response = await client.post(FORGOT, json={"email": "user@example.com"})
    assert response.status_code == 202
    assert "private" not in response.text
    assert "Password reset email could not be queued" in caplog.text
    assert "private broker error" not in caplog.text
    assert "user@example.com" not in caplog.text
    assert enqueue.call_args.args[2]["token"] not in caplog.text
    async with sessions() as db:
        old_token = (await db.scalar(select(PasswordResetTokenModel))).token
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
    enqueue.side_effect = None
    response = await client.post(FORGOT, json={"email": "user@example.com"})
    assert response.status_code == 202
    assert hash_reset_token(enqueue.call_args.args[2]["token"]) != old_token


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [CHANGE, FORGOT, RESET])
@pytest.mark.parametrize("failure_point", ["query", "commit"])
async def test_password_database_errors_are_atomic(
    login_api, reset_email, monkeypatch, path, failure_point,
):
    client, sessions, manager, user_id = login_api
    await create_reset_token(sessions, user_id)
    await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": OLD_PASSWORD,
    })
    payloads = {
        CHANGE: {"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        FORGOT: {"email": "user@example.com"},
        RESET: {"token": "reset-token", "new_password": NEW_PASSWORD},
    }
    error = OperationalError("private SQL error", {}, Exception())

    async def fail_commit(db):
        await db.flush()
        raise error

    with monkeypatch.context() as patch:
        if failure_point == "commit":
            patch.setattr(AsyncSession, "commit", fail_commit)
        else:
            patch.setattr(
                AsyncSession, "execute", AsyncMock(side_effect=error),
            )
        response = await client.request(
            "PATCH" if path == CHANGE else "POST",
            path, json=payloads[path], headers={
                "Authorization": (
                    f"Bearer {manager.create_access_token(user_id)}"
                ),
            },
        )
    assert response.status_code == 503
    assert "private" not in response.text
    reset_email.assert_not_awaited()
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
        assert await db.scalar(select(RefreshTokenModel)) is not None
        reset_token = await db.scalar(select(PasswordResetTokenModel))
        assert reset_token.token == hash_reset_token("reset-token")


@pytest.mark.asyncio
@pytest.mark.parametrize("path,payload", [
    (FORGOT, {}), (FORGOT, {"email": "invalid"}),
    (RESET, {"token": "reset-token", "new_password": "weak"}),
    (RESET, {"token": "", "new_password": NEW_PASSWORD}),
    (RESET, {"token": "reset-token"}),
])
async def test_password_request_validation(login_api, path, payload):
    client, _, _, _ = login_api
    assert (await client.post(path, json=payload)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,expected", [
    ("GET", CHANGE, 405), ("GET", FORGOT, 405), ("GET", RESET, 405),
    ("POST", CHANGE, 405), ("PATCH", RESET, 405),
    ("GET", f"{PREFIX}/password/reset/confirm/", 404),
    ("POST", f"{PREFIX}/password/reset/confirm/", 404),
    ("POST", f"{PREFIX}/password/reset/confirm/form/", 404),
])
async def test_only_agreed_password_routes_exist(
    login_api, method, path, expected,
):
    client, _, _, _ = login_api
    response = await client.request(method, path)
    assert response.status_code == expected


def test_password_openapi_contract():
    paths = app.openapi()["paths"]
    password_paths = {
        path: set(operations) for path, operations in paths.items()
        if path.startswith(f"{PREFIX}/password/")
    }
    assert password_paths == {
        CHANGE: {"patch"}, FORGOT: {"post"}, RESET: {"post"},
    }
    assert paths[CHANGE]["patch"]["security"] == [{"HTTPBearer": []}]
    for path in (FORGOT, RESET):
        assert not paths[path]["post"].get("security")
    assert "202" in paths[FORGOT]["post"]["responses"]


@pytest.mark.asyncio
async def test_stored_reset_hash_cannot_be_used_as_token(
    login_api, reset_email,
):
    client, sessions, _, user_id = login_api
    await client.post(FORGOT, json={"email": "user@example.com"})
    token = reset_email.call_args.args[1]
    response = await client.post(RESET, json={
        "token": hash_reset_token(token), "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 400
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
        assert await db.scalar(select(PasswordResetTokenModel)) is not None


@pytest.mark.asyncio
async def test_email_is_queued_after_token_commit_before_response(
    login_api, monkeypatch,
):
    client, sessions, _, _ = login_api
    response_sent = False

    async def check_email(email, token, expires_at):
        assert not response_sent
        async with sessions() as db:
            record = await db.scalar(select(PasswordResetTokenModel))
            assert record.token == hash_reset_token(token)

    send_email = AsyncMock(side_effect=check_email)
    monkeypatch.setattr(EmailQueue, "send_password_reset_email", send_email)
    original_app = client._transport.app

    async def observe_response(scope, receive, send):
        async def track_send(message):
            nonlocal response_sent
            if message["type"] == "http.response.body":
                response_sent = not message.get("more_body", False)
            await send(message)
        await original_app(scope, receive, track_send)

    monkeypatch.setattr(client._transport, "app", observe_response)
    response = await client.post(FORGOT, json={"email": "user@example.com"})
    assert response.status_code == 202
    send_email.assert_awaited_once()

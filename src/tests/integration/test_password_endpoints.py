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
from src.notifications.emails import EmailDeliveryError, EmailSender


PREFIX = "/api/v1/accounts"
CHANGE = f"{PREFIX}/password/change/"
RESET = f"{PREFIX}/password/reset/"
CONFIRM = f"{PREFIX}/password/reset/confirm/"
FORM = f"{CONFIRM}form/"
OLD_PASSWORD = "StrongPassword1!"
NEW_PASSWORD = "AnotherPassword2!"


@pytest.fixture(autouse=True)
def reset_email(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(EmailSender, "send_password_reset_email", send)
    return send


async def create_reset_token(sessions, user_id, *, expired=False):
    async with sessions() as db:
        db.add(PasswordResetTokenModel(
            user_id=user_id, token="reset-token",
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

    response = await client.post(CHANGE, json={
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
    assert (await client.post(CONFIRM, json={
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
    response = await client.post(CHANGE, json={
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
    response = await client.post(CHANGE, headers=headers, json={
        "old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == (403 if auth_case == "inactive" else 401)


@pytest.mark.asyncio
async def test_reset_password_full_flow(login_api, reset_email):
    client, sessions, _, user_id = login_api
    await client.post(f"{PREFIX}/login/", json={
        "email": "user@example.com", "password": OLD_PASSWORD,
    })
    response = await client.post(RESET, json={"email": "USER@example.com"})
    assert response.status_code == 200
    email, token, expires_at = reset_email.call_args.args
    assert email == "user@example.com"
    assert token not in response.text
    assert len(token) == 64
    assert datetime.now(timezone.utc) + timedelta(hours=23) < expires_at
    async with sessions() as db:
        reset_token = await db.scalar(select(PasswordResetTokenModel))
        assert reset_token.token == token
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
        assert await db.scalar(select(RefreshTokenModel)) is not None

    response = await client.post(CONFIRM, json={
        "token": token, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 200
    assert NEW_PASSWORD not in response.text
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(NEW_PASSWORD)
        assert await db.scalar(select(PasswordResetTokenModel)) is None
        assert await db.scalar(select(RefreshTokenModel)) is None
    assert (await client.post(CONFIRM, json={
        "token": token, "new_password": OLD_PASSWORD,
    })).status_code == 400
    assert (await client.post(f"{PREFIX}/login/", json={
        "email": email, "password": NEW_PASSWORD,
    })).status_code == 200


@pytest.mark.asyncio
async def test_reset_unknown_inactive_and_active_have_same_response(
    login_api, reset_email,
):
    client, sessions, _, user_id = login_api
    unknown = await client.post(RESET, json={"email": "unknown@example.com"})
    reset_email.assert_not_awaited()
    active = await client.post(RESET, json={"email": "user@example.com"})
    reset_email.assert_awaited_once()
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()
    inactive = await client.post(RESET, json={"email": "user@example.com"})
    assert unknown.status_code == active.status_code == 200
    assert inactive.status_code == 200
    assert unknown.json() == active.json() == inactive.json()
    reset_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_reset_request_replaces_old_link(login_api, reset_email):
    client, sessions, _, _ = login_api
    await client.post(RESET, json={"email": "user@example.com"})
    old_token = reset_email.call_args.args[1]
    await client.post(RESET, json={"email": "user@example.com"})
    new_token = reset_email.call_args.args[1]
    assert old_token != new_token
    async with sessions() as db:
        tokens = (await db.scalars(select(PasswordResetTokenModel))).all()
        assert len(tokens) == 1
        assert tokens[0].token == new_token
    response = await client.post(CONFIRM, json={
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
    response = await client.post(CONFIRM, json={
        "token": "unknown-token" if case == "unknown" else "reset-token",
        "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Invalid or expired password reset token.",
    }


@pytest.mark.asyncio
async def test_reset_email_failure_can_be_retried(login_api, reset_email):
    client, sessions, _, user_id = login_api
    reset_email.side_effect = EmailDeliveryError("private SMTP error")
    response = await client.post(RESET, json={"email": "user@example.com"})
    assert response.status_code == 503
    assert "private" not in response.text
    async with sessions() as db:
        old_token = (await db.scalar(select(PasswordResetTokenModel))).token
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
    reset_email.side_effect = None
    response = await client.post(RESET, json={"email": "user@example.com"})
    assert response.status_code == 200
    assert reset_email.call_args.args[1] != old_token


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [CHANGE, RESET, CONFIRM])
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
        RESET: {"email": "user@example.com"},
        CONFIRM: {"token": "reset-token", "new_password": NEW_PASSWORD},
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
        response = await client.post(path, json=payloads[path], headers={
            "Authorization": f"Bearer {manager.create_access_token(user_id)}",
        })
    assert response.status_code == 503
    assert "private" not in response.text
    reset_email.assert_not_awaited()
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
        assert await db.scalar(select(RefreshTokenModel)) is not None
        reset_token = await db.scalar(select(PasswordResetTokenModel))
        assert reset_token.token == "reset-token"


@pytest.mark.asyncio
@pytest.mark.parametrize("path,payload", [
    (RESET, {}), (RESET, {"email": "invalid"}),
    (CONFIRM, {"token": "reset-token", "new_password": "weak"}),
    (CONFIRM, {"token": "", "new_password": NEW_PASSWORD}),
    (CONFIRM, {"token": "reset-token"}),
])
async def test_password_request_validation(login_api, path, payload):
    client, _, _, _ = login_api
    assert (await client.post(path, json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_reset_form_get_is_safe_and_post_resets_password(login_api):
    client, sessions, _, user_id = login_api
    await create_reset_token(sessions, user_id)
    page = await client.get(CONFIRM, params={"token": "reset-token"})
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert f'action="{FORM}"' in page.text
    assert "<script" not in page.text
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)
        assert await db.scalar(select(PasswordResetTokenModel)) is not None
    response = await client.post(FORM, data={
        "token": "reset-token", "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Password reset successfully" in response.text
    assert NEW_PASSWORD not in response.text
    assert "reset-token" not in response.text
    assert "<form" not in response.text
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(NEW_PASSWORD)


@pytest.mark.asyncio
@pytest.mark.parametrize("token,password,expected", [
    ("reset-token", "weak", 422), ("unknown-token", NEW_PASSWORD, 400),
])
async def test_reset_form_errors_do_not_echo_password(
    login_api, token, password, expected,
):
    client, sessions, _, user_id = login_api
    await create_reset_token(sessions, user_id)
    response = await client.post(FORM, data={
        "token": token, "new_password": password,
    })
    assert response.status_code == expected
    assert 'role="alert"' in response.text
    assert password not in response.text
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).verify_password(OLD_PASSWORD)


@pytest.mark.asyncio
async def test_reset_form_escapes_token(login_api):
    client, _, _, _ = login_api
    response = await client.get(CONFIRM, params={
        "token": '\"><script>alert(1)</script>',
    })
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_password_openapi_contract():
    paths = app.openapi()["paths"]
    assert paths[CHANGE]["post"]["security"] == [{"HTTPBearer": []}]
    for path in (RESET, CONFIRM):
        assert not paths[path]["post"].get("security")
    assert FORM not in paths
    assert "get" not in paths[CONFIRM]

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    ActivationTokenModel, UserGroupEnum, UserGroupModel, UserModel
)
from src.main import app
from src.notifications.queue import EmailQueueError, EmailQueue
from src.repositories.accounts import AccountRepository
from src.repositories.tokens import TokenRepository


PREFIX = "/api/v1/accounts"


@pytest.fixture(autouse=True)
def confirmation_email(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(EmailQueue, "send_activation_complete_email", send)
    return send


@pytest_asyncio.fixture
async def admin_api(login_api, password_hash):
    client, sessions, manager, admin_id = login_api
    async with sessions() as db:
        user_group = await db.scalar(select(UserGroupModel))
        admin_group = UserGroupModel(name=UserGroupEnum.ADMIN)
        moderator_group = UserGroupModel(name=UserGroupEnum.MODERATOR)
        db.add_all([admin_group, moderator_group])
        await db.flush()
        admin = await db.get(UserModel, admin_id)
        admin.group_id = admin_group.id
        target = UserModel(
            email="target@example.com", group_id=user_group.id,
            _hashed_password=password_hash, is_active=False
        )
        db.add(target)
        await db.commit()
        groups = {
            "user": user_group.id,
            "moderator": moderator_group.id,
            "admin": admin_group.id
        }
        return client, sessions, manager, admin_id, target.id, groups


@pytest.fixture
def admin_headers(admin_api):
    _, _, manager, admin_id, _, _ = admin_api
    return {"Authorization": f"Bearer {manager.create_access_token(admin_id)}"}


async def send_admin_request(
        client, action, user_id, headers, group="moderator"
):
    if action == "group":
        return await client.patch(
            f"{PREFIX}/{user_id}/group/",
            headers=headers, json={"group": group}
        )
    return await client.post(f"{PREFIX}/{user_id}/activate/", headers=headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["user", "moderator", "admin"])
async def test_admin_changes_group(admin_api, admin_headers, group):
    client, sessions, _, _, target_id, groups = admin_api
    response = await send_admin_request(
        client, "group", target_id, admin_headers, group
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == target_id
    assert body["group"] == {"id": groups[group], "name": group}
    assert body["is_active"] is False
    assert set(body) == {
        "id", "email", "is_active", "created_at", "updated_at", "group"
    }
    async with sessions() as db:
        target = await db.get(UserModel, target_id)
        assert target.group_id == groups[group]
        assert not target.is_active
    repeated = await send_admin_request(
        client, "group", target_id, admin_headers, group
    )
    assert repeated.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["group", "activate"])
@pytest.mark.parametrize("role", ["user", "moderator"])
async def test_non_admin_cannot_manage_accounts(
        admin_api, admin_headers, confirmation_email, action, role
):
    client, sessions, _, admin_id, target_id, groups = admin_api
    async with sessions() as db:
        actor = await db.get(UserModel, admin_id)
        actor.group_id = groups[role]
        await db.commit()
    response = await send_admin_request(
        client, action, target_id, admin_headers
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Administrator access is required"}
    async with sessions() as db:
        target = await db.get(UserModel, target_id)
        assert target.group_id == groups["user"]
        assert not target.is_active
    confirmation_email.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["group", "activate"])
@pytest.mark.parametrize("auth_case", [
    "missing", "invalid", "refresh", "inactive", "deleted"
])
async def test_admin_operations_require_active_authenticated_account(
        admin_api, admin_headers, confirmation_email, action, auth_case
):
    client, sessions, manager, admin_id, target_id, _ = admin_api
    headers = admin_headers
    if auth_case == "missing":
        headers = {}
    elif auth_case == "invalid":
        headers = {"Authorization": "Bearer invalid-token"}
    elif auth_case == "refresh":
        headers = {
            "Authorization": (
                f"Bearer {manager.create_refresh_token(admin_id)}"
            )
        }
    else:
        async with sessions() as db:
            actor = await db.get(UserModel, admin_id)
            if auth_case == "inactive":
                actor.is_active = False
            else:
                await db.delete(actor)
            await db.commit()
    response = await send_admin_request(client, action, target_id, headers)
    assert response.status_code == (403 if auth_case == "inactive" else 401)
    confirmation_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_role_changes_apply_to_existing_access_tokens(
        admin_api, admin_headers
):
    client, sessions, manager, admin_id, target_id, _ = admin_api
    async with sessions() as db:
        target = await db.get(UserModel, target_id)
        target.is_active = True
        await db.commit()
    target_headers = {
        "Authorization": f"Bearer {manager.create_access_token(target_id)}"
    }
    denied = await send_admin_request(
        client, "group", admin_id, target_headers, "user"
    )
    assert denied.status_code == 403
    promoted = await send_admin_request(
        client, "group", target_id, admin_headers, "admin"
    )
    assert promoted.status_code == 200
    demoted = await send_admin_request(
        client, "group", admin_id, target_headers, "user"
    )
    assert demoted.status_code == 200
    denied_again = await send_admin_request(
        client, "group", target_id, admin_headers, "user"
    )
    assert denied_again.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["group", "activate"])
async def test_admin_target_not_found(
        admin_api, admin_headers, confirmation_email, action
):
    client, _, _, _, _, _ = admin_api
    response = await send_admin_request(client, action, 9999, admin_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}
    confirmation_email.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("token_state", ["valid", "expired", "missing"])
async def test_admin_activation_does_not_require_valid_token(
        admin_api, admin_headers, confirmation_email, token_state
):
    client, sessions, _, _, target_id, _ = admin_api
    if token_state != "missing":
        async with sessions() as db:
            db.add(ActivationTokenModel(
                user_id=target_id, token="old-activation-token",
                expires_at=datetime.now(timezone.utc) + timedelta(
                    hours=-1 if token_state == "expired" else 1
                )
            ))
            await db.commit()
    response = await send_admin_request(
        client, "activate", target_id, admin_headers
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Account activated successfully"}
    confirmation_email.assert_awaited_once_with("target@example.com")
    async with sessions() as db:
        assert (await db.get(UserModel, target_id)).is_active
        assert await db.scalar(select(ActivationTokenModel)) is None
    repeated = await send_admin_request(
        client, "activate", target_id, admin_headers
    )
    assert repeated.status_code == 409
    confirmation_email.assert_awaited_once()
    old_token_response = await client.post(f"{PREFIX}/activate/", json={
        "token": "old-activation-token"
    })
    assert old_token_response.status_code == 400
    login = await client.post(f"{PREFIX}/login/", json={
        "email": "target@example.com", "password": "StrongPassword1!"
    })
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_admin_activation_survives_email_failure(
        admin_api, admin_headers, confirmation_email
):
    client, sessions, _, _, target_id, _ = admin_api
    confirmation_email.side_effect = EmailQueueError("private SMTP details")
    response = await send_admin_request(
        client, "activate", target_id, admin_headers
    )
    assert response.status_code == 200
    assert response.json() == {"message": (
        "Account activated successfully, but the confirmation "
        "email could not be queued"
    )}
    async with sessions() as db:
        assert (await db.get(UserModel, target_id)).is_active


@pytest.mark.asyncio
async def test_missing_group_is_configuration_error(admin_api, admin_headers):
    client, sessions, _, _, target_id, groups = admin_api
    async with sessions() as db:
        await db.execute(delete(UserGroupModel).where(
            UserGroupModel.id == groups["moderator"]
        ))
        await db.commit()
    response = await send_admin_request(
        client, "group", target_id, admin_headers
    )
    assert response.status_code == 503
    async with sessions() as db:
        assert (await db.get(UserModel, target_id)).group_id == groups["user"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["group", "activate"])
@pytest.mark.parametrize("failure_point", ["query", "commit"])
async def test_admin_database_failure_does_not_leave_partial_changes(
        admin_api, admin_headers, confirmation_email, monkeypatch,
        action, failure_point
):
    client, sessions, _, _, target_id, groups = admin_api
    async with sessions() as db:
        db.add(ActivationTokenModel(
            user_id=target_id, token="activation-token"
        ))
        await db.commit()
    error = OperationalError("private SQL details", {}, Exception())

    async def fail_commit(db):
        await db.flush()
        raise error

    with monkeypatch.context() as patch:
        if failure_point == "commit":
            patch.setattr(AsyncSession, "commit", fail_commit)
        else:
            method = (
                "get_group_by_name" if action == "group"
                else "get_user_activation_token"
            )
            patch.setattr(
                AccountRepository if action == "group" else TokenRepository,
                method, AsyncMock(side_effect=error)
            )
        response = await send_admin_request(
            client, action, target_id, admin_headers
        )
    assert response.status_code == 503
    assert "private" not in response.text
    confirmation_email.assert_not_awaited()
    async with sessions() as db:
        target = await db.get(UserModel, target_id)
        assert target.group_id == groups["user"]
        assert not target.is_active
        assert await db.scalar(select(ActivationTokenModel)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["group", "activate"])
@pytest.mark.parametrize("user_id", [0, -1, "invalid", 2**63])
async def test_admin_user_id_validation(
        admin_api, admin_headers, action, user_id
):
    client, _, _, _, _, _ = admin_api
    response = await send_admin_request(client, action, user_id, admin_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {}, {"group": "unknown"}, {"group": "ADMIN"}, {"group": None},
    {"group": "admin", "is_active": True}
])
async def test_admin_group_validation(admin_api, admin_headers, payload):
    client, sessions, _, _, target_id, groups = admin_api
    response = await client.patch(
        f"{PREFIX}/{target_id}/group/", headers=admin_headers, json=payload
    )
    assert response.status_code == 422
    async with sessions() as db:
        assert (await db.get(UserModel, target_id)).group_id == groups["user"]


def test_admin_openapi_and_no_account_read_endpoints():
    paths = app.openapi()["paths"]
    for suffix, method in [("group", "patch"), ("activate", "post")]:
        path = f"{PREFIX}/{{user_id}}/{suffix}/"
        assert set(paths[path]) == {method}
        operation = paths[path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert {"200", "401", "403", "404", "422", "503"} <= set(
            operation["responses"]
        )
    assert f"{PREFIX}/" not in paths
    assert f"{PREFIX}/{{user_id}}/" not in paths

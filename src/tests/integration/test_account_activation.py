from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.database import get_db
from src.database.models import (
    ActivationTokenModel,
    Base,
    CartModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel
)
from src.database.session_sqlite import create_sqlite_engine
from src.main import app
from src.notifications.queue import EmailQueueError, EmailQueue
from src.repositories.accounts import AccountRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.cart import CartRepository
from src.repositories.tokens import TokenRepository


PREFIX = "/api/v1/accounts"


@pytest.fixture
def completion_email(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(EmailQueue, "send_activation_complete_email", send)
    return send


@pytest_asyncio.fixture
async def activation_api(monkeypatch, completion_email):
    engine = create_sqlite_engine(URL.create("sqlite+aiosqlite", database=":memory:"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        db.add(UserGroupModel(id=42, name=UserGroupEnum.USER))
        await db.commit()

    async def override_db():
        async with sessions() as db:
            try:
                yield db
            except Exception:
                await db.rollback()
                raise

    send_email = AsyncMock()
    monkeypatch.setattr(EmailQueue, "send_activation_email", send_email)
    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    try:
        async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
        ) as client:
            yield client, sessions, send_email
    finally:
        await engine.dispose()


async def create_account(sessions, *, active=False, expires_at=None):
    async with sessions() as db:
        user = UserModel(
            email="user@example.com",
            group_id=42,
            _hashed_password="unused-test-hash",
            is_active=active
        )
        db.add(user)
        await db.flush()
        if expires_at is not None:
            db.add(
                ActivationTokenModel(
                    user_id=user.id,
                    token="original-token",
                    expires_at=expires_at
                )
            )
        await db.commit()
        return user.id


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "GET"])
async def test_registration_email_activation_and_replay(
        activation_api,
        completion_email,
        method
):
    client, sessions, send_email = activation_api
    response = await client.post(
        f"{PREFIX}/register/",
        json={
            "email": "User@Example.com",
            "password": "StrongPassword1!"
        }
    )
    assert response.status_code == 201
    completion_email.assert_not_awaited()
    user_id = response.json()["id"]
    email, token, expires_at = send_email.call_args.args
    assert email == "user@example.com"
    assert len(token) == 64
    assert datetime.now(timezone.utc) + timedelta(hours=23) < expires_at
    assert token not in response.text
    async with sessions() as db:
        record = await db.scalar(select(ActivationTokenModel))
        cart = await db.scalar(select(CartModel))
        profile = await db.scalar(select(UserProfileModel))
        assert record.token == token
        assert record.user_id == cart.user_id == profile.user_id == user_id
        for field in (
                "first_name",
                "last_name",
                "avatar",
                "gender",
                "date_of_birth",
                "info"
        ):
            assert getattr(profile, field) is None
        profile_id = profile.id
    kwargs = {"json" if method == "POST" else "params": {"token": token}}
    response = await client.request(method, f"{PREFIX}/activate/", **kwargs)
    assert response.status_code == 200
    completion_email.assert_awaited_once_with("user@example.com")
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).is_active
        assert await db.scalar(select(ActivationTokenModel)) is None
        assert (await db.scalar(select(UserProfileModel))).id == profile_id
    response = await client.request(method, f"{PREFIX}/activate/", **kwargs)
    assert response.status_code == 400
    completion_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_registration_mail_failure_can_be_retried(activation_api):
    client, sessions, send_email = activation_api
    send_email.side_effect = EmailQueueError("private SMTP failure")
    response = await client.post(
        f"{PREFIX}/register/",
        json={
            "email": "user@example.com",
            "password": "StrongPassword1!"
        }
    )
    assert response.status_code == 503
    assert "Account created" in response.json()["detail"]
    assert "private" not in response.text
    token = send_email.call_args.args[1]
    async with sessions() as db:
        assert not (await db.scalar(select(UserModel))).is_active
        assert (await db.scalar(select(ActivationTokenModel))).token == token
        user = await db.scalar(select(UserModel))
        assert (await db.scalar(select(UserProfileModel))).user_id == user.id
    send_email.side_effect = None
    response = await client.post(
        f"{PREFIX}/activation/resend/",
        json={"email": "USER@example.com"}
    )
    assert response.status_code == 200
    assert send_email.call_args.args[1] == token


@pytest.mark.asyncio
async def test_registration_queues_email_after_all_records_are_committed(
        activation_api
):
    client, sessions, send_email = activation_api

    async def check_saved_records(email, token, expires_at):
        async with sessions() as db:
            user = await db.scalar(select(UserModel).where(UserModel.email == email))
            assert user is not None
            for model in (UserProfileModel, CartModel, ActivationTokenModel):
                record = await db.scalar(select(model).where(model.user_id == user.id))
                assert record is not None
            assert record.token == token

    send_email.side_effect = check_saved_records
    response = await client.post(
        f"{PREFIX}/register/",
        json={
            "email": "user@example.com",
            "password": "StrongPassword1!"
        }
    )
    assert response.status_code == 201
    send_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_registration_does_not_add_profile(activation_api):
    client, sessions, send_email = activation_api
    data = {"email": "user@example.com", "password": "StrongPassword1!"}
    response = await client.post(f"{PREFIX}/register/", json=data)
    assert response.status_code == 201
    response = await client.post(f"{PREFIX}/register/", json=data)
    assert response.status_code == 409
    async with sessions() as db:
        assert len((await db.scalars(select(UserProfileModel))).all()) == 1
    send_email.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "profile_insert",
        "cart_insert",
        "token_insert",
        "after_flush"
    ]
)
async def test_registration_related_records_failure_rolls_back(
        activation_api,
        monkeypatch,
        failure
):
    client, sessions, send_email = activation_api
    if failure == "profile_insert":

        def add_duplicate_profile(self, user_id):
            self.db.add_all(
                [
                    UserProfileModel(user_id=user_id),
                    UserProfileModel(user_id=user_id)
                ]
            )

        monkeypatch.setattr(
            ProfileRepository,
            "add_profile",
            add_duplicate_profile
        )
        expected_status = 500
    elif failure in {"cart_insert", "token_insert"}:

        def fail_insert(self, value):
            raise OperationalError("insert failed", {}, Exception())

        repository, method = (
            (CartRepository, "add_cart")
            if failure == "cart_insert"
            else (TokenRepository, "add_activation_token")
        )
        monkeypatch.setattr(repository, method, fail_insert)
        expected_status = 503
    else:

        async def fail_commit(self):
            await self.db.flush()
            raise OperationalError("commit failed", {}, Exception())

        monkeypatch.setattr(AccountRepository, "commit", fail_commit)
        expected_status = 503

    response = await client.post(
        f"{PREFIX}/register/",
        json={
            "email": "user@example.com",
            "password": "StrongPassword1!"
        }
    )
    assert response.status_code == expected_status
    send_email.assert_not_awaited()
    async with sessions() as db:
        for model in (
                UserModel,
                UserProfileModel,
                CartModel,
                ActivationTokenModel
        ):
            assert await db.scalar(select(model)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [True, False, None])
async def test_resend_replaces_only_expired_or_missing_token(
        activation_api,
        expired
):
    client, sessions, send_email = activation_api
    now = datetime.now(timezone.utc)
    expiry = (
        None
        if expired is None
        else now
        + timedelta(
            hours=-1 if expired else 1
        )
    )
    user_id = await create_account(sessions, expires_at=expiry)
    response = await client.post(
        f"{PREFIX}/activation/resend/",
        json={"email": "User@Example.com"}
    )
    assert response.status_code == 200
    async with sessions() as db:
        records = (await db.scalars(select(ActivationTokenModel))).all()
        assert len(records) == 1
        token = records[0]
        assert token.user_id == user_id
        assert send_email.call_args.args[1] == token.token
        expires_at = token.expires_at.replace(tzinfo=timezone.utc)
        if expired is False:
            assert token.token == "original-token"
            assert expires_at == expiry
        else:
            assert token.token != "original-token"
            assert now + timedelta(hours=24) <= expires_at
            assert expires_at <= (datetime.now(timezone.utc) + timedelta(hours=24))
    if expired:
        response = await client.post(
            f"{PREFIX}/activate/",
            json={"token": "original-token"}
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_unknown_and_active_accounts_get_same_response(activation_api):
    client, sessions, send_email = activation_api
    unknown = await client.post(
        f"{PREFIX}/activation/resend/",
        json={"email": "user@example.com"}
    )
    await create_account(sessions, active=True)
    active = await client.post(
        f"{PREFIX}/activation/resend/",
        json={"email": "user@example.com"}
    )
    assert unknown.status_code == active.status_code == 200
    assert unknown.json() == active.json()
    send_email.assert_not_awaited()
    async with sessions() as db:
        assert await db.scalar(select(ActivationTokenModel)) is None


@pytest.mark.asyncio
async def test_resend_mail_failure_preserves_new_token(activation_api):
    client, sessions, send_email = activation_api
    await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    send_email.side_effect = EmailQueueError("private failure")
    response = await client.post(
        f"{PREFIX}/activation/resend/",
        json={"email": "user@example.com"}
    )
    assert response.status_code == 503
    assert "private" not in response.text
    token = send_email.call_args.args[1]
    assert token != "original-token"
    send_email.side_effect = None
    response = await client.post(
        f"{PREFIX}/activation/resend/",
        json={"email": "user@example.com"}
    )
    assert response.status_code == 200
    assert send_email.call_args.args[1] == token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "bad"},
        {
            "email": "user@example.com",
            "is_active": True
        }
    ]
)
async def test_resend_rejects_invalid_input(activation_api, payload):
    client, _, send_email = activation_api
    response = await client.post(f"{PREFIX}/activation/resend/", json=payload)
    assert response.status_code == 422
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_resend_commit_failure_rolls_back(activation_api, monkeypatch):
    client, sessions, send_email = activation_api
    expiry = datetime.now(timezone.utc) - timedelta(hours=1)
    await create_account(sessions, expires_at=expiry)
    async with sessions() as failing_db:

        async def override_db():
            yield failing_db

        async def failing_commit():
            await failing_db.flush()
            raise OperationalError("test", {}, Exception("private failure"))

        monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
        monkeypatch.setattr(failing_db, "commit", failing_commit)
        response = await client.post(
            f"{PREFIX}/activation/resend/",
            json={"email": "user@example.com"}
        )
        assert response.status_code == 503
        assert "private" not in response.text
    send_email.assert_not_awaited()
    async with sessions() as db:
        token = await db.scalar(select(ActivationTokenModel))
        assert token.token == "original-token"
        assert token.expires_at.replace(tzinfo=timezone.utc) == expiry


@pytest.mark.asyncio
async def test_activation_page_get_activates_without_form(activation_api):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    response = await client.get(
        f"{PREFIX}/activate/",
        params={"token": "original-token"}
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "original-token" not in response.text
    assert "<form" not in response.text
    assert "<button" not in response.text
    assert "<script" not in response.text
    assert "Account activated successfully" in response.text
    assert "You can close this page." in response.text
    assert "form-action 'none'" in response.headers["content-security-policy"]
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).is_active
        assert await db.scalar(select(ActivationTokenModel)) is None


@pytest.mark.asyncio
async def test_activation_page_does_not_render_token(activation_api):
    client, _, _ = activation_api
    token = '\"><script>alert(1)</script>'
    response = await client.get(f"{PREFIX}/activate/", params={"token": token})
    assert response.status_code == 400
    assert token not in response.text
    assert "<script" not in response.text
    assert "&lt;script&gt;" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "active, hours, status_code",
    [
        (False, -1, 400),
        (False, 0, 400),
        (True, 1, 409)
    ]
)
async def test_activation_rejects_expired_or_active_account(
        activation_api,
        completion_email,
        active,
        hours,
        status_code
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        active=active,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours)
    )
    response = await client.post(
        f"{PREFIX}/activate/",
        json={"token": "original-token"}
    )
    assert response.status_code == status_code
    completion_email.assert_not_awaited()
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).is_active == active
        assert await db.scalar(select(ActivationTokenModel)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, payload",
    [
        ("/activation/resend/", {"email": "user@example.com"}),
        ("/activate/", {"token": "original-token"})
    ]
)
async def test_activation_database_errors_are_safe(
        activation_api,
        monkeypatch,
        path,
        payload
):
    client, sessions, send_email = activation_api
    async with sessions() as db:

        async def broken_db():
            yield db

        monkeypatch.setitem(app.dependency_overrides, get_db, broken_db)
        monkeypatch.setattr(
            db,
            "execute",
            AsyncMock(
                side_effect=(OperationalError("test", {}, Exception("private failure")))
            )
        )
        response = await client.post(f"{PREFIX}{path}", json=payload)
    assert response.status_code == 503
    assert "private" not in response.text
    send_email.assert_not_awaited()


def test_activation_openapi_contract():
    paths = app.openapi()["paths"]
    assert "get" in paths[f"{PREFIX}/activate/"]
    assert "post" in paths[f"{PREFIX}/activate/"]
    resend = paths[f"{PREFIX}/activation/resend/"]["post"]
    assert set(resend["responses"]) == {"200", "422", "503"}
    schema = resend["requestBody"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/ActivationResendRequestSchema")
    assert f"{PREFIX}/activate/confirm/" not in paths
    activation = paths[f"{PREFIX}/activate/"]
    assert set(activation) == {"get", "post"}
    assert "application/json" in activation["post"]["requestBody"]["content"]
    assert "text/html" in activation["get"]["responses"]["200"]["content"]


@pytest.mark.asyncio
async def test_confirmation_mail_failure_does_not_undo_activation(
        activation_api,
        completion_email
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    completion_email.side_effect = EmailQueueError("private failure")
    response = await client.post(
        f"{PREFIX}/activate/",
        json={"token": "original-token"}
    )
    assert response.status_code == 200
    assert "confirmation email could not be queued" in response.json()["message"]
    assert "private" not in response.text
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).is_active
        assert await db.scalar(select(ActivationTokenModel)) is None


@pytest.mark.asyncio
async def test_confirmation_email_is_sent_after_commit(
        activation_api,
        completion_email
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )

    async def check_saved_account(email):
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            assert user.email == email
            assert user.is_active
            assert await db.scalar(select(ActivationTokenModel)) is None

    completion_email.side_effect = check_saved_account
    response = await client.post(
        f"{PREFIX}/activate/",
        json={"token": "original-token"}
    )
    assert response.status_code == 200
    completion_email.assert_awaited_once_with("user@example.com")


@pytest.mark.asyncio
async def test_activation_commit_failure_does_not_send_confirmation(
        activation_api,
        completion_email,
        monkeypatch
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    async with sessions() as db:

        async def broken_db():
            yield db

        async def failing_commit():
            await db.flush()
            raise OperationalError("test", {}, Exception("private failure"))

        monkeypatch.setitem(app.dependency_overrides, get_db, broken_db)
        monkeypatch.setattr(db, "commit", failing_commit)
        response = await client.post(
            f"{PREFIX}/activate/",
            json={"token": "original-token"}
        )
    assert response.status_code == 503
    completion_email.assert_not_awaited()
    async with sessions() as db:
        assert not (await db.get(UserModel, user_id)).is_active
        assert await db.scalar(select(ActivationTokenModel)) is not None


@pytest.mark.asyncio
async def test_link_activation_returns_html_and_prevents_replay(
        activation_api,
        completion_email
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    response = await client.get(
        f"{PREFIX}/activate/",
        params={"token": "original-token"}
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Account activated successfully" in response.text
    assert "You can close this page." in response.text
    assert "<script" not in response.text
    assert "<form" not in response.text
    assert "original-token" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    completion_email.assert_awaited_once_with("user@example.com")
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).is_active
        assert await db.scalar(select(ActivationTokenModel)) is None

    response = await client.get(
        f"{PREFIX}/activate/",
        params={"token": "original-token"}
    )
    assert response.status_code == 400
    assert "invalid or expired" in response.text
    assert "You can close this page." not in response.text
    completion_email.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "active, hours, expected_status",
    [
        (False, -1, 400),
        (True, 1, 409)
    ]
)
async def test_link_activation_returns_html_errors(
        activation_api,
        completion_email,
        active,
        hours,
        expected_status
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        active=active,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours)
    )
    response = await client.get(
        f"{PREFIX}/activate/",
        params={"token": "original-token"}
    )
    assert response.status_code == expected_status
    assert "text/html" in response.headers["content-type"]
    assert 'role="alert"' in response.text
    assert "Account activated successfully" not in response.text
    completion_email.assert_not_awaited()
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).is_active == active


@pytest.mark.asyncio
async def test_link_activation_reports_confirmation_email_failure(
        activation_api,
        completion_email
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    completion_email.side_effect = EmailQueueError("private failure")
    response = await client.get(
        f"{PREFIX}/activate/",
        params={"token": "original-token"}
    )
    assert response.status_code == 200
    assert "confirmation email could not be queued" in response.text
    assert "You can close this page." in response.text
    assert "private failure" not in response.text
    async with sessions() as db:
        assert (await db.get(UserModel, user_id)).is_active


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"token": "a b"},
        {
            "token": "x" * 256
        }
    ]
)
async def test_link_activation_validates_input(
        activation_api,
        completion_email,
        payload
):
    client, _, _ = activation_api
    response = await client.get(f"{PREFIX}/activate/", params=payload)
    assert response.status_code == 422
    completion_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_activation_confirm_endpoint_is_removed(activation_api):
    client, _, _ = activation_api
    response = await client.post(
        f"{PREFIX}/activate/confirm/",
        data={"token": "original-token"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_link_activation_database_failure_returns_html(
        activation_api,
        completion_email,
        monkeypatch
):
    client, sessions, _ = activation_api
    user_id = await create_account(
        sessions,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    async with sessions() as db:

        async def failing_db():
            try:
                yield db
            except Exception:
                await db.rollback()
                raise

        async def fail_commit():
            await db.flush()
            raise OperationalError("private SQL", {}, Exception())

        monkeypatch.setitem(app.dependency_overrides, get_db, failing_db)
        monkeypatch.setattr(db, "commit", fail_commit)
        response = await client.get(
            f"{PREFIX}/activate/",
            params={"token": "original-token"}
        )
    assert response.status_code == 503
    assert "text/html" in response.headers["content-type"]
    assert 'role="alert"' in response.text
    assert "private" not in response.text
    assert "<button" not in response.text
    completion_email.assert_not_awaited()
    async with sessions() as db:
        assert not (await db.get(UserModel, user_id)).is_active
        assert await db.scalar(select(ActivationTokenModel)) is not None

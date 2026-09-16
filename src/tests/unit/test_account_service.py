from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, create_autospec

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from src.database.models import (
    ActivationTokenModel, UserGroupEnum, UserGroupModel, UserModel,
)
from src.notifications.emails import EmailSender
from src.repositories.accounts import AccountRepository
from src.schemas.accounts import (
    AccountActivationRequestSchema, ActivationResendRequestSchema,
    UserRegistrationRequestSchema,
)
from src.services.accounts import AccountService


@pytest.fixture
def repository():
    return create_autospec(AccountRepository, instance=True)


@pytest.fixture
def email_sender():
    return create_autospec(EmailSender, instance=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    "duplicate", "missing_group", "database", "conflict", "integrity",
])
async def test_registration_errors(repository, email_sender, failure):
    repository.get_user_by_email.return_value = None
    repository.get_default_group.return_value = UserGroupModel(
        id=1, name=UserGroupEnum.USER,
    )
    user = UserModel(id=1, email="user@example.com", group_id=1)
    expected_status = 503
    if failure == "duplicate":
        repository.get_user_by_email.return_value = user
        expected_status = 409
    elif failure == "missing_group":
        repository.get_default_group.return_value = None
    elif failure == "database":
        repository.get_user_by_email.side_effect = OperationalError(
            "private details", {}, Exception(),
        )
    else:
        repository.add_user.side_effect = IntegrityError(
            "private details", {}, Exception(),
        )
        if failure == "conflict":
            repository.get_user_by_email.side_effect = [None, user]
            expected_status = 409
        else:
            expected_status = 500

    data = UserRegistrationRequestSchema(
        email="user@example.com", password="StrongPassword1!",
    )
    with pytest.raises(HTTPException) as error:
        await AccountService(repository, email_sender).register_user(data)

    assert error.value.status_code == expected_status
    assert "private details" not in error.value.detail
    repository.commit.assert_not_awaited()
    email_sender.send_activation_email.assert_not_awaited()
    if failure in {"database", "conflict", "integrity"}:
        repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_activation_rejects_token_without_user(repository, email_sender):
    repository.get_activation_token.return_value = ActivationTokenModel(
        user_id=1, token="activation-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    repository.get_user_by_id.return_value = None
    with pytest.raises(HTTPException) as error:
        await AccountService(repository, email_sender).activate_account(
            AccountActivationRequestSchema(token="activation-token"),
        )
    assert error.value.status_code == 400
    repository.delete_activation_token.assert_not_awaited()
    repository.commit.assert_not_awaited()
    email_sender.send_activation_complete_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_resend_rechecks_activation_after_lock(repository, email_sender):
    user = UserModel(id=1, email="user@example.com", is_active=False)
    repository.get_user_by_email.return_value = user

    async def activate_before_refresh(account):
        account.is_active = True

    repository.refresh_user = AsyncMock(side_effect=activate_before_refresh)
    service = AccountService(repository, email_sender)
    response = await service.resend_activation_link(
        ActivationResendRequestSchema(email=user.email),
    )
    assert response.message.startswith("If an inactive account exists")
    repository.commit.assert_not_awaited()
    email_sender.send_activation_email.assert_not_awaited()


@pytest.mark.parametrize("seconds, expected", [
    (-1, True), (0, True), (1, False),
])
@pytest.mark.parametrize("token_timezone", [
    None, timezone.utc, timezone(timedelta(hours=3)),
])
def test_token_expiration_handles_boundary_and_timezone(
    seconds, expected, token_timezone,
):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    expires_at = now + timedelta(seconds=seconds)
    if token_timezone is None:
        expires_at = expires_at.replace(tzinfo=None)
    else:
        expires_at = expires_at.astimezone(token_timezone)

    assert AccountService.is_token_expired(expires_at, now) is expected

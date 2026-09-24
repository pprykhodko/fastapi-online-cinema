import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from kombu.exceptions import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError

from src.notifications.queue import EmailQueue, EmailQueueError, get_email_queue
from src.notifications.emails import EmailDeliveryError, EmailSender
from src.tasks import emails


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["activation", "activation_complete", "password_reset", "comment"])
async def test_queue_serializes_data_without_sending_smtp(monkeypatch, kind):
    publish = Mock()
    smtp = AsyncMock()
    monkeypatch.setattr(emails.send_email, "apply_async", publish)
    monkeypatch.setattr(EmailSender, "_send_email", smtp)
    queue = get_email_queue()
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    if kind == "activation":
        await queue.send_activation_email("user@example.com", "secret-token", expiry)
    elif kind == "activation_complete":
        await queue.send_activation_complete_email("user@example.com")
    elif kind == "password_reset":
        await queue.send_password_reset_email("user@example.com", "secret-token", expiry)
    else:
        await queue.send_comment_notification("user@example.com", "Movie", 1, "reply")
    publish.assert_called_once()
    options = publish.call_args.kwargs
    assert options["args"][:2] == (kind, "user@example.com")
    json.dumps(options["args"])
    assert options["retry"] is False
    assert "secret-token" not in options["argsrepr"]
    smtp.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [OperationalError, RedisConnectionError, OSError])
async def test_queue_failure_is_translated(monkeypatch, error):
    monkeypatch.setattr(emails.send_email, "apply_async", Mock(side_effect=error("private")))
    with pytest.raises(EmailQueueError, match="could not be queued"):
        await EmailQueue().send_activation_complete_email("user@example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["password_reset", "comment"])
async def test_optional_queue_failure_is_logged_without_private_data(monkeypatch, caplog, kind):
    monkeypatch.setattr(emails.send_email, "apply_async", Mock(side_effect=OperationalError("private")))
    queue = EmailQueue()
    if kind == "password_reset":
        await queue.send_password_reset_email("user@example.com", "secret-token", datetime.now(timezone.utc))
    else:
        await queue.send_comment_notification("user@example.com", "Movie", 1, "like")
    assert "could not be queued" in caplog.text
    assert "private" not in caplog.text
    assert "user@example.com" not in caplog.text
    assert "secret-token" not in caplog.text


@pytest.mark.parametrize("kind,method,data", [
    ("activation", "send_activation_email", {"token": "secret-token"}),
    ("password_reset", "send_password_reset_email", {"token": "secret-token"}),
    ("activation_complete", "send_activation_complete_email", {}),
    ("comment", "send_comment_notification", {"movie_name": "Movie", "comment_id": 1, "event": "reply"}),
])
def test_worker_dispatches_email(monkeypatch, kind, method, data):
    sender = AsyncMock(spec=EmailSender)
    monkeypatch.setattr(emails, "get_email_sender", lambda: sender)
    payload = dict(data)
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    if "token" in payload:
        payload["expires_at"] = expiry.isoformat()
    emails.send_email.apply(args=(kind, "user@example.com", payload), throw=True)
    expected = ["user@example.com"]
    if "token" in payload:
        expected += ["secret-token", expiry]
    elif kind == "comment":
        expected += ["Movie", 1, "reply"]
    getattr(sender, method).assert_awaited_once_with(*expected)


@pytest.mark.parametrize("kind", ["activation", "password_reset"])
@pytest.mark.parametrize("aware", [True, False])
def test_worker_skips_expired_token(monkeypatch, kind, aware):
    sender = AsyncMock(spec=EmailSender)
    monkeypatch.setattr(emails, "get_email_sender", lambda: sender)
    expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
    if not aware:
        expiry = expiry.replace(tzinfo=None)
    emails.send_email.apply(args=(kind, "user@example.com", {
        "token": "old", "expires_at": expiry.isoformat(),
    }), throw=True)
    sender.send_activation_email.assert_not_awaited()
    sender.send_password_reset_email.assert_not_awaited()


@pytest.mark.parametrize("recover", [True, False])
def test_worker_retries_smtp_failure_with_limit(monkeypatch, recover):
    sender = AsyncMock(spec=EmailSender)
    error = EmailDeliveryError("The email could not be sent")
    sender.send_activation_complete_email.side_effect = [error, None] if recover else error
    monkeypatch.setattr(emails, "get_email_sender", lambda: sender)
    result = emails.send_email.apply(args=("activation_complete", "user@example.com", {}), throw=False)
    assert result.successful() is recover
    assert sender.send_activation_complete_email.await_count == (2 if recover else 4)
    assert emails.send_email.max_retries == 3
    assert emails.send_email.retry_backoff == 10


def test_worker_does_not_retry_programming_errors(monkeypatch):
    sender = AsyncMock(spec=EmailSender)
    sender.send_activation_complete_email.side_effect = ValueError("Invalid template")
    monkeypatch.setattr(emails, "get_email_sender", lambda: sender)
    result = emails.send_email.apply(args=("activation_complete", "user@example.com", {}), throw=False)
    assert result.failed()
    assert sender.send_activation_complete_email.await_count == 1


def test_worker_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown email kind"):
        emails.send_email.apply(args=("unknown", "user@example.com", {}), throw=True)


def test_email_task_is_registered_in_worker():
    assert "src.tasks.emails" in emails.celery_app.conf.include
    assert emails.celery_app.tasks["emails.send"] is emails.send_email._get_current_object()

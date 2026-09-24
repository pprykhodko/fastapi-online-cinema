from unittest.mock import AsyncMock

import pytest

from src.core.config import Settings
from src.notifications import emails


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["reply", "like"])
async def test_comment_email(monkeypatch, event):
    sender = emails.EmailSender(Settings(_env_file=None))
    send = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr(emails.aiosmtplib, "send", send)
    await sender.send_comment_notification(
        "author@example.com", "Movie <script>", 12, event,
    )
    message = send.call_args.args[0]
    assert message["To"] == "author@example.com"
    html = message.get_body(preferencelist=("html",)).get_content()
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert "<script>" not in html and "&lt;script&gt;" in html
    for body in (html, plain):
        assert "#12" in body
        assert f"received a {event}" in body


@pytest.mark.asyncio
async def test_email_failure_propagates_for_worker_retry(monkeypatch):
    sender = emails.EmailSender(Settings(_env_file=None))
    monkeypatch.setattr(emails.aiosmtplib, "send",
                        AsyncMock(side_effect=OSError("private")))
    with pytest.raises(emails.EmailDeliveryError):
        await sender.send_comment_notification(
            "author@example.com", "Movie", 1, "like",
        )

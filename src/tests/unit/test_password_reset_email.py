from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.config import Settings
from src.notifications import emails
from src.security.utils import hash_reset_token


def test_hash_reset_token_is_stable_sha256():
    assert hash_reset_token("abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
    assert hash_reset_token("abc") != hash_reset_token("abcd")


@pytest.mark.asyncio
@pytest.mark.parametrize("aware", [True, False])
async def test_password_reset_email_content(monkeypatch, aware):
    settings = Settings(_env_file=None)
    sender = emails.EmailSender(settings)
    send = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr(emails.aiosmtplib, "send", send)
    await sender.send_password_reset_email(
        "user@example.com", "token+with/symbols",
        datetime(2030, 1, 2, 12, tzinfo=timezone.utc if aware else None)
    )
    message = send.call_args.args[0]
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Reset your Online Cinema password"
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "<a " not in html
    assert "token+with/symbols" in html
    assert "token+with/symbols" in plain
    assert "2030-01-02 12:00:00 UTC" in html
    for body in (html, plain):
        assert "POST /api/v1/accounts/password/reset/" in body
        assert "new_password" in body
        assert "only once" in body


@pytest.mark.asyncio
async def test_password_reset_email_escapes_values(monkeypatch):
    sender = emails.EmailSender(Settings(_env_file=None))
    send = AsyncMock()
    monkeypatch.setattr(sender, "_send_email", send)
    await sender.send_password_reset_email(
        "<script>alert(1)</script>@example.com", "<token>",
        datetime.now(timezone.utc)
    )
    html = send.call_args.args[2]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<token>" not in html
    assert "&lt;token&gt;" in html

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
    settings = Settings(
        _env_file=None,
        PASSWORD_RESET_URL="http://localhost:8000/password-reset/"
    )
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
    assert "<a " in html
    link = "http://localhost:8000/password-reset/#token=token%2Bwith%2Fsymbols"
    assert link in html
    assert link in plain
    assert "2030-01-02 12:00:00 UTC" in html
    for body in (html, plain):
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
    assert "%3Ctoken%3E" in html


@pytest.mark.asyncio
async def test_reset_email_uses_configured_public_url(monkeypatch):
    sender = emails.EmailSender(Settings(
        _env_file=None,
        PASSWORD_RESET_URL="https://cinema.example.com/password-reset/"
    ))
    send = AsyncMock()
    monkeypatch.setattr(sender, "_send_email", send)
    await sender.send_password_reset_email(
        "user@example.com", "secret-token", datetime.now(timezone.utc)
    )
    link = "https://cinema.example.com/password-reset/#token=secret-token"
    assert link in send.call_args.args[2]
    assert link in send.call_args.args[3]

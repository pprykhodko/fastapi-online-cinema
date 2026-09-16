from datetime import datetime, timezone
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.core.config import Settings
from src.notifications import emails


@pytest.mark.asyncio
@pytest.mark.parametrize("aware", [True, False])
async def test_password_reset_email_content(monkeypatch, aware):
    settings = Settings(
        _env_file=None,
        PASSWORD_RESET_URL="https://cinema.example/reset/?lang=en",
    )
    sender = emails.EmailSender(settings)
    send = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr(emails.aiosmtplib, "send", send)
    await sender.send_password_reset_email(
        "user@example.com", "token+with/symbols",
        datetime(2030, 1, 2, 12, tzinfo=timezone.utc if aware else None),
    )
    message = send.call_args.args[0]
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Reset your Online Cinema password"
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "Choose a new password</a>" in html
    assert "2030-01-02 12:00:00 UTC" in html
    assert "token%2Bwith%2Fsymbols" in html
    assert "lang=en&amp;token=" in html
    link = next(
        line for line in plain.splitlines() if line.startswith("https:")
    )
    assert parse_qs(urlsplit(link).query) == {
        "lang": ["en"], "token": ["token+with/symbols"],
    }


@pytest.mark.asyncio
async def test_password_reset_email_escapes_values(monkeypatch):
    sender = emails.EmailSender(Settings(_env_file=None))
    send = AsyncMock()
    monkeypatch.setattr(sender, "_send_email", send)
    await sender.send_password_reset_email(
        "<script>alert(1)</script>@example.com", "token",
        datetime.now(timezone.utc),
    )
    html = send.call_args.args[2]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html

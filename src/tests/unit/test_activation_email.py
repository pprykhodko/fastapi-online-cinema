from datetime import datetime, timezone
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import aiosmtplib
import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.notifications import emails


@pytest.mark.asyncio
@pytest.mark.parametrize("aware", [True, False])
async def test_activation_email_content_and_smtp(monkeypatch, aware):
    settings = Settings(
        _env_file=None,
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=587,
        SMTP_USER="sender",
        SMTP_PASSWORD="secret",
        SMTP_START_TLS=True,
        ACCOUNT_ACTIVATION_URL="https://cinema.example/activate?lang=en"
    )
    monkeypatch.setattr(emails, "get_settings", lambda: settings)
    send = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr(emails.aiosmtplib, "send", send)
    expires_at = datetime(
        2030, 1, 2, 12, tzinfo=timezone.utc if aware else None
    )

    await emails.get_email_sender().send_activation_email(
        "user@example.com", "token+with/symbols", expires_at
    )

    message = send.call_args.args[0]
    body = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "user@example.com" in html
    assert "2030-01-02 12:00:00 UTC" in html
    assert "Activate your account</a>" in html
    assert "token%2Bwith%2Fsymbols" in html
    assert "lang=en&amp;token=" in html
    link = next(
        line for line in body.splitlines() if line.startswith("https:")
    )
    assert parse_qs(urlsplit(link).query) == {
        "lang": ["en"], "token": ["token+with/symbols"]
    }
    assert message["To"] == "user@example.com"
    assert message["From"] == "noreply@example.com"
    assert "2030-01-02 12:00:00 UTC" in body
    assert "secret" not in body
    assert send.call_args.kwargs == {
        "hostname": "smtp.example.com", "port": 587,
        "username": "sender", "password": "secret",
        "use_tls": False, "start_tls": True, "timeout": 10
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [aiosmtplib.SMTPException("private"), OSError(), TimeoutError()]
)
async def test_smtp_errors_are_wrapped(monkeypatch, error):
    monkeypatch.setattr(
        emails, "get_settings", lambda: Settings(_env_file=None)
    )
    monkeypatch.setattr(
        emails.aiosmtplib, "send", AsyncMock(side_effect=error)
    )
    with pytest.raises(emails.EmailDeliveryError):
        await emails.get_email_sender().send_activation_email(
            "user@example.com", "token", datetime.now(timezone.utc)
        )


def test_conflicting_tls_settings_are_rejected():
    with pytest.raises(ValidationError, match="Choose SMTP_USE_TLS"):
        Settings(_env_file=None, SMTP_USE_TLS=True, SMTP_START_TLS=True)


@pytest.mark.asyncio
async def test_activation_complete_email_content(monkeypatch):
    sender = emails.EmailSender(Settings(_env_file=None))
    send = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr(emails.aiosmtplib, "send", send)

    await sender.send_activation_complete_email("user@example.com")

    message = send.call_args.args[0]
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Your Online Cinema account is activated"
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "user@example.com" in plain
    assert "user@example.com" in html
    assert "Your account is activated!" in html
    assert "is now active" in plain
    assert "Activate your account</a>" not in html
    assert send.call_args.kwargs["username"] is None
    assert send.call_args.kwargs["password"] is None


@pytest.mark.asyncio
async def test_email_templates_escape_dynamic_values(monkeypatch):
    sender = emails.EmailSender(Settings(_env_file=None))
    send = AsyncMock()
    monkeypatch.setattr(sender, "_send_email", send)
    malicious_email = "<script>alert(1)</script>@example.com"
    await sender.send_activation_complete_email(malicious_email)
    html = send.call_args.args[2]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    await sender.send_activation_email(
        malicious_email, "token", datetime.now(timezone.utc)
    )
    html = send.call_args.args[2]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize("template_name", [
    "activation_request.html",
    "activation_complete.html",
    "password_reset_request.html"
])
def test_email_layout_is_self_contained_and_preserves_escaping(template_name):
    sender = emails.EmailSender(Settings(_env_file=None))
    html = sender._env.get_template(template_name).render(
        email="<script>alert(1)</script>@example.com",
        activation_link="https://cinema.example/activate/?token=example",
        token="test-reset-token",
        expires_at="2030-01-02 12:00:00 UTC"
    )
    assert '<meta name="viewport"' in html
    assert '<table role="presentation"' in html
    assert "Online Cinema" in html
    assert "Please do not reply." in html
    assert "&lt;script&gt;" in html
    assert "<script" not in html
    assert "<form" not in html
    assert "<link" not in html

from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.core.config import Settings, get_settings


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class EmailDeliveryError(Exception):
    pass


class EmailSender:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(["html"])
        )

    async def _send_email(
            self,
            recipient: str,
            subject: str,
            html_content: str,
            text_content: str
    ) -> None:
        message = EmailMessage()
        message["From"] = str(self._settings.SMTP_FROM_EMAIL)
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text_content)
        message.add_alternative(html_content, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.SMTP_HOST,
                port=self._settings.SMTP_PORT,
                username=self._settings.SMTP_USER or None,
                password=self._settings.SMTP_PASSWORD or None,
                use_tls=self._settings.SMTP_USE_TLS,
                start_tls=self._settings.SMTP_START_TLS,
                timeout=self._settings.SMTP_TIMEOUT
            )

        except (aiosmtplib.SMTPException, OSError, TimeoutError) as error:
            raise EmailDeliveryError("The email could not be sent") from error

    async def send_payment_confirmation(
            self,
            email: str,
            order_id: int,
            amount: str,
            currency: str
    ) -> None:
        html = self._env.get_template("payment_confirmation.html").render(
            order_id=order_id,
            amount=amount,
            currency=currency.upper()
        )
        await self._send_email(
            email, "Your Online Cinema payment is confirmed", html,
            f"Payment for order #{order_id} confirmed: {amount} {currency.upper()}. "
            f"Your movies are now in Purchased."
        )

    async def send_comment_notification(
            self, email: str,
            movie_name: str,
            comment_id: int,
            event: str
    ) -> None:
        action = "received a reply" if event == "reply" else "received a like"
        template = self._env.get_template("comment_notification.html")
        html_content = template.render(
            movie_name=movie_name,
            comment_id=comment_id,
            action=action
        )

        await self._send_email(
            email, "New activity on your Online Cinema comment",
            html_content,
            f'Your comment #{comment_id} on "{movie_name}" {action}'
        )

    async def send_activation_email(
            self,
            email: str,
            token: str,
            expires_at: datetime
    ) -> None:
        url_parts = urlsplit(str(self._settings.ACCOUNT_ACTIVATION_URL))
        query = dict(parse_qsl(url_parts.query))
        query["token"] = token
        activation_link = urlunsplit(url_parts._replace(query=urlencode(query)))

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        expiration = expires_at.astimezone(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

        template = self._env.get_template("activation_request.html")
        html_content = template.render(
            email=email,
            activation_link=activation_link,
            expires_at=expiration,
        )
        await self._send_email(
            email,
            "Activate your Online Cinema account",
            html_content,
            f"Welcome to Online Cinema!\n\n{activation_link}\n\n"
            f"This link expires at {expiration}.\n"
            "If you did not request this email, you can ignore it."
        )

    async def send_activation_complete_email(self, email: str) -> None:
        template = self._env.get_template("activation_complete.html")
        html_content = template.render(email=email)
        await self._send_email(
            email,
            "Your Online Cinema account is activated",
            html_content,
            f"Your Online Cinema account ({email}) is now active.\n"
            "Thank you for joining Online Cinema!"
        )

    async def send_password_reset_email(
            self,
            email: str,
            token: str,
            expires_at: datetime
    ) -> None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        expiration = expires_at.astimezone(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        template = self._env.get_template("password_reset_request.html")
        html_content = template.render(email=email, token=token, expires_at=expiration)
        await self._send_email(
            email,
            "Reset your Online Cinema password",
            html_content,
            f"Your password reset token:\n{token}\n\n"
            "Send token and new_password as JSON to "
            "POST /api/v1/accounts/password/reset/ using Swagger or Postman.\n"
            f"This token expires at {expiration} and can be used only once.\n"
            "If you did not request a reset, you can ignore this email."
        )


def get_email_sender() -> EmailSender:
    return EmailSender(get_settings())

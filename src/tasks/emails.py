import asyncio
from datetime import datetime, timezone

from src.core.celery_app import celery_app
from src.notifications.emails import EmailDeliveryError, get_email_sender


@celery_app.task(
    name="emails.send",
    autoretry_for=EmailDeliveryError,
    retry_backoff=10,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3
)
def send_email(kind: str, recipient: str, data: dict) -> None:
    asyncio.run(deliver_email(kind, recipient, data))


async def deliver_email(kind: str, recipient: str, data: dict) -> None:
    sender = get_email_sender()

    if kind in {"activation", "password_reset"}:
        expires_at = datetime.fromisoformat(data["expires_at"])

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= datetime.now(timezone.utc):
            return

        if kind == "activation":
            await sender.send_activation_email(recipient, data["token"], expires_at)

        else:
            await sender.send_password_reset_email(recipient, data["token"], expires_at)

    elif kind == "activation_complete":
        await sender.send_activation_complete_email(recipient)

    elif kind == "comment":
        await sender.send_comment_notification(
            recipient, data["movie_name"], data["comment_id"], data["event"],
        )

    else:
        raise ValueError("Unknown email kind")

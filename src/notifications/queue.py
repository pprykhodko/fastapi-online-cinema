import logging
from datetime import datetime
from functools import partial

from fastapi.concurrency import run_in_threadpool
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from src.tasks.emails import send_email


logger = logging.getLogger(__name__)


class EmailQueueError(Exception):
    pass


class EmailQueue:
    async def send_payment_confirmation(
            self,
            email: str,
            order_id: int,
            amount: str,
            currency: str
    ) -> None:
        """
        Queue a payment confirmation for later delivery by Celery.

        Args:
            email (str): Email address of the account or message recipient.
            order_id (int): ID of the order.
            amount (str): Monetary amount in major currency units, not cents.
            currency (str): Payment currency code, such as usd or eur.

        Raises:
            EmailQueueError: The broker cannot accept the email task.
        """
        await self._enqueue(
            "payment",
            email,
            {
                "order_id": order_id,
                "amount": amount,
                "currency": currency
            }
        )

    async def _enqueue(self, kind: str, email: str, data: dict) -> None:
        """
        Publish an email task without exposing its arguments in the Celery task
        representation.

        Args:
            kind (str): Email type: activation, activation_complete, password_reset,
                payment or comment.
            email (str): Email address of the account or message recipient.
            data (dict): Serializable email payload containing the fields required by
                this message type.

        Raises:
            EmailQueueError: The broker cannot accept the email task.
        """
        try:
            # celery-types omits argsrepr, which Celery supports via **options.
            publish = partial(  # type: ignore[call-arg]
                send_email.apply_async,
                args=(kind, email, data),
                argsrepr="<email arguments hidden>",
                retry=False
            )
            await run_in_threadpool(publish)

        except (OperationalError, RedisError, OSError):
            raise EmailQueueError("The email could not be queued")

    async def send_activation_email(
            self,
            email: str,
            token: str,
            expires_at: datetime
    ) -> None:
        """
        Queue an activation link for later delivery by Celery.

        Args:
            email (str): Email address of the account or message recipient.
            token (str): Plaintext token supplied by the caller; never log this value.
            expires_at (datetime): Expiration time; naive datetime values are
                interpreted as UTC.

        Raises:
            EmailQueueError: The broker cannot accept the email task.
        """
        await self._enqueue(
            "activation",
            email,
            {
                "token": token,
                "expires_at": expires_at.isoformat()
            }
        )

    async def send_activation_complete_email(self, email: str) -> None:
        """
        Queue an activation confirmation for later delivery by Celery.

        Args:
            email (str): Email address of the account or message recipient.

        Raises:
            EmailQueueError: The broker cannot accept the email task.
        """
        await self._enqueue("activation_complete", email, {})

    async def send_password_reset_email(
            self,
            email: str,
            token: str,
            expires_at: datetime
    ) -> None:
        """
        Queue a reset link for later delivery by Celery. Log and suppress queue failure.

        Args:
            email (str): Email address of the account or message recipient.
            token (str): Plaintext token supplied by the caller; never log this value.
            expires_at (datetime): Expiration time; naive datetime values are
                interpreted as UTC.
        """
        try:
            await self._enqueue(
                "password_reset",
                email,
                {
                    "token": token,
                    "expires_at": expires_at.isoformat()
                }
            )

        except EmailQueueError:
            logger.error("Password reset email could not be queued")

    async def send_comment_notification(
            self,
            email: str,
            movie_name: str,
            comment_id: int,
            event: str
    ) -> None:
        """
        Queue a comment notification for later delivery by Celery. Log and suppress
        queue failure.

        Args:
            email (str): Email address of the account or message recipient.
            movie_name (str): Movie title included in the notification.
            comment_id (int): ID of the comment.
            event (str): Comment activity type: reply or like.
        """
        try:
            await self._enqueue(
                "comment",
                email,
                {
                    "movie_name": movie_name,
                    "comment_id": comment_id,
                    "event": event
                }
            )

        except EmailQueueError:
            logger.error("Comment notification could not be queued")


def get_email_queue() -> EmailQueue:
    """
    Provide the Celery email queue publisher.

    Returns:
        EmailQueue: Configured component ready for use.
    """
    return EmailQueue()

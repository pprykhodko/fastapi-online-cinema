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
        await self._enqueue(
            "activation",
            email,
            {
                "token": token,
                "expires_at": expires_at.isoformat()
            }
        )

    async def send_activation_complete_email(self, email: str) -> None:
        await self._enqueue("activation_complete", email, {})

    async def send_password_reset_email(
            self,
            email: str,
            token: str,
            expires_at: datetime
    ) -> None:
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
    return EmailQueue()

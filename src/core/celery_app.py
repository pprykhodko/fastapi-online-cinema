from celery import Celery  # type: ignore[import-untyped]

from src.core.config import get_settings


celery_app = Celery(
    "online_cinema",
    broker=get_settings().CELERY_BROKER_URL,
    include=["src.tasks.accounts"],
)
celery_app.conf.update(
    timezone="Europe/Vienna",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    beat_schedule={
        "delete-expired-activation-tokens-hourly": {
            "task": "accounts.delete_expired_activation_tokens",
            "schedule": 3600.0,
        },
    },
)

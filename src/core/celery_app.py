from celery import Celery

from src.core.config import get_settings


celery_app = Celery(
    "online_cinema",
    broker=get_settings().CELERY_BROKER_URL,
    include=["src.tasks.accounts", "src.tasks.emails"]
)
celery_app.conf.update(
    timezone="Europe/Vienna",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    beat_schedule={
        "delete-expired-activation-tokens-hourly": {
            "task": "accounts.delete_expired_activation_tokens",
            "schedule": 3600.0
        }
    }
)

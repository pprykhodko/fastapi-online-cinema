from unittest.mock import AsyncMock

from src.core.celery_app import celery_app
from src.tasks import accounts


def test_cleanup_task_runs_async_function(monkeypatch):
    cleanup = AsyncMock()
    monkeypatch.setattr(accounts, "cleanup_expired_activation_tokens", cleanup)
    accounts.delete_expired_activation_tokens.run()
    cleanup.assert_awaited_once_with()


def test_beat_schedules_registered_task_hourly():
    schedule = celery_app.conf.beat_schedule[
        "delete-expired-activation-tokens-hourly"
    ]
    assert schedule["task"] == accounts.delete_expired_activation_tokens.name
    assert schedule["schedule"] == 3600.0
    assert celery_app.conf.timezone == "Europe/Vienna"
    assert celery_app.conf.enable_utc is True

from pathlib import Path
import runpy
from unittest.mock import MagicMock, Mock

from alembic import context
from alembic.config import Config
import pytest
from sqlalchemy.engine import make_url

from src.core.config import Settings
from src.storages.s3 import S3Storage


@pytest.mark.parametrize("database", ["sqlite", "postgresql"])
def test_alembic_selects_database_without_connecting(monkeypatch, database):
    settings = Settings(
        _env_file=None, DATABASE_TYPE=database,
        POSTGRES_PASSWORD="test%pass@word", POSTGRES_HOST="postgres"
    )
    config = Config()
    config.set_main_option("sqlalchemy.url", "sqlite:///test-only.sqlite3")
    monkeypatch.setattr("src.core.config.get_settings", lambda: settings)
    monkeypatch.setattr(context, "config", config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    configure = Mock()
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", MagicMock())
    monkeypatch.setattr(context, "run_migrations", Mock())
    path = Path(__file__).resolve().parents[2] / "database/alembic/env.py"
    runpy.run_path(str(path))
    url = make_url(configure.call_args.kwargs["url"])
    if database == "sqlite":
        assert url.drivername == "sqlite"
        assert url.database == "test-only.sqlite3"
    else:
        assert url.drivername == "postgresql+psycopg2"
        assert url.password == "test%pass@word"
        assert url.host == "postgres"


def test_signed_urls_use_public_endpoint_not_docker_hostname(monkeypatch):
    client = Mock(spec=["put_object", "generate_presigned_url", "close"])
    factory = Mock(return_value=client)
    monkeypatch.setattr("src.storages.s3.boto3.client", factory)
    storage = S3Storage(Settings(
        _env_file=None, S3_ENDPOINT_URL="http://minio:9000",
        S3_PUBLIC_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="test-access", S3_SECRET_KEY="test-secret"
    ))
    storage.upload_file(b"test", "key", "image/png")
    assert factory.call_args.kwargs["endpoint_url"] == "http://minio:9000/"
    storage.get_file_url("key")
    assert factory.call_args.kwargs["endpoint_url"] == "http://localhost:9000/"

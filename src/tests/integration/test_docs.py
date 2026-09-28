from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.database.models import UserModel
from src.main import app
from src.repositories.accounts import AccountRepository


PATHS = ["/docs", "/redoc", "/openapi.json"]
AUTH = ("user@example.com", "StrongPassword1!")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PATHS)
async def test_docs_require_authentication(login_api, path):
    client, _, _, _ = login_api
    response = await client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")
    assert "paths" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("auth", [
    ("missing@example.com", AUTH[1]), (AUTH[0], "WrongPassword")
])
async def test_docs_reject_invalid_credentials(login_api, path, auth):
    client, _, _, _ = login_api
    response = await client.get(path, auth=auth)
    assert response.status_code == 401
    assert "Basic" in response.headers["www-authenticate"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PATHS)
async def test_active_user_can_access_docs(login_api, path):
    client, _, _, _ = login_api
    response = await client.get(path, auth=("USER@EXAMPLE.COM", AUTH[1]))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert AUTH[1] not in response.text
    if path == "/openapi.json":
        paths = response.json()["paths"]
        assert "/api/v1/accounts/login/" in paths
        assert all(doc_path not in paths for doc_path in PATHS)
        assert response.json()["components"]["securitySchemes"]["HTTPBearer"]
    else:
        assert "text/html" in response.headers["content-type"]
        assert "/openapi.json" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PATHS)
async def test_inactive_user_cannot_access_docs(login_api, path):
    client, sessions, _, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()
    assert (await client.get(path, auth=AUTH)).status_code == 403


@pytest.mark.asyncio
async def test_docs_auth_does_not_grant_api_access(login_api):
    client, _, _, _ = login_api
    assert (await client.get("/docs", auth=AUTH)).status_code == 200
    response = await client.get("/api/v1/cart/", auth=AUTH)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_docs_database_error_is_sanitized(login_api, monkeypatch):
    client, _, _, _ = login_api
    monkeypatch.setattr(
        AccountRepository, "get_user_by_email",
        AsyncMock(side_effect=SQLAlchemyError("private database details"))
    )
    response = await client.get("/docs", auth=AUTH)
    assert response.status_code == 503
    assert "private database details" not in response.text


def test_default_documentation_routes_are_disabled():
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    for path in PATHS:
        assert sum(route.path == path for route in app.routes) == 1
    assert not any(route.path == "/docs/oauth2-redirect" for route in app.routes)

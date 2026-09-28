import re

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_reset_page_is_public_and_does_not_expose_query_values():
    async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/password-reset/?token=do-not-reflect")
        second = await client.get("/password-reset/")

    assert response.status_code == 200
    assert "do-not-reflect" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    nonce = re.search(r'<script nonce="([^"]+)"', response.text).group(1)
    assert f"'nonce-{nonce}'" in response.headers["content-security-policy"]
    assert nonce not in second.text
    assert 'fetch("/api/v1/accounts/password/reset/"' in response.text
    assert 'history.replaceState' in response.text
    assert 'textContent' in response.text


def test_password_api_still_has_three_operations():
    paths = app.openapi()["paths"]
    password_paths = [path for path in paths if "/accounts/password/" in path]
    assert len(password_paths) == 3
    assert "/password-reset/" not in paths

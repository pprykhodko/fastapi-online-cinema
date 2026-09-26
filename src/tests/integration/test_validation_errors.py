import json

import pytest


PREFIX = "/api/v1/accounts"
PASSWORD = "SensitivePassword1!"
TOKEN = "sensitive token with spaces"


@pytest.mark.asyncio
@pytest.mark.parametrize("path,payload", [
    ("register", {"email": "user@example.com", "password": "weak-secret"}),
    ("register", {"password": PASSWORD}),
    ("register", [PASSWORD]),
    ("register", {"email": "invalid", "password": PASSWORD}),
    ("register", {
        "email": "user@example.com", "password": PASSWORD,
        "extra": {"password": PASSWORD, "token": TOKEN}
    }),
    ("login", {"email": "user@example.com", "password": PASSWORD * 5}),
    ("login", {"email": "user@example.com", "password": {"value": PASSWORD}}),
    ("activate", {"token": TOKEN}),
    ("token/refresh", {"refresh_token": TOKEN}),
    ("logout", {"refresh_token": TOKEN}),
    ("password/reset", {"token": TOKEN, "new_password": PASSWORD}),
    ("password/reset", {"token": TOKEN.replace(" ", "-")}),
    ("password/reset", {
        "token": TOKEN.replace(" ", "-"), "new_password": "weak-secret"
    })
])
async def test_validation_response_does_not_echo_credentials(
        login_api, path, payload
):
    client, _, _, _ = login_api
    response = await client.post(f"{PREFIX}/{path}/", json=payload)
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert "weak-secret" not in response.text
    assert TOKEN not in response.text
    assert TOKEN.replace(" ", "-") not in response.text
    for error in response.json()["detail"]:
        assert set(error) == {"type", "loc", "msg"}
        assert error["loc"]
        assert error["msg"]


@pytest.mark.asyncio
async def test_password_change_validation_hides_both_passwords(login_api):
    client, _, manager, user_id = login_api
    response = await client.patch(f"{PREFIX}/password/change/", json={
        "old_password": PASSWORD * 5, "new_password": "weak-secret"
    }, headers={
        "Authorization": f"Bearer {manager.create_access_token(user_id)}"
    })
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert "weak-secret" not in response.text
    assert {tuple(error["loc"]) for error in response.json()["detail"]} == {
        ("body", "old_password"), ("body", "new_password")
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,kwargs", [
    ("GET", "activate", {"params": {"token": TOKEN}}),
    ("POST", "register", {
        "content": '{"password": "SensitivePassword1!",',
        "headers": {"Content-Type": "application/json"}
    })
])
async def test_validation_hides_query_and_malformed_json_input(
        login_api, method, path, kwargs
):
    client, _, _, _ = login_api
    response = await client.request(method, f"{PREFIX}/{path}/", **kwargs)
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert TOKEN not in response.text
    assert all(set(error) == {"type", "loc", "msg"}
               for error in response.json()["detail"])


@pytest.mark.asyncio
async def test_validation_error_keeps_useful_password_message(login_api):
    client, _, _, _ = login_api
    response = await client.post(f"{PREFIX}/register/", json={
        "email": "user@example.com", "password": "lowercaseonly1!"
    })
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "password"]
    assert error["type"] == "value_error"
    assert "uppercase" in error["msg"]
    assert "lowercaseonly1!" not in json.dumps(response.json())


@pytest.mark.asyncio
async def test_http_errors_are_not_changed(login_api):
    client, _, _, _ = login_api
    response = await client.patch(f"{PREFIX}/password/change/", json={
        "old_password": PASSWORD, "new_password": "AnotherPassword2!"
    })
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}
    assert response.headers["www-authenticate"] == "Bearer"

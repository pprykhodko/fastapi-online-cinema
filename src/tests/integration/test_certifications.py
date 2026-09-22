from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError

from src.api.dependencies import get_certification_service
from src.database.models import (
    CertificationModel, MovieModel, UserGroupEnum,
    UserGroupModel, UserModel,
)
from src.main import app
from src.services.certifications import CertificationService


URL = "/api/v1/certifications/"


@pytest_asyncio.fixture
async def certifications_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        group = await db.get(UserGroupModel, user.group_id)
        group.name = UserGroupEnum.MODERATOR
        db.add_all([CertificationModel(id=1, name="PG"),
                    CertificationModel(id=2, name="R")])
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    }
    return client, sessions, user_id, headers


@pytest.mark.asyncio
async def test_certification_crud(certifications_api):
    client, _, _, headers = certifications_api
    listing = await client.get(URL)
    assert listing.status_code == 200
    assert listing.json() == [
        {"id": 1, "name": "PG"},
        {"id": 2, "name": "R"},
    ]
    created = await client.post(
        URL, headers=headers, json={"name": " PG-13 "},
    )
    assert created.status_code == 201
    certification = created.json()
    assert certification["name"] == "PG-13"
    path = f"{URL}{certification['id']}/"
    assert certification in (await client.get(URL)).json()
    updated = await client.patch(path, headers=headers, json={"name": "NC-17"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "NC-17"
    same = await client.patch(path, headers=headers, json={"name": "NC-17"})
    assert same.status_code == 200
    removed = await client.delete(path, headers=headers)
    assert removed.status_code == 204
    assert removed.content == b""
    assert (await client.get(path)).status_code == 405


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", [False, True])
async def test_used_certification_cannot_be_deleted(
    certifications_api, deleted,
):
    client, sessions, _, headers = certifications_api
    async with sessions() as db:
        db.add(MovieModel(
            id=1, name="Movie", year=2020, time=90, imdb=8, votes=100,
            description="Story", price=Decimal("5"),
            certification_id=1, is_deleted=deleted,
        ))
        await db.commit()
    response = await client.delete(URL + "1/", headers=headers)
    assert response.status_code == 409
    async with sessions() as db:
        assert await db.get(CertificationModel, 1) is not None
        assert (await db.get(MovieModel, 1)).certification_id == 1
    renamed = await client.patch(
        URL + "1/", headers=headers, json={"name": "PG-13"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "PG-13"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("role", [None, "USER", "MODERATOR", "ADMIN"])
async def test_write_permissions(certifications_api, method, role):
    client, sessions, user_id, headers = certifications_api
    if role is None:
        headers = {}
    else:
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            group = await db.get(UserGroupModel, user.group_id)
            group.name = UserGroupEnum(role.lower())
            await db.commit()
    path = URL if method == "POST" else URL + "1/"
    response = await client.request(
        method, path, headers=headers,
        **({"json": {"name": "New"}} if method != "DELETE" else {}),
    )
    if role is None:
        assert response.status_code == 401
    elif role == "USER":
        assert response.status_code == 403
    else:
        assert response.status_code == {"POST": 201, "PATCH": 200,
                                        "DELETE": 204}[method]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("body", [
    {}, {"name": ""}, {"name": "   "}, {"name": "x" * 101},
    {"name": None}, {"name": 123}, {"name": "New", "extra": "bad"},
])
async def test_invalid_names(certifications_api, method, body):
    client, _, _, headers = certifications_api
    response = await client.request(
        method, URL if method == "POST" else URL + "1/",
        headers=headers, json=body,
    )
    assert response.status_code == 422
    assert (await client.get(URL)).json()[0]["name"] == "PG"
    assert len((await client.get(URL)).json()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_duplicate_name_rolls_back(certifications_api, method):
    client, _, _, headers = certifications_api
    response = await client.request(
        method, URL if method == "POST" else URL + "2/",
        headers=headers, json={"name": " PG "},
    )
    assert response.status_code == 409
    assert (await client.get(URL)).json()[1]["name"] == "R"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
@pytest.mark.parametrize("certification_id, expected", [
    (999, 404), (0, 422), (-1, 422), (2**31, 422), ("abc", 422),
])
async def test_missing_or_invalid_id(
    certifications_api, method, certification_id, expected,
):
    client, _, _, headers = certifications_api
    response = await client.request(
        method, f"{URL}{certification_id}/", headers=headers,
        **({"json": {"name": "New"}} if method == "PATCH" else {}),
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, failing_method", [
    ("GET", URL, "list_certifications"),
    ("PATCH", URL + "1/", "get_certification"),
    ("POST", URL, "save"), ("DELETE", URL + "1/", "delete"),
])
async def test_database_errors(certifications_api, monkeypatch, method, path,
                               failing_method):
    client, _, _, headers = certifications_api
    repository = AsyncMock()
    getattr(repository, failing_method).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(
        app.dependency_overrides, get_certification_service,
        lambda: CertificationService(repository),
    )
    response = await client.request(
        method, path, headers=headers,
        **({"json": {"name": "New"}} if method in ("POST", "PATCH") else {}),
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_certification_list(certifications_api):
    client, _, _, headers = certifications_api
    for certification_id in (1, 2):
        response = await client.delete(
            f"{URL}{certification_id}/", headers=headers,
        )
        assert response.status_code == 204
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
async def test_inactive_moderator_cannot_write(certifications_api, method):
    client, sessions, user_id, headers = certifications_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()
    response = await client.request(
        method, URL if method == "POST" else URL + "1/", headers=headers,
        **({"json": {"name": "PG-13"}} if method != "DELETE" else {}),
    )
    assert response.status_code == 403
    assert (await client.get(URL)).json()[0]["name"] == "PG"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["G", "PG-13", "NC-17", "12"])
async def test_certification_names_allow_rating_codes(
    certifications_api, name,
):
    client, _, _, headers = certifications_api
    response = await client.post(URL, headers=headers, json={"name": name})
    assert response.status_code == 201
    assert response.json()["name"] == name


def test_certifications_openapi():
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[URL + "{certification_id}/"]) == {"patch", "delete"}
    assert not paths[URL]["get"].get("security")
    assert paths[URL]["post"]["security"]

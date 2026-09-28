from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api.dependencies import get_star_service
from src.database.models import (
    CertificationModel, StarModel, MovieModel, UserGroupEnum,
    UserGroupModel, UserModel
)
from src.database.models.movies import MoviesStarsModel
from src.main import app
from src.services.stars import StarService


URL = "/api/v1/stars/"


@pytest_asyncio.fixture
async def stars_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        group = await db.get(UserGroupModel, user.group_id)
        group.name = UserGroupEnum.MODERATOR
        db.add_all([StarModel(id=1, name="Keanu Reeves"),
                    StarModel(id=2, name="Tom Hanks")])
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}"
    }
    return client, sessions, user_id, headers


@pytest.mark.asyncio
async def test_star_crud(stars_api):
    client, _, _, headers = stars_api
    listing = await client.get(URL)
    assert listing.status_code == 200
    assert listing.json() == [
        {"id": 1, "name": "Keanu Reeves"},
        {"id": 2, "name": "Tom Hanks"}
    ]
    created = await client.post(
        URL, headers=headers, json={"name": " Jean-Claude Van Damme "}
    )
    assert created.status_code == 201
    star = created.json()
    assert star["name"] == "Jean-Claude Van Damme"
    path = f"{URL}{star['id']}/"
    assert (await client.get(path)).json() == star
    updated = await client.patch(path, headers=headers, json={"name": "SF"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "SF"
    same = await client.patch(path, headers=headers, json={"name": "SF"})
    assert same.status_code == 200
    removed = await client.delete(path, headers=headers)
    assert removed.status_code == 204
    assert removed.content == b""
    assert (await client.get(path)).status_code == 404


@pytest.mark.asyncio
async def test_rename_and_delete_preserve_movies(stars_api):
    client, sessions, _, headers = stars_api
    async with sessions() as db:
        star = await db.get(StarModel, 1)
        certification = CertificationModel(name="PG")
        for movie_id, deleted in [(1, False), (2, True)]:
            db.add(MovieModel(
                id=movie_id, name=f"Movie {movie_id}", year=2020, time=90,
                imdb=8, votes=100, description="Story", price=Decimal("5"),
                certification=certification, stars=[star],
                is_deleted=deleted
            ))
        await db.commit()
    response = await client.patch(
        URL + "1/", headers=headers, json={"name": "Renamed"}
    )
    assert response.status_code == 200
    movies = await client.get("/api/v1/movies/", params={"search": "Renamed"})
    assert movies.json()["total"] == 1
    removed = await client.delete(URL + "1/", headers=headers)
    assert removed.status_code == 204
    async with sessions() as db:
        assert len((await db.scalars(select(MovieModel))).all()) == 2
        assert (await db.execute(select(MoviesStarsModel))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("role", [None, "USER", "MODERATOR", "ADMIN"])
async def test_write_permissions(stars_api, method, role):
    client, sessions, user_id, headers = stars_api
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
        **({"json": {"name": "New"}} if method != "DELETE" else {})
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
    {"name": "Actor123"}, {"name": "Актёр"}, {"name": "Actor!"},
    {"name": "Actor?"}, {"name": "—-"}, {"name": "---"},
    {"name": "Lupita Nyong'o"}, {"name": "Penélope Cruz"},
    {"name": "Tom\tHanks"}, {"name": "Tom\nHanks"}
])
async def test_invalid_names(stars_api, method, body):
    client, _, _, headers = stars_api
    response = await client.request(
        method, URL if method == "POST" else URL + "1/",
        headers=headers, json=body
    )
    assert response.status_code == 422
    assert (await client.get(URL + "1/")).json()["name"] == "Keanu Reeves"
    assert len((await client.get(URL)).json()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_duplicate_name_rolls_back(stars_api, method):
    client, _, _, headers = stars_api
    response = await client.request(
        method, URL if method == "POST" else URL + "2/",
        headers=headers, json={"name": " Keanu Reeves "}
    )
    assert response.status_code == 409
    assert (await client.get(URL + "2/")).json()["name"] == "Tom Hanks"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
@pytest.mark.parametrize("star_id, expected", [
    (999, 404), (0, 422), (-1, 422), (2**31, 422), ("abc", 422)
])
async def test_missing_or_invalid_id(stars_api, method, star_id, expected):
    client, _, _, headers = stars_api
    response = await client.request(
        method, f"{URL}{star_id}/", headers=headers,
        **({"json": {"name": "New"}} if method == "PATCH" else {})
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, failing_method", [
    ("GET", URL, "list_stars"), ("GET", URL + "1/", "get_star"),
    ("POST", URL, "save"), ("DELETE", URL + "1/", "delete")
])
async def test_database_errors(stars_api, monkeypatch, method, path,
                               failing_method):
    client, _, _, headers = stars_api
    repository = AsyncMock()
    getattr(repository, failing_method).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(
        app.dependency_overrides, get_star_service,
        lambda: StarService(repository)
    )
    response = await client.request(
        method, path, headers=headers,
        **({"json": {"name": "New"}} if method == "POST" else {})
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_actor_list(stars_api):
    client, _, _, headers = stars_api
    for star_id in (1, 2):
        response = await client.delete(f"{URL}{star_id}/", headers=headers)
        assert response.status_code == 204
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
async def test_inactive_moderator_cannot_write(stars_api, method):
    client, sessions, user_id, headers = stars_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()
    response = await client.request(
        method, URL if method == "POST" else URL + "1/", headers=headers,
        **({"json": {"name": "New Actor"}} if method != "DELETE" else {})
    )
    assert response.status_code == 403
    assert (await client.get(URL + "1/")).json()["name"] == "Keanu Reeves"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("name", ["Jean-Claude Van Damme", "Mary Smith-Jones"])
async def test_actor_names_allow_spaces_and_hyphens(stars_api, method, name):
    client, _, _, headers = stars_api
    response = await client.request(
        method, URL if method == "POST" else URL + "1/",
        headers=headers, json={"name": name}
    )
    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json()["name"] == name


def test_stars_openapi():
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[URL + "{star_id}/"]) == {"get", "patch", "delete"}
    assert not paths[URL]["get"].get("security")
    assert paths[URL]["post"]["security"]

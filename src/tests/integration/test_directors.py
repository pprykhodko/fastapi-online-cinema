from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api.dependencies import get_director_service
from src.database.models import (
    CertificationModel, DirectorModel, MovieModel, UserGroupEnum,
    UserGroupModel, UserModel
)
from src.database.models.movies import MoviesDirectorsModel
from src.main import app
from src.services.directors import DirectorService


URL = "/api/v1/directors/"


@pytest_asyncio.fixture
async def directors_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        group = await db.get(UserGroupModel, user.group_id)
        group.name = UserGroupEnum.MODERATOR
        db.add_all([DirectorModel(id=1, name="Christopher Nolan"),
                    DirectorModel(id=2, name="Steven Spielberg")])
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}"
    }
    return client, sessions, user_id, headers


@pytest.mark.asyncio
async def test_director_crud(directors_api):
    client, _, _, headers = directors_api
    listing = await client.get(URL)
    assert listing.status_code == 200
    assert listing.json() == [
        {"id": 1, "name": "Christopher Nolan"},
        {"id": 2, "name": "Steven Spielberg"}
    ]
    created = await client.post(
        URL, headers=headers, json={"name": " Jean-Luc Godard "}
    )
    assert created.status_code == 201
    director = created.json()
    assert director["name"] == "Jean-Luc Godard"
    path = f"{URL}{director['id']}/"
    assert director in (await client.get(URL)).json()
    updated = await client.patch(path, headers=headers, json={"name": "SF"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "SF"
    same = await client.patch(path, headers=headers, json={"name": "SF"})
    assert same.status_code == 200
    removed = await client.delete(path, headers=headers)
    assert removed.status_code == 204
    assert removed.content == b""
    assert (await client.get(path)).status_code == 405
    remaining = (await client.get(URL)).json()
    assert all(item["id"] != director["id"] for item in remaining)


@pytest.mark.asyncio
async def test_rename_and_delete_preserve_movies(directors_api):
    client, sessions, _, headers = directors_api
    async with sessions() as db:
        director = await db.get(DirectorModel, 1)
        certification = CertificationModel(name="PG")
        for movie_id, deleted in [(1, False), (2, True)]:
            db.add(MovieModel(
                id=movie_id, name=f"Movie {movie_id}", year=2020, time=90,
                imdb=8, votes=100, description="Story", price=Decimal("5"),
                certification=certification, directors=[director],
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
        assert (await db.execute(select(MoviesDirectorsModel))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("role", [None, "USER", "MODERATOR", "ADMIN"])
async def test_write_permissions(directors_api, method, role):
    client, sessions, user_id, headers = directors_api
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
    {"name": "123"}, {"name": "Nolan2"}, {"name": "---"},
    {"name": " - - "}, {"name": "Nolan!"}, {"name": "Penélope Cruz"},
    {"name": "Кристофер"}, {"name": "O'Connor"},
    {"name": "John\tSmith"}, {"name": "John\nSmith"}
])
async def test_invalid_names(directors_api, method, body):
    client, _, _, headers = directors_api
    response = await client.request(
        method, URL if method == "POST" else URL + "1/",
        headers=headers, json=body
    )
    assert response.status_code == 422
    assert (await client.get(URL)).json()[0]["name"] == "Christopher Nolan"
    assert len((await client.get(URL)).json()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_duplicate_name_rolls_back(directors_api, method):
    client, _, _, headers = directors_api
    response = await client.request(
        method, URL if method == "POST" else URL + "2/",
        headers=headers, json={"name": " Christopher Nolan "}
    )
    assert response.status_code == 409
    assert (await client.get(URL)).json()[1]["name"] == "Steven Spielberg"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
@pytest.mark.parametrize("director_id, expected", [
    (999, 404), (0, 422), (-1, 422), (2**31, 422), ("abc", 422)
])
async def test_missing_or_invalid_id(
        directors_api, method, director_id, expected
):
    client, _, _, headers = directors_api
    response = await client.request(
        method, f"{URL}{director_id}/", headers=headers,
        **({"json": {"name": "New"}} if method == "PATCH" else {})
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, failing_method", [
    ("GET", URL, "list_directors"), ("PATCH", URL + "1/", "get_director"),
    ("POST", URL, "save"), ("DELETE", URL + "1/", "delete")
])
async def test_database_errors(directors_api, monkeypatch, method, path,
                               failing_method):
    client, _, _, headers = directors_api
    repository = AsyncMock()
    getattr(repository, failing_method).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(
        app.dependency_overrides, get_director_service,
        lambda: DirectorService(repository)
    )
    response = await client.request(
        method, path, headers=headers,
        **({"json": {"name": "New"}} if method in ("POST", "PATCH") else {})
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_director_list(directors_api):
    client, _, _, headers = directors_api
    for director_id in (1, 2):
        response = await client.delete(f"{URL}{director_id}/", headers=headers)
        assert response.status_code == 204
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
async def test_inactive_moderator_cannot_write(directors_api, method):
    client, sessions, user_id, headers = directors_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        user.is_active = False
        await db.commit()
    response = await client.request(
        method, URL if method == "POST" else URL + "1/", headers=headers,
        **({"json": {"name": "New Director"}} if method != "DELETE" else {})
    )
    assert response.status_code == 403
    assert (await client.get(URL)).json()[0]["name"] == "Christopher Nolan"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Jean-Luc Godard", "Wes Anderson"])
async def test_director_names_allow_spaces_and_hyphens(
        directors_api, name
):
    client, _, _, headers = directors_api
    response = await client.post(URL, headers=headers, json={"name": name})
    assert response.status_code == 201
    assert response.json()["name"] == name


def test_directors_openapi():
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[URL + "{director_id}/"]) == {"patch", "delete"}
    assert not paths[URL]["get"].get("security")
    assert paths[URL]["post"]["security"]

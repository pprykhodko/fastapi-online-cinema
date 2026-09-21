from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api.dependencies import get_genre_service
from src.database.models import (
    CertificationModel, GenreModel, MovieModel, UserGroupEnum,
    UserGroupModel, UserModel,
)
from src.database.models.movies import MoviesGenresModel
from src.main import app
from src.services.genres import GenreService


URL = "/api/v1/genres/"


@pytest_asyncio.fixture
async def genres_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        group = await db.get(UserGroupModel, user.group_id)
        group.name = UserGroupEnum.MODERATOR
        db.add_all([GenreModel(id=1, name="Drama"),
                    GenreModel(id=2, name="Comedy")])
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    }
    return client, sessions, user_id, headers


@pytest.mark.asyncio
async def test_genre_crud(genres_api):
    client, _, _, headers = genres_api
    listing = await client.get(URL)
    assert listing.status_code == 200
    assert listing.json() == [
        {"id": 1, "name": "Drama", "movie_count": 0},
        {"id": 2, "name": "Comedy", "movie_count": 0},
    ]
    created = await client.post(
        URL, headers=headers, json={"name": " Sci-Fi "},
    )
    assert created.status_code == 201
    genre = created.json()
    assert genre["name"] == "Sci-Fi"
    path = f"{URL}{genre['id']}/"
    assert (await client.get(path)).json() == genre
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
async def test_movie_counts_and_delete_preserve_movies(genres_api):
    client, sessions, _, headers = genres_api
    async with sessions() as db:
        genre = await db.get(GenreModel, 1)
        certification = CertificationModel(name="PG")
        for movie_id, deleted in [(1, False), (2, True)]:
            db.add(MovieModel(
                id=movie_id, name=f"Movie {movie_id}", year=2020, time=90,
                imdb=8, votes=100, description="Story", price=Decimal("5"),
                certification=certification, genres=[genre],
                is_deleted=deleted,
            ))
        await db.commit()
    assert (await client.get(URL)).json()[0]["movie_count"] == 1
    response = await client.patch(
        URL + "1/", headers=headers, json={"name": "Renamed"},
    )
    assert response.status_code == 200
    assert (await client.get(URL)).json()[0]["movie_count"] == 1
    movies = await client.get("/api/v1/movies/", params={"genre_id": 1})
    assert movies.json()["total"] == 1
    removed = await client.delete(URL + "1/", headers=headers)
    assert removed.status_code == 204
    async with sessions() as db:
        assert len((await db.scalars(select(MovieModel))).all()) == 2
        assert (await db.execute(select(MoviesGenresModel))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("role", [None, "USER", "MODERATOR", "ADMIN"])
async def test_write_permissions(genres_api, method, role):
    client, sessions, user_id, headers = genres_api
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
async def test_invalid_names(genres_api, method, body):
    client, _, _, headers = genres_api
    response = await client.request(
        method, URL if method == "POST" else URL + "1/",
        headers=headers, json=body,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_duplicate_name_rolls_back(genres_api, method):
    client, _, _, headers = genres_api
    response = await client.request(
        method, URL if method == "POST" else URL + "2/",
        headers=headers, json={"name": " Drama "},
    )
    assert response.status_code == 409
    assert (await client.get(URL + "2/")).json()["name"] == "Comedy"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
@pytest.mark.parametrize("genre_id, expected", [
    (999, 404), (0, 422), (-1, 422), (2**31, 422), ("abc", 422),
])
async def test_missing_or_invalid_id(genres_api, method, genre_id, expected):
    client, _, _, headers = genres_api
    response = await client.request(
        method, f"{URL}{genre_id}/", headers=headers,
        **({"json": {"name": "New"}} if method == "PATCH" else {}),
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path, failing_method", [
    ("GET", URL, "list_genres"), ("GET", URL + "1/", "get_genre"),
    ("POST", URL, "save"), ("DELETE", URL + "1/", "delete"),
])
async def test_database_errors(genres_api, monkeypatch, method, path,
                               failing_method):
    client, _, _, headers = genres_api
    repository = AsyncMock()
    getattr(repository, failing_method).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(
        app.dependency_overrides, get_genre_service,
        lambda: GenreService(repository),
    )
    response = await client.request(
        method, path, headers=headers,
        **({"json": {"name": "New"}} if method == "POST" else {}),
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


def test_genres_openapi():
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[URL + "{genre_id}/"]) == {"get", "patch", "delete"}
    assert not paths[URL]["get"].get("security")
    assert paths[URL]["post"]["security"]

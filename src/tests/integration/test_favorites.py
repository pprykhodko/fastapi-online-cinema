from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api.dependencies import get_favorite_service
from src.database.models import (
    CertificationModel, DirectorModel, GenreModel, MovieFavoriteModel,
    MovieModel, StarModel, UserModel,
)
from src.main import app
from src.repositories.favorites import FavoriteRepository
from src.services.favorites import FavoriteService


URL = "/api/v1/favorites/"


@pytest_asyncio.fixture
async def favorites_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(
            email="other@example.com", group_id=user.group_id,
            _hashed_password="unused", is_active=True,
        )
        db.add(other)
        await db.flush()
        other_id = other.id
        certification = CertificationModel(name="PG")
        genre = GenreModel(id=1, name="Drama")
        stars = [StarModel(name="Alice Actor"), StarModel(name="Alice Star")]
        director = DirectorModel(name="Bob Director")
        for movie_id, name, year, imdb, votes, price in [
            (1, "First", 2020, 8, 100, "10"),
            (2, "Second", 2022, 6, 300, "5"),
            (3, "100%_Movie/", 2022, 10, 200, None),
            (4, "Deleted", 2025, 9, 1000, "1"),
            (5, "Other movie", 2024, 9, 1000, "1"),
        ]:
            db.add(MovieModel(
                id=movie_id, name=name, year=year, time=90, imdb=imdb,
                votes=votes, price=Decimal(price) if price else None,
                description="Space adventure" if movie_id == 1 else "Story",
                certification=certification, is_deleted=movie_id == 4,
                genres=[genre] if movie_id in (1, 2) else [],
                stars=stars if movie_id == 1 else [],
                directors=[director] if movie_id == 2 else [],
            ))
        await db.flush()
        db.add_all([
            MovieFavoriteModel(user_id=user_id, movie_id=movie_id)
            for movie_id in (1, 2, 3, 4)
        ])
        db.add_all([
            MovieFavoriteModel(user_id=other_id, movie_id=movie_id)
            for movie_id in (1, 5)
        ])
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    }
    return client, sessions, user_id, other_id, headers


@pytest.mark.asyncio
@pytest.mark.parametrize("params, expected", [
    ({}, [2, 3, 1]), ({"year": 2020}, [1]), ({"min_imdb": 8}, [3, 1]),
    ({"genre_id": 1}, [2, 1]),
    ({"genre_id": 1, "min_imdb": 8, "year": 2020}, [1]),
    ({"search": " FIRST "}, [1]), ({"search": "space"}, [1]),
    ({"search": "ALICE"}, [1]), ({"search": "bob"}, [2]),
    ({"search": "%"}, [3]), ({"search": "_"}, [3]),
    ({"search": "/"}, [3]), ({"search": "Other movie"}, []),
    ({"search": "Deleted"}, []), ({"genre_id": 999}, []),
    ({"sort_by": "price", "sort_order": "asc"}, [2, 1, 3]),
    ({"sort_by": "price", "sort_order": "desc"}, [1, 2, 3]),
    ({"sort_by": "year", "sort_order": "asc"}, [1, 2, 3]),
    ({"sort_by": "popularity", "sort_order": "asc"}, [1, 3, 2]),
    ({"sort_by": "popularity", "sort_order": "desc"}, [2, 3, 1]),
])
async def test_favorite_queries(favorites_api, params, expected):
    client, _, _, _, headers = favorites_api
    response = await client.get(URL, headers=headers, params=params)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == len(expected)
    assert [item["movie"]["id"] for item in data["items"]] == expected
    for item in data["items"]:
        assert item["added_at"]
        assert item["id"] > 0
        assert "genres" in item["movie"]


@pytest.mark.asyncio
@pytest.mark.parametrize("page, expected", [(1, [2, 3]), (2, [1]), (3, [])])
async def test_favorite_pagination(favorites_api, page, expected):
    client, _, _, _, headers = favorites_api
    response = await client.get(
        URL, headers=headers, params={"page": page, "per_page": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert (data["total"], data["page"], data["per_page"]) == (3, page, 2)
    assert [item["movie"]["id"] for item in data["items"]] == expected


@pytest.mark.asyncio
async def test_add_remove_and_isolation(favorites_api):
    client, sessions, user_id, other_id, headers = favorites_api
    # It belongs to another user's favorites, but not ours.
    missing = await client.delete(URL + "5/", headers=headers)
    assert missing.status_code == 404
    response = await client.post(URL, headers=headers, json={"movie_id": 5})
    assert response.status_code == 201, response.text
    assert response.json()["movie"]["id"] == 5
    duplicate = await client.post(URL, headers=headers, json={"movie_id": 5})
    assert duplicate.status_code == 409
    removed = await client.delete(URL + "5/", headers=headers)
    assert removed.status_code == 204
    assert removed.content == b""
    missing = await client.delete(URL + "5/", headers=headers)
    assert missing.status_code == 404
    async with sessions() as db:
        assert await db.get(MovieModel, 5) is not None
        assert await db.scalar(select(MovieFavoriteModel.id).where(
            MovieFavoriteModel.user_id == other_id,
            MovieFavoriteModel.movie_id == 5,
        )) is not None
        assert await db.scalar(select(MovieFavoriteModel.id).where(
            MovieFavoriteModel.user_id == user_id,
            MovieFavoriteModel.movie_id == 5,
        )) is None


@pytest.mark.asyncio
async def test_remove_deleted_movie_and_empty_list(favorites_api):
    client, _, _, _, headers = favorites_api
    for movie_id in (1, 2, 3, 4):
        response = await client.delete(f"{URL}{movie_id}/", headers=headers)
        assert response.status_code == 204
    empty = await client.get(URL, headers=headers)
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []
    # Movies without a price can still be favorites.
    added = await client.post(URL, headers=headers, json={"movie_id": 3})
    assert added.status_code == 201
    assert added.json()["movie"]["is_available_for_purchase"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("movie_id", [4, 999])
async def test_missing_or_deleted_movie(favorites_api, movie_id):
    client, _, _, _, headers = favorites_api
    response = await client.post(
        URL, headers=headers, json={"movie_id": movie_id},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {}, {"movie_id": 0}, {"movie_id": -1}, {"movie_id": True},
    {"movie_id": "1"}, {"movie_id": 2**63}, {"movie_id": 5, "user_id": 2},
])
async def test_invalid_favorite_body(favorites_api, body):
    client, _, _, _, headers = favorites_api
    response = await client.post(URL, headers=headers, json=body)
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [
    {"page": 0}, {"per_page": 101}, {"min_imdb": 11}, {"search": "   "},
    {"genre_id": 0}, {"sort_by": "invalid"}, {"user_id": 2},
])
async def test_invalid_favorite_query(favorites_api, params):
    client, _, _, _, headers = favorites_api
    response = await client.get(URL, headers=headers, params=params)
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
@pytest.mark.parametrize("auth", ["missing", "invalid", "inactive"])
async def test_favorites_require_active_account(favorites_api, method, auth):
    client, sessions, user_id, _, headers = favorites_api
    if auth == "inactive":
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            user.is_active = False
            await db.commit()
    else:
        headers = {} if auth == "missing" else {"Authorization": "Bearer bad"}
    response = await client.request(
        method, URL + "1/" if method == "DELETE" else URL, headers=headers,
        **({"json": {"movie_id": 5}} if method == "POST" else {}),
    )
    assert response.status_code == (403 if auth == "inactive" else 401)


@pytest.mark.asyncio
@pytest.mark.parametrize("method, failure", [
    ("GET", "list_movies"), ("POST", "get_movie"), ("DELETE", "delete"),
])
async def test_favorite_database_failure(favorites_api, monkeypatch,
                                         method, failure):
    client, _, _, _, headers = favorites_api
    repository = AsyncMock()
    movie_repository = AsyncMock()
    failed_repo = repository if failure == "delete" else movie_repository
    getattr(failed_repo, failure).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(app.dependency_overrides, get_favorite_service,
                        lambda: FavoriteService(repository, movie_repository))
    response = await client.request(
        method, URL + "1/" if method == "DELETE" else URL, headers=headers,
        **({"json": {"movie_id": 5}} if method == "POST" else {}),
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_favorite_commit_failure_rolls_back(favorites_api, monkeypatch):
    client, sessions, user_id, _, headers = favorites_api

    async def fail_commit(self):
        raise SQLAlchemyError("private")

    monkeypatch.setattr(FavoriteRepository, "commit", fail_commit)
    response = await client.post(URL, headers=headers, json={"movie_id": 5})
    assert response.status_code == 503
    async with sessions() as db:
        assert await db.scalar(select(MovieFavoriteModel.id).where(
            MovieFavoriteModel.user_id == user_id,
            MovieFavoriteModel.movie_id == 5,
        )) is None


def test_favorites_openapi():
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[URL + "{movie_id}/"]) == {"delete"}
    for path in (URL, URL + "{movie_id}/"):
        for operation in paths[path].values():
            assert operation["security"]
    assert {p["name"] for p in paths[URL]["get"]["parameters"]} == {
        "page", "per_page", "year", "min_imdb", "genre_id", "search",
        "sort_by", "sort_order",
    }

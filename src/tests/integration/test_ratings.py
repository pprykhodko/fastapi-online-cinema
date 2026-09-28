from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.api.dependencies import get_rating_service
from src.database.models import (
    CertificationModel, MovieModel, MovieRatingModel, UserModel
)
from src.main import app
from src.repositories.ratings import RatingRepository
from src.services.ratings import RatingService


PATH = "/api/v1/movies/1/rating/"


@pytest_asyncio.fixture
async def ratings_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(
            email="other@example.com", group_id=user.group_id,
            _hashed_password="unused", is_active=True
        )
        movie = MovieModel(
            id=1, name="Movie", year=2020, time=90, imdb=8, votes=5,
            description="Story", price=Decimal("5"),
            certification=CertificationModel(name="PG")
        )
        db.add_all([other, movie])
        await db.flush()
        other_id = other.id
        db.add(MovieRatingModel(
            user_id=other_id, movie_id=1, score=3
        ))
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}"
    }
    return client, sessions, user_id, other_id, headers


@pytest.mark.asyncio
async def test_rating_lifecycle_and_user_isolation(ratings_api):
    client, sessions, user_id, other_id, headers = ratings_api
    assert (await client.get(PATH, headers=headers)).status_code == 404
    assert (await client.delete(PATH, headers=headers)).status_code == 404
    created = await client.put(
        PATH, headers=headers, json={"score": 8}
    )
    assert created.status_code == 201
    first = created.json()
    assert first["user_id"] == user_id
    assert first["movie_id"] == 1
    assert first["score"] == 8
    assert first["created_at"] and first["updated_at"]
    repeated = await client.put(
        PATH, headers=headers, json={"score": 8}
    )
    assert repeated.status_code == 200
    assert repeated.json() == first
    async with sessions() as db:
        rating = await db.get(MovieRatingModel, first["id"])
        rating.updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        await db.commit()
    changed = await client.put(
        PATH, headers=headers, json={"score": 3}
    )
    assert changed.status_code == 200
    assert changed.json()["id"] == first["id"]
    assert changed.json()["created_at"] == first["created_at"]
    assert not changed.json()["updated_at"].startswith("2000")
    assert changed.json()["score"] == 3
    assert (await client.get(PATH, headers=headers)).json() == changed.json()
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(
            MovieRatingModel
        )) == 2
    removed = await client.delete(PATH, headers=headers)
    assert removed.status_code == 204
    assert removed.content == b""
    assert (await client.delete(PATH, headers=headers)).status_code == 404
    async with sessions() as db:
        other = await db.scalar(select(MovieRatingModel).where(
            MovieRatingModel.user_id == other_id
        ))
        assert other.score == 3
        assert await db.get(MovieModel, 1) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("auth", ["missing", "invalid", "inactive"])
async def test_authentication(ratings_api, method, auth):
    client, sessions, user_id, _, headers = ratings_api
    if auth == "inactive":
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            user.is_active = False
            await db.commit()
    else:
        headers = {} if auth == "missing" else {"Authorization": "Bearer bad"}
    response = await client.request(
        method, PATH, headers=headers,
        **({"json": {"score": 8}} if method == "PUT" else {})
    )
    assert response.status_code == (403 if auth == "inactive" else 401)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {}, {"score": 0}, {"score": 11}, {"score": -1}, {"score": 5.5},
    {"score": "8"}, {"score": None}, {"score": True}, {"score": 8.0},
    {"score": 8, "user_id": 2}, {"score": 8, "movie_id": 2}

])
async def test_invalid_rating_body(ratings_api, body):
    client, _, _, _, headers = ratings_api
    response = await client.put(PATH, headers=headers, json=body)
    assert response.status_code == 422
    assert (await client.get(PATH, headers=headers)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("movie_id, expected", [
    (999, 404), (0, 422), (-1, 422), (2**31, 422), ("abc", 422)
])
async def test_missing_or_invalid_movie(
        ratings_api, method, movie_id, expected
):
    client, _, _, _, headers = ratings_api
    response = await client.request(
        method, f"/api/v1/movies/{movie_id}/rating/", headers=headers,
        **({"json": {"score": 8}} if method == "PUT" else {})
    )
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_deleted_movie_rating_can_only_be_removed(ratings_api):
    client, sessions, _, _, headers = ratings_api
    response = await client.put(
        PATH, headers=headers, json={"score": 8}
    )
    assert response.status_code == 201
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.is_deleted = True
        await db.commit()
    assert (await client.get(PATH, headers=headers)).status_code == 404
    response = await client.put(
        PATH, headers=headers, json={"score": 3}
    )
    assert response.status_code == 404
    assert (await client.delete(PATH, headers=headers)).status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize("method, failure", [
    ("GET", "get_movie"), ("GET", "get_rating"),
    ("PUT", "get_movie"), ("DELETE", "delete")
])
async def test_database_failure(ratings_api, monkeypatch, method, failure):
    client, _, _, _, headers = ratings_api
    repository = AsyncMock()
    movie_repository = AsyncMock()
    failed_repo = movie_repository if failure == "get_movie" else repository
    getattr(failed_repo, failure).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(app.dependency_overrides, get_rating_service,
                        lambda: RatingService(repository, movie_repository))
    response = await client.request(
        method, PATH, headers=headers,
        **({"json": {"score": 8}} if method == "PUT" else {})
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_failed_commit_rolls_back(ratings_api, monkeypatch, operation):
    client, sessions, user_id, _, headers = ratings_api
    if operation != "create":
        await client.put(PATH, headers=headers, json={"score": 8})

    async def fail_commit(self):
        raise SQLAlchemyError("private")

    monkeypatch.setattr(RatingRepository, "commit", fail_commit)
    response = await client.request(
        "DELETE" if operation == "delete" else "PUT", PATH, headers=headers,
        **({"json": {"score": 3}} if operation != "delete" else {})
    )
    assert response.status_code == 503
    async with sessions() as db:
        rating = await db.scalar(select(MovieRatingModel).where(
            MovieRatingModel.user_id == user_id
        ))
        if operation == "create":
            assert rating is None
        else:
            assert rating.score == 8


@pytest.mark.asyncio
async def test_integrity_conflict_returns_409(ratings_api, monkeypatch):
    client, _, _, _, headers = ratings_api

    async def fail_save(self, rating):
        raise IntegrityError("private", {}, Exception())

    monkeypatch.setattr(RatingRepository, "save", fail_save)
    response = await client.put(
        PATH, headers=headers, json={"score": 8}
    )
    assert response.status_code == 409
    assert "private" not in response.text


def test_rating_openapi():
    operations = app.openapi()["paths"]["/api/v1/movies/{movie_id}/rating/"]
    assert set(operations) == {"get", "put", "delete"}
    for operation in operations.values():
        assert operation["security"]
        assert {"401", "403", "404", "503"} <= operation["responses"].keys()
    assert {"200", "201", "409"} <= operations["put"]["responses"].keys()


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [1, 10])
async def test_rating_boundaries(ratings_api, score):
    client, _, _, _, headers = ratings_api
    response = await client.put(PATH, headers=headers, json={"score": score})
    assert response.status_code == 201
    assert response.json()["score"] == score


@pytest.mark.asyncio
async def test_average_rating_in_catalog(ratings_api):
    client, sessions, _, other_id, headers = ratings_api
    async with sessions() as db:
        first = await db.get(MovieModel, 1)
        for movie_id in (2, 3):
            db.add(MovieModel(
                id=movie_id, name=f"Movie {movie_id}", year=2010, time=90,
                imdb=9, votes=10, description="Story", price=None,
                certification_id=first.certification_id
            ))
        await db.flush()
        db.add(MovieRatingModel(user_id=other_id, movie_id=2, score=10))
        await db.commit()
    catalog = (await client.get("/api/v1/movies/")).json()
    assert catalog["total"] == 3
    averages = {
        item["id"]: item["average_rating"] for item in catalog["items"]
    }
    assert averages == {1: 3.0, 2: 10.0, 3: None}

    response = await client.put(PATH, headers=headers, json={"score": 8})
    assert response.status_code == 201
    # A repeat PUT must not add another vote to the average.
    response = await client.put(PATH, headers=headers, json={"score": 8})
    assert response.status_code == 200
    for params in ({}, {"search": "Movie", "per_page": 1}, {"year": 2020}):
        catalog = (await client.get("/api/v1/movies/", params=params)).json()
        first = catalog["items"][0]
        assert first["id"] == 1
        assert first["average_rating"] == 5.5
        assert first["imdb"] == 8
        assert first["likes_count"] == first["dislikes_count"] == 0
    own = (await client.get(PATH, headers=headers)).json()
    assert own["score"] == 8
    assert "average_rating" not in own
    detail = (await client.get("/api/v1/movies/1/")).json()
    assert "average_rating" not in detail

    await client.put(PATH, headers=headers, json={"score": 10})
    catalog = (await client.get("/api/v1/movies/")).json()
    assert catalog["items"][0]["average_rating"] == 6.5
    await client.delete(PATH, headers=headers)
    catalog = (await client.get("/api/v1/movies/")).json()
    assert catalog["items"][0]["average_rating"] == 3
    async with sessions() as db:
        await db.execute(delete(MovieRatingModel).where(
            MovieRatingModel.movie_id == 1
        ))
        await db.commit()
    catalog = (await client.get("/api/v1/movies/")).json()
    assert catalog["items"][0]["average_rating"] is None
    assert catalog["items"][1]["average_rating"] == 10

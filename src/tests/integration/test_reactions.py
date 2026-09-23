from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.api.dependencies import get_reaction_service
from src.database.models import (
    CertificationModel, MovieModel, MovieReactionModel, UserModel,
)
from src.main import app
from src.repositories.reactions import ReactionRepository
from src.services.reactions import ReactionService


PATH = "/api/v1/movies/1/reaction/"


@pytest_asyncio.fixture
async def reactions_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(
            email="other@example.com", group_id=user.group_id,
            _hashed_password="unused", is_active=True,
        )
        movie = MovieModel(
            id=1, name="Movie", year=2020, time=90, imdb=8, votes=5,
            description="Story", price=Decimal("5"),
            certification=CertificationModel(name="PG"),
        )
        db.add_all([other, movie])
        await db.flush()
        other_id = other.id
        db.add(MovieReactionModel(
            user_id=other_id, movie_id=1, reaction="dislike",
        ))
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}",
    }
    return client, sessions, user_id, other_id, headers


@pytest.mark.asyncio
async def test_reaction_lifecycle_and_user_isolation(reactions_api):
    client, sessions, user_id, other_id, headers = reactions_api
    assert (await client.get(PATH, headers=headers)).status_code == 404
    assert (await client.delete(PATH, headers=headers)).status_code == 404
    created = await client.put(
        PATH, headers=headers, json={"reaction": "like"},
    )
    assert created.status_code == 201
    first = created.json()
    assert first["user_id"] == user_id
    assert first["movie_id"] == 1
    assert first["reaction"] == "like"
    assert first["created_at"] and first["updated_at"]
    repeated = await client.put(
        PATH, headers=headers, json={"reaction": "like"},
    )
    assert repeated.status_code == 200
    assert repeated.json() == first
    async with sessions() as db:
        reaction = await db.get(MovieReactionModel, first["id"])
        reaction.updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        await db.commit()
    changed = await client.put(
        PATH, headers=headers, json={"reaction": "dislike"},
    )
    assert changed.status_code == 200
    assert changed.json()["id"] == first["id"]
    assert changed.json()["created_at"] == first["created_at"]
    assert not changed.json()["updated_at"].startswith("2000")
    assert changed.json()["reaction"] == "dislike"
    assert (await client.get(PATH, headers=headers)).json() == changed.json()
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(
            MovieReactionModel,
        )) == 2
    removed = await client.delete(PATH, headers=headers)
    assert removed.status_code == 204
    assert removed.content == b""
    assert (await client.delete(PATH, headers=headers)).status_code == 404
    async with sessions() as db:
        other = await db.scalar(select(MovieReactionModel).where(
            MovieReactionModel.user_id == other_id,
        ))
        assert other.reaction == "dislike"
        assert await db.get(MovieModel, 1) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("auth", ["missing", "invalid", "inactive"])
async def test_authentication(reactions_api, method, auth):
    client, sessions, user_id, _, headers = reactions_api
    if auth == "inactive":
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            user.is_active = False
            await db.commit()
    else:
        headers = {} if auth == "missing" else {"Authorization": "Bearer bad"}
    response = await client.request(
        method, PATH, headers=headers,
        **({"json": {"reaction": "like"}} if method == "PUT" else {}),
    )
    assert response.status_code == (403 if auth == "inactive" else 401)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {}, {"reaction": "love"}, {"reaction": "LIKE"}, {"reaction": ""},
    {"reaction": None}, {"reaction": 1}, {"reaction": True},
    {"reaction": "like", "user_id": 2}, {"reaction": "like", "movie_id": 2},
])
async def test_invalid_reaction_body(reactions_api, body):
    client, _, _, _, headers = reactions_api
    response = await client.put(PATH, headers=headers, json=body)
    assert response.status_code == 422
    assert (await client.get(PATH, headers=headers)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("movie_id, expected", [
    (999, 404), (0, 422), (-1, 422), (2**31, 422), ("abc", 422),
])
async def test_missing_or_invalid_movie(
    reactions_api, method, movie_id, expected,
):
    client, _, _, _, headers = reactions_api
    response = await client.request(
        method, f"/api/v1/movies/{movie_id}/reaction/", headers=headers,
        **({"json": {"reaction": "like"}} if method == "PUT" else {}),
    )
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_deleted_movie_reaction_can_only_be_removed(reactions_api):
    client, sessions, _, _, headers = reactions_api
    response = await client.put(
        PATH, headers=headers, json={"reaction": "like"},
    )
    assert response.status_code == 201
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.is_deleted = True
        await db.commit()
    assert (await client.get(PATH, headers=headers)).status_code == 404
    response = await client.put(
        PATH, headers=headers, json={"reaction": "dislike"},
    )
    assert response.status_code == 404
    assert (await client.delete(PATH, headers=headers)).status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize("method, failure", [
    ("GET", "movie_exists"), ("GET", "get_reaction"),
    ("PUT", "movie_exists"), ("DELETE", "delete"),
])
async def test_database_failure(reactions_api, monkeypatch, method, failure):
    client, _, _, _, headers = reactions_api
    repository = AsyncMock()
    repository.movie_exists.return_value = True
    getattr(repository, failure).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(app.dependency_overrides, get_reaction_service,
                        lambda: ReactionService(repository))
    response = await client.request(
        method, PATH, headers=headers,
        **({"json": {"reaction": "like"}} if method == "PUT" else {}),
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_failed_commit_rolls_back(reactions_api, monkeypatch, operation):
    client, sessions, user_id, _, headers = reactions_api
    if operation != "create":
        await client.put(PATH, headers=headers, json={"reaction": "like"})

    async def fail_commit(self):
        raise SQLAlchemyError("private")

    monkeypatch.setattr(ReactionRepository, "commit", fail_commit)
    response = await client.request(
        "DELETE" if operation == "delete" else "PUT", PATH, headers=headers,
        **({"json": {"reaction": "dislike"}} if operation != "delete" else {}),
    )
    assert response.status_code == 503
    async with sessions() as db:
        reaction = await db.scalar(select(MovieReactionModel).where(
            MovieReactionModel.user_id == user_id,
        ))
        if operation == "create":
            assert reaction is None
        else:
            assert reaction.reaction == "like"


@pytest.mark.asyncio
async def test_integrity_conflict_returns_409(reactions_api, monkeypatch):
    client, _, _, _, headers = reactions_api

    async def fail_save(self, reaction):
        raise IntegrityError("private", {}, Exception())

    monkeypatch.setattr(ReactionRepository, "save", fail_save)
    response = await client.put(
        PATH, headers=headers, json={"reaction": "like"},
    )
    assert response.status_code == 409
    assert "private" not in response.text


def test_reaction_openapi():
    operations = app.openapi()["paths"]["/api/v1/movies/{movie_id}/reaction/"]
    assert set(operations) == {"get", "put", "delete"}
    for operation in operations.values():
        assert operation["security"]
        assert {"401", "403", "404", "503"} <= operation["responses"].keys()
    assert {"200", "201", "409"} <= operations["put"]["responses"].keys()

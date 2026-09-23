from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.api.dependencies import get_movie_service
from src.database import get_db
from src.database.models import (
    Base, CertificationModel, DirectorModel, GenreModel, MovieModel, StarModel,
    MovieReactionModel, UserGroupModel, UserGroupEnum, UserModel,
)
from src.database.session_sqlite import create_sqlite_engine
from src.main import app
from src.repositories.movies import MovieRepository
from src.services.movies import MovieService


URL_PATH = "/api/v1/movies/"


@pytest_asyncio.fixture
async def catalog_api(monkeypatch):
    engine = create_sqlite_engine(
        URL.create("sqlite+aiosqlite", database=":memory:")
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        certification = CertificationModel(name="PG")
        drama = GenreModel(id=1, name="Drama")
        comedy = GenreModel(id=2, name="Comedy")
        stars = [StarModel(name="Alice Actor"), StarModel(name="Alice Star")]
        director = DirectorModel(name="Bob Director")
        for movie_id, name, year, imdb, votes, price, genres in [
            (1, "First", 2020, 8.0, 100, "10.00", [drama]),
            (2, "Second", 2022, 6.0, 300, "5.00", [drama, comedy]),
            (3, "100%_Movie/", 2022, 10.0, 200, None, [comedy]),
            (4, "Fourth", 2019, 0.0, 100, "10.00", []),
            (5, "Deleted", 2025, 9.0, 999, "1.00", [drama]),
        ]:
            db.add(MovieModel(
                id=movie_id, name=name, year=year, time=90, imdb=imdb,
                votes=votes, price=Decimal(price) if price else None,
                genres=genres,
                description="Space adventure" if movie_id == 1 else "Story",
                certification=certification, is_deleted=movie_id == 5,
                stars=stars if movie_id == 1 else [],
                directors=[director] if movie_id == 2 else [],
            ))
        await db.commit()

    async def override_db():
        async with sessions() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, sessions
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_is_public_and_excludes_deleted(catalog_api):
    client, _ = catalog_api
    response = await client.get(URL_PATH)
    assert response.status_code == 200
    data = response.json()
    assert (data["total"], data["page"], data["per_page"]) == (4, 1, 10)
    assert [item["id"] for item in data["items"]] == [2, 3, 1, 4]
    assert data["items"][0]["is_available_for_purchase"] is True
    assert {g["name"] for g in data["items"][0]["genres"]} == {
        "Drama", "Comedy",
    }
    assert data["items"][1]["price"] is None
    assert data["items"][1]["is_available_for_purchase"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("params, expected", [
    ({"year": 2022}, [2, 3]),
    ({"min_imdb": 8}, [3, 1]),
    ({"min_imdb": 10}, [3]),
    ({"min_imdb": 0}, [2, 3, 1, 4]),
    ({"genre_id": 1}, [2, 1]),
    ({"year": 2022, "genre_id": 1, "min_imdb": 6}, [2]),
    ({"year": 2022, "genre_id": 1, "min_imdb": 7}, []),
    ({"genre_id": 999}, []),
    ({"search": " FIRST "}, [1]),
    ({"search": "space"}, [1]),
    ({"search": "ALICE"}, [1]),
    ({"search": "bob"}, [2]),
    ({"search": "%"}, [3]),
    ({"search": "_"}, [3]),
    ({"search": "/"}, [3]),
    ({"search": "deleted"}, []),
    ({"search": "' OR 1=1 --"}, []),
])
async def test_catalog_filters_and_search(catalog_api, params, expected):
    client, _ = catalog_api
    response = await client.get(URL_PATH, params=params)
    assert response.status_code == 200
    assert response.json()["total"] == len(expected)
    assert [item["id"] for item in response.json()["items"]] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("sort_by, sort_order, expected", [
    ("year", "asc", [4, 1, 2, 3]),
    ("year", "desc", [2, 3, 1, 4]),
    ("price", "asc", [2, 1, 4, 3]),
    ("price", "desc", [1, 4, 2, 3]),
    ("popularity", "asc", [1, 4, 3, 2]),
    ("popularity", "desc", [2, 3, 1, 4]),
])
async def test_catalog_sorting(catalog_api, sort_by, sort_order, expected):
    client, _ = catalog_api
    response = await client.get(URL_PATH, params={
        "sort_by": sort_by, "sort_order": sort_order,
    })
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("page, expected", [(1, [2, 3]), (2, [1, 4]), (3, [])])
async def test_catalog_pagination(catalog_api, page, expected):
    client, _ = catalog_api
    response = await client.get(URL_PATH, params={"page": page, "per_page": 2})
    assert response.status_code == 200
    assert response.json()["total"] == 4
    assert response.json()["page"] == page
    assert response.json()["per_page"] == 2
    assert [item["id"] for item in response.json()["items"]] == expected


@pytest.mark.asyncio
async def test_empty_catalog(catalog_api):
    client, sessions = catalog_api
    async with sessions() as db:
        await db.execute(delete(MovieModel))
        await db.commit()
    response = await client.get(URL_PATH)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": "abc"}, {"page": 2**63},
    {"per_page": 0}, {"per_page": 101},
    {"year": "abc"}, {"year": 2**63},
    {"genre_id": 0}, {"genre_id": 2**64},
    {"min_imdb": -1}, {"min_imdb": 11}, {"min_imdb": "nan"},
    {"min_imdb": "inf"}, {"search": ""}, {"search": "   "},
    {"search": "a" * 251}, {"sort_by": "invalid"},
    {"sort_order": "invalid"}, {"unknown": "field"},
])
async def test_invalid_catalog_parameters(catalog_api, params):
    client, _ = catalog_api
    response = await client.get(URL_PATH, params=params)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_catalog_database_failure(catalog_api, monkeypatch):
    client, _ = catalog_api
    db = AsyncMock()
    db.scalar.side_effect = SQLAlchemyError("private DB details")
    monkeypatch.setitem(
        app.dependency_overrides, get_movie_service,
        lambda: MovieService(MovieRepository(db)),
    )
    response = await client.get(URL_PATH)
    assert response.status_code == 503
    assert response.json() == {
        "detail": "The movie catalog is temporarily unavailable.",
    }
    db.rollback.assert_awaited_once()


def test_catalog_openapi():
    operation = app.openapi()["paths"][URL_PATH]["get"]
    assert "requestBody" not in operation
    assert not operation.get("security")
    assert {p["name"] for p in operation["parameters"]} == {
        "page", "per_page", "year", "min_imdb", "genre_id", "search",
        "sort_by", "sort_order",
    }
    assert {"200", "422", "503"} <= operation["responses"].keys()


@pytest.mark.asyncio
async def test_catalog_reaction_counts(catalog_api):
    client, sessions = catalog_api
    async with sessions() as db:
        group = UserGroupModel(name=UserGroupEnum.USER)
        users = [UserModel(
            email=f"user{i}@example.com", group=group,
            _hashed_password="unused", is_active=True,
        ) for i in range(3)]
        db.add_all(users)
        await db.flush()
        reactions = [MovieReactionModel(
            user_id=user.id, movie_id=2,
            reaction="dislike" if index == 2 else "like",
        ) for index, user in enumerate(users)]
        db.add_all(reactions)
        db.add(MovieReactionModel(
            user_id=users[0].id, movie_id=1, reaction="dislike",
        ))
        await db.commit()
        reaction_id = reactions[0].id

    response = await client.get(URL_PATH)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    counts = {item["id"]: (item["likes_count"], item["dislikes_count"])
              for item in data["items"]}
    assert counts == {1: (0, 1), 2: (2, 1), 3: (0, 0), 4: (0, 0)}
    for params in (
        {"page": 1, "per_page": 1}, {"search": "Second"},
        {"genre_id": 1, "year": 2022},
    ):
        page = (await client.get(URL_PATH, params=params)).json()
        assert len(page["items"]) == 1
        assert page["items"][0]["likes_count"] == 2
        assert page["items"][0]["dislikes_count"] == 1

    detail = (await client.get(URL_PATH + "2/")).json()
    assert "likes_count" not in detail
    assert "dislikes_count" not in detail
    async with sessions() as db:
        reaction = await db.get(MovieReactionModel, reaction_id)
        reaction.reaction = "dislike"
        await db.commit()
    changed = (await client.get(URL_PATH)).json()["items"][0]
    assert (changed["likes_count"], changed["dislikes_count"]) == (1, 2)
    async with sessions() as db:
        await db.execute(delete(MovieReactionModel).where(
            MovieReactionModel.id == reaction_id,
        ))
        await db.commit()
    changed = (await client.get(URL_PATH)).json()["items"][0]
    assert (changed["likes_count"], changed["dislikes_count"]) == (1, 1)

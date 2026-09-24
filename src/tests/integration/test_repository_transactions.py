from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import (
    CertificationModel, DirectorModel, GenreModel, MovieFavoriteModel,
    MovieModel, StarModel,
)
from src.repositories.certifications import CertificationRepository
from src.repositories.directors import DirectorRepository
from src.repositories.favorites import FavoriteRepository
from src.repositories.genres import GenreRepository
from src.repositories.movies import MovieRepository
from src.repositories.stars import StarRepository
from src.services.certifications import CertificationService
from src.services.directors import DirectorService
from src.services.favorites import FavoriteService
from src.services.genres import GenreService
from src.services.stars import StarService


REFERENCE_CASES = [
    (GenreModel, GenreRepository, GenreService, "delete_genre"),
    (StarModel, StarRepository, StarService, "delete_star"),
    (DirectorModel, DirectorRepository, DirectorService, "delete_director"),
    (CertificationModel, CertificationRepository, CertificationService,
     "delete_certification"),
]


@pytest.mark.asyncio
async def test_multiple_repositories_share_one_transaction(login_api):
    _, sessions, _, _ = login_api
    async with sessions() as db:
        genre_repo = GenreRepository(db)
        star_repo = StarRepository(db)
        db.add(StarModel(name="Existing"))
        await db.commit()

        await genre_repo.save(GenreModel(name="Drama"))
        with pytest.raises(IntegrityError):
            await star_repo.save(StarModel(name="Existing"))
        await genre_repo.rollback()

    async with sessions() as db:
        assert await db.scalar(select(GenreModel)) is None
        assert (await db.scalar(select(StarModel))).name == "Existing"


@pytest.mark.asyncio
@pytest.mark.parametrize("model,repo_class,service_class,delete_method",
                         REFERENCE_CASES)
async def test_repository_writes_can_be_rolled_back(
    login_api, model, repo_class, service_class, delete_method,
):
    _, sessions, _, _ = login_api
    async with sessions() as db:
        repo = repo_class(db)
        item = model(name="Original")
        await repo.save(item)
        item_id = item.id
        assert item_id is not None
        await repo.rollback()
        assert await db.get(model, item_id) is None

        item = model(name="Original")
        await repo.save(item)
        item_id = item.id
        await repo.commit()
        item.name = "Changed"
        await repo.save(item)
        await repo.rollback()
        assert (await db.get(model, item_id)).name == "Original"

        assert await repo.delete(item_id)
        await repo.rollback()
        assert (await db.get(model, item_id)).name == "Original"


@pytest.mark.asyncio
@pytest.mark.parametrize("model,repo_class,service_class,delete_method",
                         REFERENCE_CASES)
@pytest.mark.parametrize("operation", ["create", "update", "delete"])
@pytest.mark.parametrize("conflict", [False, True])
async def test_service_commit_failure_rolls_back(
    login_api, monkeypatch, model, repo_class, service_class,
    delete_method, operation, conflict,
):
    _, sessions, _, _ = login_api
    async with sessions() as db:
        item = model(name="Original")
        db.add(item)
        await db.commit()
        item_id = item.id
        repo = repo_class(db)
        service = service_class(repo)
        error = (IntegrityError("private", {}, Exception()) if conflict
                 else SQLAlchemyError("private"))
        commit = AsyncMock(side_effect=error)
        monkeypatch.setattr(repo, "commit", commit)
        with pytest.raises(HTTPException) as caught:
            if operation == "delete":
                await getattr(service, delete_method)(item_id)
            elif operation == "update":
                item.name = "Changed"
                await service.save(item)
            else:
                await service.save(model(name="New"))
        expected = 409 if conflict and (
            operation != "delete" or model is CertificationModel
        ) else 503
        assert caught.value.status_code == expected
        commit.assert_awaited_once()
        assert "private" not in caught.value.detail
        assert not db.in_transaction()
    async with sessions() as db:
        items = list(await db.scalars(select(model)))
        assert [(row.id, row.name) for row in items] == [(item_id, "Original")]


@pytest.mark.asyncio
@pytest.mark.parametrize("model,repo_class,service_class,delete_method",
                         REFERENCE_CASES)
async def test_missing_delete_does_not_commit(
    login_api, monkeypatch, model, repo_class, service_class, delete_method,
):
    _, sessions, _, _ = login_api
    async with sessions() as db:
        repo = repo_class(db)
        commit = AsyncMock()
        monkeypatch.setattr(repo, "commit", commit)
        with pytest.raises(HTTPException) as caught:
            await getattr(service_class(repo), delete_method)(999)
        assert caught.value.status_code == 404
        commit.assert_not_awaited()
        assert not db.in_transaction()


@pytest.mark.asyncio
async def test_favorite_delete_transaction(login_api, monkeypatch):
    _, sessions, _, user_id = login_api
    async with sessions() as db:
        movie = MovieModel(
            name="Movie", year=2020, time=90, imdb=8, votes=5,
            description="Story", price=Decimal("5"),
            certification=CertificationModel(name="PG"),
        )
        db.add(movie)
        await db.flush()
        movie_id = movie.id
        favorite = MovieFavoriteModel(user_id=user_id, movie_id=movie_id)
        db.add(favorite)
        await db.commit()
        favorite_id = favorite.id
        repo = FavoriteRepository(db)
        assert await repo.delete(user_id, movie_id)
        await repo.rollback()
        assert await db.get(MovieFavoriteModel, favorite_id) is not None

        commit = AsyncMock(side_effect=SQLAlchemyError("private"))
        monkeypatch.setattr(repo, "commit", commit)
        with pytest.raises(HTTPException) as caught:
            await FavoriteService(repo, MovieRepository(db)).delete_favorite(
                user_id, movie_id,
            )
        assert caught.value.status_code == 503
        commit.assert_awaited_once()
        assert not db.in_transaction()
        assert await db.get(MovieFavoriteModel, favorite_id) is not None

        commit.reset_mock()
        with pytest.raises(HTTPException) as caught:
            await FavoriteService(repo, MovieRepository(db)).delete_favorite(
                user_id, 999,
            )
        assert caught.value.status_code == 404
        commit.assert_not_awaited()
        assert not db.in_transaction()

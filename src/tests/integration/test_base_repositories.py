from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    CertificationModel, DirectorModel, GenreModel, StarModel,
)
from src.repositories.accounts import AccountRepository
from src.repositories.cart import CartRepository
from src.repositories.tokens import TokenRepository
from src.repositories.base import BaseRepository, NamedEntityRepository
from src.repositories.certifications import CertificationRepository
from src.repositories.comments import CommentRepository
from src.repositories.directors import DirectorRepository
from src.repositories.favorites import FavoriteRepository
from src.repositories.genres import GenreRepository
from src.repositories.movies import MovieRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.ratings import RatingRepository
from src.repositories.reactions import ReactionRepository
from src.repositories.stars import StarRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_class", [
    AccountRepository, CertificationRepository, CommentRepository,
    DirectorRepository, FavoriteRepository, GenreRepository, MovieRepository,
    ProfileRepository, RatingRepository, ReactionRepository, StarRepository,
    CartRepository, TokenRepository,
])
async def test_repository_inherits_session_management(repository_class):
    db = AsyncMock(spec=AsyncSession)
    repository = repository_class(db)
    assert isinstance(repository, BaseRepository)
    assert repository.db is db
    db.commit.assert_not_awaited()
    db.rollback.assert_not_awaited()
    await repository.commit()
    await repository.rollback()
    db.commit.assert_awaited_once()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_class,model,getter", [
    (GenreRepository, GenreModel, "get_genre"),
    (StarRepository, StarModel, "get_star"),
    (DirectorRepository, DirectorModel, "get_director"),
    (CertificationRepository, CertificationModel, "get_certification"),
])
async def test_named_entity_crud_preserves_transaction(
    login_api, repository_class, model, getter,
):
    _, sessions, _, _ = login_api
    async with sessions() as db:
        repository = repository_class(db)
        assert isinstance(repository, NamedEntityRepository)
        assert repository.model is model
        assert await repository.get_by_id(999) is None
        assert not await repository.delete(999)

        entity = model(name="Original")
        await repository.save(entity)
        entity_id = entity.id
        assert entity_id is not None
        assert await repository.get_by_id(entity_id) is entity
        assert await getattr(repository, getter)(entity_id) is entity
        await repository.rollback()
        assert await repository.get_by_id(entity_id) is None

        entity = model(name="Saved")
        await repository.save(entity)
        entity_id = entity.id
        await repository.commit()
    async with sessions() as db:
        repository = repository_class(db)
        entity = await repository.get_by_id(entity_id)
        assert entity.name == "Saved"
        entity.name = "Updated"
        await repository.save(entity)
        await repository.commit()
    async with sessions() as db:
        repository = repository_class(db)
        assert (await repository.get_by_id(entity_id)).name == "Updated"
        assert await repository.delete(entity_id)
        await repository.rollback()
        assert await repository.get_by_id(entity_id) is not None
        assert await repository.delete(entity_id)
        await repository.commit()
    async with sessions() as db:
        assert await repository_class(db).get_by_id(entity_id) is None

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.api.dependencies import (
    get_comment_service, get_favorite_service, get_rating_service,
    get_reaction_service, get_account_service
)
from src.services.database_errors import database_errors
from src.services.movie_checks import get_movie_or_404
from src.database.models import GenreModel
from src.services.genres import GenreService


@pytest.mark.asyncio
async def test_database_scope_does_not_commit():
    repository = AsyncMock()
    async with database_errors(repository, detail="Unavailable"):
        await repository.save()
    repository.commit.assert_not_awaited()
    repository.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_named_entity_service_saves_and_deletes():
    repository = AsyncMock()
    repository.delete.return_value = True
    service = GenreService(repository)
    genre = GenreModel(id=1, name="Drama")
    response = await service.save(genre)
    assert response.id == 1 and response.name == "Drama"
    repository.save.assert_awaited_once_with(genre)
    repository.commit.assert_awaited_once()
    await service.delete_genre(1)
    repository.delete.assert_awaited_once_with(1)
    assert repository.commit.await_count == 2
    repository.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["query", "save", "commit"])
@pytest.mark.parametrize("conflict", [None, "Duplicate"])
async def test_database_error_translation_and_rollback(failure, conflict):
    repository = AsyncMock()
    getattr(repository, failure).side_effect = IntegrityError(
        "private", {}, Exception()
    )
    with pytest.raises(HTTPException) as caught:
        async with database_errors(
                repository, detail="Unavailable", conflict_detail=conflict
        ):
            await getattr(repository, failure)()
    assert caught.value.status_code == (409 if conflict else 503)
    assert caught.value.detail == (conflict or "Unavailable")
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_other_database_errors():
    repository = AsyncMock()
    with pytest.raises(HTTPException) as caught:
        async with database_errors(repository, detail="Unavailable"):
            raise SQLAlchemyError("private")
    assert caught.value.status_code == 503
    assert caught.value.detail == "Unavailable"
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    HTTPException(status_code=404, detail="Missing"),
    ValueError("Invalid response")
])
async def test_unexpected_and_http_errors_are_not_replaced(error):
    repository = AsyncMock()
    with pytest.raises(type(error)) as caught:
        async with database_errors(repository, detail="Unavailable"):
            raise error
    assert caught.value is error
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_movie_check_preserves_lock_and_loading_options():
    repository = AsyncMock()
    movie = object()
    repository.get_movie.return_value = movie
    assert await get_movie_or_404(
        repository, 12, lock=True, with_relations=True
    ) is movie
    repository.get_movie.assert_awaited_once_with(
        12, for_update=True, with_relations=True
    )
    repository.get_movie.return_value = None
    with pytest.raises(HTTPException) as caught:
        await get_movie_or_404(repository, 12)
    assert caught.value.status_code == 404


def test_injected_repositories_share_session():
    db = AsyncMock()
    for factory in (
            get_favorite_service, get_rating_service, get_reaction_service
    ):
        service = factory(db=db)
        assert service.repository.db is db
        assert service.movie_repository.db is db
    sender = AsyncMock()
    accounts = get_account_service(db=db, email_queue=sender)
    assert accounts.repository.db is db
    assert accounts.token_repository.db is db
    assert accounts.profile_repository.db is db
    assert accounts.cart_repository.db is db
    assert accounts.email_queue is sender
    comments = get_comment_service(db=db, email_queue=sender)
    assert comments.repository.db is db
    assert comments.movie_repository.db is db
    assert comments.account_repository.db is db
    assert comments.email_queue is sender

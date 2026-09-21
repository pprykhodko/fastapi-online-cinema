from typing import Any

from fastapi import APIRouter, Depends, Path, Response

from src.api.dependencies import get_genre_service
from src.schemas.common import ErrorResponseSchema
from src.schemas.movies import (
    GenreCreateRequestSchema, GenreResponseSchema, GenreUpdateRequestSchema,
    GenreWithMovieCountResponseSchema,
)
from src.security.dependencies import get_current_moderator
from src.services.genres import GenreService


router = APIRouter(
    responses={
        503: {"model": ErrorResponseSchema, "description": "Database unavailable"}
    }
)
write_responses: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponseSchema, "description": "Unauthorized."},
    403: {"model": ErrorResponseSchema, "description": "Moderator required."},
    409: {"model": ErrorResponseSchema, "description": "Duplicate genre name"}
}
not_found: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponseSchema, "description": "Genre not found."}
}


@router.get(
    "/", response_model=list[GenreWithMovieCountResponseSchema],
    summary="List genres with movie counts",
    description=(
        "Public list ordered by ID. Counts exclude soft-deleted movies; "
        "empty genres have count 0. Use GET /api/v1/movies/?genre_id={id} "
        "to browse movies belonging to a genre."
    ),
)
async def list_genres(
    service: GenreService = Depends(get_genre_service),
):
    return await service.list_genres()


@router.get(
    "/{genre_id}/", response_model=GenreResponseSchema,
    summary="Get a genre", description="Public lookup by genre ID.",
    responses=not_found,
)
async def get_genre(
    genre_id: int = Path(gt=0, le=2**31 - 1),
    service: GenreService = Depends(get_genre_service),
):
    return await service.get_genre(genre_id)


@router.post(
    "/", response_model=GenreResponseSchema, status_code=201,
    dependencies=[Depends(get_current_moderator)], responses=write_responses,
    summary="Create a genre",
    description=(
        "MODERATOR or ADMIN only. Supply name (1–100 characters). "
        "Surrounding whitespace is removed; the name must be unique."
    ),
)
async def create_genre(
    data: GenreCreateRequestSchema,
    service: GenreService = Depends(get_genre_service),
):
    return await service.create_genre(data)


@router.patch(
    "/{genre_id}/", response_model=GenreResponseSchema,
    dependencies=[Depends(get_current_moderator)],
    responses={**write_responses, **not_found}, summary="Rename a genre",
    description=(
        "MODERATOR or ADMIN only. Supply the new unique name "
        "(1–100 characters). Movie associations are preserved."
    ),
)
async def update_genre(
    data: GenreUpdateRequestSchema,
    genre_id: int = Path(gt=0, le=2**31 - 1),
    service: GenreService = Depends(get_genre_service),
):
    return await service.update_genre(genre_id, data)


@router.delete(
    "/{genre_id}/", status_code=204,
    dependencies=[Depends(get_current_moderator)],
    responses={
        **not_found, 401: write_responses[401], 403: write_responses[403],
    },
    summary="Delete a genre",
    description=(
        "MODERATOR or ADMIN only. Removes the genre and its movie "
        "associations, not the movies themselves. Returns an empty response."
    ),
)
async def delete_genre(
    genre_id: int = Path(gt=0, le=2**31 - 1),
    service: GenreService = Depends(get_genre_service),
):
    await service.delete_genre(genre_id)

    return Response(status_code=204)

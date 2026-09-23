from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from src.api.dependencies import get_movie_service
from src.schemas.common import ErrorResponseSchema
from src.schemas.movies import MovieListQuerySchema, MovieListResponseSchema
from src.schemas.movies import (
    MovieCreateRequestSchema, MovieDetailResponseSchema,
    MovieUpdateRequestSchema,
)
from src.security.dependencies import get_current_moderator
from src.services.movies import MovieService


router = APIRouter()


@router.get(
    "/",
    response_model=MovieListResponseSchema,
    summary="Browse the movie catalog",
    description=(
        "Public catalog; no access token required. Soft-deleted movies are "
        "excluded. Filters are combined with AND. Search matches a substring "
        "in the name, description, actor or director name (OR); % and _ are "
        "literal characters, not wildcards. Matching uses database "
        "case-insensitive comparison; Unicode behavior depends on the DB. "
        "Popularity means IMDb vote count. Default order: year descending, "
        "then id ascending to break ties. Missing prices sort last in both "
        "directions; these movies cannot be purchased. Total counts all "
        "matching movies before pagination. An empty or out-of-range page "
        "returns 200 with an empty items list. Each movie includes "
        "likes_count and dislikes_count across all users (0 if none)."
    ),
    responses={503: {
        "model": ErrorResponseSchema, "description": "Database unavailable.",
    }},
)
async def list_movies(
    query: Annotated[MovieListQuerySchema, Query()],
    service: MovieService = Depends(get_movie_service),
) -> MovieListResponseSchema:
    return await service.list_movies(query)


@router.get(
    "/{movie_id}/", response_model=MovieDetailResponseSchema,
    summary="Get movie details",
    description="Public movie details with all related catalog records.",
    responses={404: {"description": "Movie missing or deleted."},
               503: {"description": "Database unavailable."}},
)
async def get_movie(
    movie_id: int = Path(gt=0, le=2**31 - 1),
    service: MovieService = Depends(get_movie_service),
):
    return await service.get_movie(movie_id)


@router.post(
    "/", response_model=MovieDetailResponseSchema, status_code=201,
    dependencies=[Depends(get_current_moderator)], summary="Create a movie",
    description=(
        "ADMIN/MODERATOR only. Supply movie fields and existing "
        "certification, genre, star and director IDs. "
        "Missing related IDs return 422. "
        "The combination of name, year and duration must be unique. "
        "price=null makes the movie unavailable for purchase."
    ),
    responses={401: {"description": "Unauthorized."},
               403: {"description": "Moderator required."},
               409: {"description": "Conflicting movie or related records."},
               503: {"description": "Database unavailable."}},
)
async def create_movie(
    data: MovieCreateRequestSchema,
    service: MovieService = Depends(get_movie_service),
):
    return await service.save_movie(data)


@router.put(
    "/{movie_id}/", response_model=MovieDetailResponseSchema,
    dependencies=[Depends(get_current_moderator)], summary="Replace a movie",
    description=(
        "ADMIN/MODERATOR only. Full replacement using the creation fields. "
        "Omitted relation lists become empty; omitted meta_score/gross become "
        "null. Existing IDs are required for all references. ID and UUID "
        "remain unchanged. Saved order/payment prices are not modified."
    ),
    responses={401: {"description": "Unauthorized."},
               403: {"description": "Moderator required."},
               404: {"description": "Movie missing or deleted."},
               409: {"description": "Conflicting movie or related records."},
               503: {"description": "Database unavailable."}},
)
async def update_movie(
    data: MovieUpdateRequestSchema,
    movie_id: int = Path(gt=0, le=2**31 - 1),
    service: MovieService = Depends(get_movie_service),
):
    return await service.save_movie(data, movie_id)


@router.delete(
    "/{movie_id}/", status_code=204,
    dependencies=[Depends(get_current_moderator)], summary="Delete a movie",
    description=(
        "ADMIN/MODERATOR only. Soft deletion, preserving history. Paid orders "
        "or successful/refunded payments block deletion, even with confirm. "
        "If carts contain the movie, returns 409 before making changes; "
        "repeat with confirm=true to remove cart items and hide the movie."
    ),
    responses={401: {"description": "Unauthorized."},
               403: {"description": "Moderator required."},
               404: {"description": "Movie missing or deleted."},
               409: {"description": "Purchased movie or cart warning."},
               503: {"description": "Database unavailable."}},
)
async def delete_movie(
    movie_id: int = Path(gt=0, le=2**31 - 1),
    confirm: bool = Query(False, description="Confirm removal from carts."),
    service: MovieService = Depends(get_movie_service),
):
    await service.delete_movie(movie_id, confirm)
    return Response(status_code=204)

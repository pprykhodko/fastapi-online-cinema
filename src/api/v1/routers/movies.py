from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_movie_service
from src.schemas.common import ErrorResponseSchema
from src.schemas.movies import MovieListQuerySchema, MovieListResponseSchema
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
        "returns 200 with an empty items list."
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

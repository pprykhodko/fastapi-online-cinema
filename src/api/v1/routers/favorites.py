from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from src.api.dependencies import get_favorite_service
from src.database.models import UserModel
from src.schemas.common import ErrorResponseSchema
from src.schemas.interactions import (
    MovieFavoriteCreateRequestSchema,
    MovieFavoriteListQuerySchema,
    MovieFavoriteListResponseSchema,
    MovieFavoriteResponseSchema,
)
from src.security.dependencies import get_current_user
from src.services.favorites import FavoriteService


router = APIRouter(
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Unauthorized"
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Inactive account"
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Database unavailable"
        }
    }
)


@router.get(
    "/",
    response_model=MovieFavoriteListResponseSchema,
    summary="List your favorite movies",
    description=(
        "Requires an active account. Only your favorites are returned; "
        "deleted movies are hidden. Uses catalog parameters: page, per_page, "
        "year, min_imdb, genre_id, search, sort_by and sort_order. Search "
        "matches title, description, actors or directors. Popularity is IMDb "
        "vote count. Default order is year descending, then ID ascending; "
        "missing prices sort last. Filters combine with AND. Total is the "
        "matching count before pagination. Each item includes favorite ID, "
        "added_at and movie details."
    )
)
async def list_favorites(
    query: Annotated[MovieFavoriteListQuerySchema, Query()],
    current_user: UserModel = Depends(get_current_user),
    service: FavoriteService = Depends(get_favorite_service)
):
    """
    Return the user favorites with catalog pagination, search, filtering and sorting.

    Args:
        query (MovieFavoriteListQuerySchema): Validated pagination and any supported
            search, sort or filter options.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (FavoriteService): Injected service that performs the operation.

    Returns:
        MovieFavoriteListResponseSchema: Favorite records in requested catalog order and
            pagination totals.
    """
    return await service.list_favorites(current_user.id, query)


@router.post(
    "/",
    response_model=MovieFavoriteResponseSchema,
    status_code=201,
    summary="Add a movie to your favorites",
    description=(
        "Supply movie_id. The user is taken from your access token. "
        "Only existing, non-deleted movies can be added. A price is not "
        "required. Duplicate favorites return 409."
    ),
    responses={
        404: {
            "description": "Movie missing or deleted"
        },
        409: {
            "description": "Duplicate or conflicting favorite"
        }
    }
)
async def add_favorite(
    data: MovieFavoriteCreateRequestSchema,
    current_user: UserModel = Depends(get_current_user),
    service: FavoriteService = Depends(get_favorite_service)
):
    """
    Save a non-deleted movie to the user favorites, rejecting duplicates.

    Args:
        data (MovieFavoriteCreateRequestSchema): ID of the movie to add to favorites.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (FavoriteService): Injected service that performs the operation.

    Returns:
        MovieFavoriteResponseSchema: Favorite record, movie details and time added.
    """
    return await service.add_favorite(current_user.id, data.movie_id)


@router.delete(
    "/{movie_id}/",
    status_code=204,
    summary="Remove a favorite movie",
    description=(
        "Use the movie ID, not the favorite record ID. Removes only your "
        "favorite, not the movie itself. A hidden/deleted movie can also "
        "be removed from favorites. No body is returned."
    ),
    responses={
        404: {
            "description": "Movie is not in your favorites"
        }
    }
)
async def delete_favorite(
    movie_id: int = Path(gt=0, le=2**31 - 1),
    current_user: UserModel = Depends(get_current_user),
    service: FavoriteService = Depends(get_favorite_service)
):
    """
    Remove the selected movie from the user favorites.

    Args:
        movie_id (int): ID of the movie, not the cart or order item.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (FavoriteService): Injected service that performs the operation.

    Returns:
        Response: Empty HTTP 204 response.
    """
    await service.delete_favorite(current_user.id, movie_id)

    return Response(status_code=204)

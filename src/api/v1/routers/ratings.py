from fastapi import APIRouter, Depends, Path, Response

from src.api.dependencies import get_rating_service
from src.database.models import UserModel
from src.schemas.common import ErrorResponseSchema
from src.schemas.interactions import (
    MovieRatingRequestSchema, MovieRatingResponseSchema,
)
from src.security.dependencies import get_current_user
from src.services.ratings import RatingService


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
        404: {
            "model": ErrorResponseSchema,
            "description": "Movie or rating not found"
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Database unavailable"
        }
    }
)


@router.get(
    "/{movie_id}/rating/", response_model=MovieRatingResponseSchema,
    summary="Get your movie rating",
    description=(
            "Requires an active account. Returns only your rating, not other "
            "users' ratings. Missing/deleted movies or no own rating give 404."
    ),
)
async def get_rating(
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: RatingService = Depends(get_rating_service),
):
    return await service.get_rating(current_user.id, movie_id)


@router.put(
    "/{movie_id}/rating/", response_model=MovieRatingResponseSchema,
    summary="Rate a movie from 1 to 10",
    description=(
            "Requires an active account. Supply score: an integer from 1 to 10. "
            "Returns 201 for a new rating, 200 for replacement or an identical "
            "repeat. Only one rating per user/movie is stored. User ID comes "
            "from the access token. Deleted movies cannot receive ratings."
    ),
    responses={
        201: {"model": MovieRatingResponseSchema,
              "description": "Rating created"},
        409: {"model": ErrorResponseSchema,
              "description": "Concurrent data change; retry request"}
    }
)
async def set_rating(
        data: MovieRatingRequestSchema,
        response: Response,
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: RatingService = Depends(get_rating_service),
):
    rating, created = await service.set_rating(
        current_user.id, movie_id, data,
    )
    response.status_code = 201 if created else 200

    return rating


@router.delete(
    "/{movie_id}/rating/", status_code=204,
    summary="Remove your movie rating",
    description=(
            "Requires an active account. Deletes only your rating. "
            "Works even if the movie has been soft-deleted. Returns 404 if you "
            "have no rating. Keeps the movie and other users' ratings."
    ),
)
async def delete_rating(
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: RatingService = Depends(get_rating_service),
):
    await service.delete_rating(current_user.id, movie_id)

    return Response(status_code=204)

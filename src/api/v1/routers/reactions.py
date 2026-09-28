from fastapi import APIRouter, Depends, Path, Response

from src.api.dependencies import get_reaction_service
from src.database.models import UserModel
from src.schemas.common import ErrorResponseSchema
from src.schemas.interactions import (
    MovieReactionRequestSchema,
    MovieReactionResponseSchema
)
from src.security.dependencies import get_current_user
from src.services.reactions import ReactionService


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
            "description": "Movie or reaction not found",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Database unavailable"
        }
    }
)


@router.get(
    "/{movie_id}/reaction/",
    response_model=MovieReactionResponseSchema,
    summary="Get your movie reaction",
    description=(
            "Requires an active account. Returns only your reaction, not other "
            "users' reactions. Missing/deleted movies or no own reaction give 404."
    )
)
async def get_reaction(
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: ReactionService = Depends(get_reaction_service)
):
    """
    Return the user like or dislike for the selected movie.

    Args:
        movie_id (int): ID of the movie, not the cart or order item.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (ReactionService): Injected service that performs the operation.

    Returns:
        MovieReactionResponseSchema: User like or dislike and record timestamps.
    """
    return await service.get_reaction(current_user.id, movie_id)


@router.put(
    "/{movie_id}/reaction/",
    response_model=MovieReactionResponseSchema,
    summary="Like or dislike a movie",
    description=(
            "Requires an active account. Supply reaction: like or dislike. "
            "Returns 201 for a new reaction, 200 for replacement or an identical "
            "repeat. Only one reaction per user/movie is stored. User ID comes "
            "from the access token. Deleted movies cannot receive reactions."
    ),
    responses={
        201: {
            "model": MovieReactionResponseSchema,
            "description": "Reaction created"
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "Concurrent data change; retry request"
        }
    }
)
async def set_reaction(
        data: MovieReactionRequestSchema,
        response: Response,
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: ReactionService = Depends(get_reaction_service)
):
    """
    Create or replace the user movie reaction with a like or dislike.

    Args:
        data (MovieReactionRequestSchema): Requested like or dislike reaction.
        response (Response): HTTP response used to set status codes or cache-control
            headers.
        movie_id (int): ID of the movie, not the cart or order item.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (ReactionService): Injected service that performs the operation.

    Returns:
        MovieReactionResponseSchema: User like or dislike and record timestamps.
    """
    reaction, created = await service.set_reaction(
        current_user.id, movie_id, data
    )
    response.status_code = 201 if created else 200

    return reaction


@router.delete(
    "/{movie_id}/reaction/",
    status_code=204,
    summary="Remove your movie reaction",
    description=(
            "Requires an active account. Deletes only your reaction. "
            "Works even if the movie has been soft-deleted. Returns 404 if you "
            "have no reaction. Keeps the movie and other users' reactions."
    )
)
async def delete_reaction(
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: ReactionService = Depends(get_reaction_service)
):
    """
    Remove the user reaction to the selected movie.

    Args:
        movie_id (int): ID of the movie, not the cart or order item.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (ReactionService): Injected service that performs the operation.

    Returns:
        Response: Empty HTTP 204 response.
    """
    await service.delete_reaction(current_user.id, movie_id)

    return Response(status_code=204)

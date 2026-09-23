from fastapi import APIRouter, Depends, Path, Response

from src.api.dependencies import get_reaction_service
from src.database.models import UserModel
from src.schemas.common import ErrorResponseSchema
from src.schemas.interactions import (
    MovieReactionRequestSchema, MovieReactionResponseSchema,
)
from src.security.dependencies import get_current_user
from src.services.reactions import ReactionService


router = APIRouter(responses={
    401: {"model": ErrorResponseSchema, "description": "Unauthorized."},
    403: {"model": ErrorResponseSchema, "description": "Inactive account."},
    404: {
        "model": ErrorResponseSchema,
        "description": "Movie or reaction not found.",
    },
    503: {"model": ErrorResponseSchema, "description": "Database unavailable"},
})


@router.get(
    "/{movie_id}/reaction/", response_model=MovieReactionResponseSchema,
    summary="Get your movie reaction",
    description=(
        "Requires an active account. Returns only your reaction, not other "
        "users' reactions. Missing/deleted movies or no own reaction give 404."
    ),
)
async def get_reaction(
    movie_id: int = Path(gt=0, le=2**31 - 1),
    current_user: UserModel = Depends(get_current_user),
    service: ReactionService = Depends(get_reaction_service),
):
    return await service.get_reaction(current_user.id, movie_id)


@router.put(
    "/{movie_id}/reaction/", response_model=MovieReactionResponseSchema,
    summary="Like or dislike a movie",
    description=(
        "Requires an active account. Supply reaction: like or dislike. "
        "Returns 201 for a new reaction, 200 for replacement or an identical "
        "repeat. Only one reaction per user/movie is stored. User ID comes "
        "from the access token. Deleted movies cannot receive reactions."
    ),
    responses={
        201: {"model": MovieReactionResponseSchema,
              "description": "Reaction created."},
        409: {"model": ErrorResponseSchema,
              "description": "Concurrent data change; retry request."},
    },
)
async def set_reaction(
    data: MovieReactionRequestSchema,
    response: Response,
    movie_id: int = Path(gt=0, le=2**31 - 1),
    current_user: UserModel = Depends(get_current_user),
    service: ReactionService = Depends(get_reaction_service),
):
    reaction, created = await service.set_reaction(
        current_user.id, movie_id, data,
    )
    response.status_code = 201 if created else 200
    return reaction


@router.delete(
    "/{movie_id}/reaction/", status_code=204,
    summary="Remove your movie reaction",
    description=(
        "Requires an active account. Deletes only your reaction. "
        "Works even if the movie has been soft-deleted. Returns 404 if you "
        "have no reaction. Keeps the movie and other users' reactions."
    ),
)
async def delete_reaction(
    movie_id: int = Path(gt=0, le=2**31 - 1),
    current_user: UserModel = Depends(get_current_user),
    service: ReactionService = Depends(get_reaction_service),
):
    await service.delete_reaction(current_user.id, movie_id)
    return Response(status_code=204)

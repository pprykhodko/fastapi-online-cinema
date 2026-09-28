from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from src.api.dependencies import get_comment_service
from src.database.models import UserModel
from src.schemas.common import ErrorResponseSchema
from src.schemas.interactions import (
    CommentLikeResponseSchema,
    MovieCommentCreateRequestSchema,
    MovieCommentListQuerySchema,
    MovieCommentListResponseSchema,
    MovieCommentResponseSchema
)
from src.security.dependencies import get_current_user
from src.services.comments import CommentService


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
            "description": "Resource not found"
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "Data changed; retry"
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Database unavailable"
        }
    }
)


@router.get(
    "/movies/{movie_id}/comments/",
    response_model=MovieCommentListResponseSchema,
    summary="List movie comments and replies",
    description=(
            "Public paginated list, oldest first. Replies are flat items with "
            "parent_id identifying their parent. Deleted movies return 404."
    )
)
async def list_comments(
        query: Annotated[MovieCommentListQuerySchema, Query()],
        movie_id: int = Path(gt=0, le=2**31 - 1),
        service: CommentService = Depends(get_comment_service)
):
    """
    Return paginated comments and replies for a non-deleted movie.

    Args:
        query (MovieCommentListQuerySchema): Validated pagination and any supported
            search, sort or filter options.
        movie_id (int): ID of the movie, not the cart or order item.
        service (CommentService): Injected service that performs the operation.

    Returns:
        MovieCommentListResponseSchema: Comment page and pagination totals.
    """
    return await service.list_comments(movie_id, query)


@router.post(
    "/movies/{movie_id}/comments/",
    status_code=201,
    response_model=MovieCommentResponseSchema,
    summary="Write a comment or reply",
    description=(
            "Requires an active account. Supply content and optionally parent_id "
            "for a reply to a comment on this movie. The parent author receives "
            "a background email after saving, except for replies to yourself. "
            "Email delivery is best effort and does not undo a saved comment."
    )
)
async def create_comment(
        data: MovieCommentCreateRequestSchema,
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: CommentService = Depends(get_comment_service)
):
    """
    Save a comment or reply and queue a notification for another reply recipient.

    Args:
        data (MovieCommentCreateRequestSchema): Comment text and optional parent comment
            ID for replies.
        movie_id (int): ID of the movie, not the cart or order item.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (CommentService): Injected service that performs the operation.

    Returns:
        MovieCommentResponseSchema: Comment content, author, movie and optional parent
            ID.
    """
    return await service.create_comment(current_user.id, movie_id, data)


@router.put(
    "/comments/{comment_id}/like/",
    response_model=CommentLikeResponseSchema,
    summary="Like a comment",
    description=(
            "Requires an active account. Returns 201 for a new like, 200 for a "
            "repeat. Only a new like notifies the author by background email; "
            "self-likes do not send email. Deleted movies cannot receive likes."
    ),
    responses={
        201: {
            "model": CommentLikeResponseSchema
        }
    }
)
async def like_comment(
        response: Response,
        comment_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: CommentService = Depends(get_comment_service)
):
    """
    Create a comment like if absent and notify another author only for a new like.

    Args:
        response (Response): HTTP response used to set status codes or cache-control
            headers.
        comment_id (int): ID of the comment.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (CommentService): Injected service that performs the operation.

    Returns:
        CommentLikeResponseSchema: Saved comment like with its author and creation time.
    """
    like, created = await service.like_comment(current_user.id, comment_id)
    response.status_code = 201 if created else 200

    return like


@router.delete(
    "/comments/{comment_id}/like/",
    status_code=204,
    summary="Remove your comment like",
    description=(
            "Requires an active account. Removes only your like, even if the "
            "movie was soft-deleted. Returns 404 if you have no like."
    )
)
async def delete_like(
        comment_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: CommentService = Depends(get_comment_service)
):
    """
    Remove the user like from the selected comment.

    Args:
        comment_id (int): ID of the comment.
        current_user (UserModel): Authenticated account supplied by the access-token
            dependency.
        service (CommentService): Injected service that performs the operation.

    Returns:
        Response: Empty HTTP 204 response.
    """
    await service.delete_like(current_user.id, comment_id)

    return Response(status_code=204)

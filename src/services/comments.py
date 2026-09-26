from fastapi import HTTPException, status

from src.services.database_errors import database_errors
from src.database.models import CommentLikeModel, MovieCommentModel
from src.notifications.queue import EmailQueue
from src.repositories.comments import CommentRepository
from src.repositories.accounts import AccountRepository
from src.repositories.movies import MovieRepository
from src.services.movie_checks import get_movie_or_404
from src.schemas.interactions import (
    CommentLikeResponseSchema,
    MovieCommentCreateRequestSchema,
    MovieCommentListQuerySchema,
    MovieCommentListResponseSchema,
    MovieCommentResponseSchema
)


class CommentService:
    def __init__(
            self,
            repository: CommentRepository,
            email_queue: EmailQueue,
            movie_repository: MovieRepository,
            account_repository: AccountRepository
    ):
        self.repository = repository
        self.email_queue = email_queue
        self.movie_repository = movie_repository
        self.account_repository = account_repository

    async def list_comments(
            self,
            movie_id: int,
            query: MovieCommentListQuerySchema
    ) -> MovieCommentListResponseSchema:
        async with database_errors(self.repository, detail="Comments are unavailable"):
            await get_movie_or_404(self.movie_repository, movie_id)

            comments, total = await self.repository.list_comments(
                movie_id,
                query.page,
                query.per_page
            )

            return MovieCommentListResponseSchema(
                items=[
                    MovieCommentResponseSchema.model_validate(comment)
                    for comment in comments
                ],
                total=total,
                page=query.page,
                per_page=query.per_page
            )

    async def create_comment(
            self,
            user_id: int,
            movie_id: int,
            data: MovieCommentCreateRequestSchema
    ) -> MovieCommentResponseSchema:
        async with database_errors(
                self.repository,
                detail="Comment could not be saved",
                conflict_detail="Comment data changed. Try again."
        ):
            movie = await get_movie_or_404(self.movie_repository, movie_id, lock=True)

            email = None

            if data.parent_id is not None:
                parent = await self.repository.get_comment(data.parent_id)

                if parent is None or parent.movie_id != movie_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Parent comment not found"
                    )

                if parent.user_id != user_id:
                    email = await self.account_repository.get_active_email(
                        parent.user_id
                    )

            comment = MovieCommentModel(
                user_id=user_id,
                movie_id=movie_id,
                content=data.content,
                parent_id=data.parent_id
            )
            await self.repository.save(comment)
            response = MovieCommentResponseSchema.model_validate(comment)
            movie_name = movie.name
            await self.repository.commit()

        if email and data.parent_id is not None:
            await self.email_queue.send_comment_notification(
                email,
                movie_name,
                data.parent_id,
                "reply"
            )

        return response

    async def like_comment(
            self,
            user_id: int,
            comment_id: int
    ) -> tuple[CommentLikeResponseSchema, bool]:
        async with database_errors(
                self.repository,
                detail="Like could not be saved",
                conflict_detail="Like data changed. Try again."
        ):
            comment = await self.repository.get_comment(comment_id)

            if comment is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Comment not found"
                )

            movie = await get_movie_or_404(
                self.movie_repository,
                comment.movie_id,
                lock=True
            )

            like = await self.repository.get_like(user_id, comment_id)
            created = like is None
            email = None

            if like is None:
                like = CommentLikeModel(user_id=user_id, comment_id=comment_id)
                await self.repository.save(like)

                if comment.user_id != user_id:
                    email = await self.account_repository.get_active_email(
                        comment.user_id
                    )

            response = CommentLikeResponseSchema.model_validate(like)
            movie_name = movie.name
            await self.repository.commit()

        if email:
            await self.email_queue.send_comment_notification(
                email,
                movie_name,
                comment_id,
                "like"
            )

        return response, created

    async def delete_like(self, user_id: int, comment_id: int) -> None:
        async with database_errors(self.repository, detail="Like could not be removed"):
            if not await self.repository.delete_like(user_id, comment_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="You have not liked this comment"
                )

            await self.repository.commit()

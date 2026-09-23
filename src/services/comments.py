from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import CommentLikeModel, MovieCommentModel
from src.notifications.emails import EmailSender
from src.repositories.comments import CommentRepository
from src.schemas.interactions import (
    CommentLikeResponseSchema, MovieCommentCreateRequestSchema,
    MovieCommentListQuerySchema, MovieCommentListResponseSchema,
    MovieCommentResponseSchema,
)


class CommentService:
    def __init__(
            self, repository: CommentRepository, email_sender: EmailSender
    ):
        self.repository = repository
        self.email_sender = email_sender

    async def list_comments(
            self, movie_id: int, query: MovieCommentListQuerySchema
    ) -> MovieCommentListResponseSchema:
        try:
            if await self.repository.get_movie(movie_id) is None:
                raise HTTPException(404, "Movie not found")

            comments, total = await self.repository.list_comments(
                movie_id, query.page, query.per_page
            )

            return MovieCommentListResponseSchema(
                items=[MovieCommentResponseSchema.model_validate(comment)
                       for comment in comments],
                total=total, page=query.page, per_page=query.per_page
            )

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(503, "Comments are unavailable") from error

    async def create_comment(
            self, user_id: int, movie_id: int,
            data: MovieCommentCreateRequestSchema, tasks: BackgroundTasks
    ) -> MovieCommentResponseSchema:
        try:
            movie = await self.repository.get_movie(movie_id, lock=True)

            if movie is None:
                raise HTTPException(404, "Movie not found")

            email = None

            if data.parent_id is not None:
                parent = await self.repository.get_comment(data.parent_id)

                if parent is None or parent.movie_id != movie_id:
                    raise HTTPException(404, "Parent comment not found")

                if parent.user_id != user_id:
                    email = await self.repository.get_email(parent.user_id)

            comment = MovieCommentModel(
                user_id=user_id, movie_id=movie_id,
                content=data.content, parent_id=data.parent_id
            )
            await self.repository.save(comment)
            response = MovieCommentResponseSchema.model_validate(comment)
            movie_name = movie.name
            await self.repository.commit()

        except HTTPException:
            await self.repository.rollback()
            raise

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "Comment data changed. Try again.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(503, "Comment could not be saved") from error

        if email and data.parent_id is not None:
            tasks.add_task(
                self.email_sender.send_comment_notification_background,
                email, movie_name, data.parent_id, "reply"
            )

        return response

    async def like_comment(
            self, user_id: int, comment_id: int, tasks: BackgroundTasks
    ) -> tuple[CommentLikeResponseSchema, bool]:
        try:
            comment = await self.repository.get_comment(comment_id)

            if comment is None:
                raise HTTPException(404, "Comment not found")

            movie = await self.repository.get_movie(
                comment.movie_id, lock=True
            )

            if movie is None:
                raise HTTPException(404, "Movie not found")

            like = await self.repository.get_like(user_id, comment_id)
            created = like is None
            email = None

            if like is None:
                like = CommentLikeModel(user_id=user_id, comment_id=comment_id)
                await self.repository.save(like)

                if comment.user_id != user_id:
                    email = await self.repository.get_email(comment.user_id)

            response = CommentLikeResponseSchema.model_validate(like)
            movie_name = movie.name
            await self.repository.commit()

        except HTTPException:
            await self.repository.rollback()
            raise

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "Like data changed. Try again.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(503, "Like could not be saved") from error

        if email:
            tasks.add_task(
                self.email_sender.send_comment_notification_background,
                email, movie_name, comment_id, "like"
            )

        return response, created

    async def delete_like(self, user_id: int, comment_id: int) -> None:
        try:
            if not await self.repository.delete_like(user_id, comment_id):
                raise HTTPException(404, "You have not liked this comment.")

            await self.repository.commit()

        except HTTPException:
            await self.repository.rollback()
            raise

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(503, "Like could not be removed") from error

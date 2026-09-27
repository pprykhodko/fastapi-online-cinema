from sqlalchemy import delete, func, select

from src.repositories.base import BaseRepository
from src.database.models import (
    CommentLikeModel,
    MovieCommentModel
)


class CommentRepository(BaseRepository):
    async def get_comment(self, comment_id: int) -> MovieCommentModel | None:
        """
        Look up a comment by its primary key.

        The caller controls the transaction commit.

        Args:
            comment_id (int): ID of the comment.

        Returns:
            MovieCommentModel | None: Matching database record(s), or None when allowed
                and not found.
        """
        return await self.db.get(MovieCommentModel, comment_id)

    async def list_comments(
            self,
            movie_id: int,
            page: int,
            per_page: int
    ) -> tuple[list[MovieCommentModel], int]:
        """
        Load a page of movie comments in ID order and count all matches.

        The caller controls the transaction commit.

        Args:
            movie_id (int): ID of the movie, not the cart or order item.
            page (int): Page number starting at 1.
            per_page (int): Maximum number of records on one page.

        Returns:
            tuple[list[MovieCommentModel], int]: Records on this page and the total
                count before pagination.
        """
        condition = MovieCommentModel.movie_id == movie_id
        total = await self.db.scalar(
            select(func.count())
            .select_from(MovieCommentModel)
            .where(condition)
        )
        result = await self.db.scalars(
            select(MovieCommentModel).where(condition)
            .order_by(MovieCommentModel.id)
            .offset((page - 1) * per_page).limit(per_page)
        )

        return list(result), total or 0

    async def get_like(self, user_id: int, comment_id: int) -> CommentLikeModel | None:
        """
        Look up the user like on a comment.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            comment_id (int): ID of the comment.

        Returns:
            CommentLikeModel | None: Matching database record(s), or None when allowed
                and not found.
        """
        return await self.db.scalar(
            select(CommentLikeModel)
            .where(
                CommentLikeModel.user_id == user_id,
                CommentLikeModel.comment_id == comment_id
            )
        )

    async def save(self, item: MovieCommentModel | CommentLikeModel) -> None:
        """
        Add and flush the supplied record without committing the shared transaction.

        Args:
            item (MovieCommentModel | CommentLikeModel): ORM record supplied for this
                database operation.
        """
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)

    async def delete_like(self, user_id: int, comment_id: int) -> bool:
        """
        Delete the user comment like without committing and report whether it existed.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            comment_id (int): ID of the comment.

        Returns:
            bool: True if a matching record was deleted; otherwise False.
        """
        deleted_id = await self.db.scalar(
            delete(CommentLikeModel)
            .where(
                CommentLikeModel.user_id == user_id,
                CommentLikeModel.comment_id == comment_id
            )
            .returning(CommentLikeModel.id)
        )

        return deleted_id is not None

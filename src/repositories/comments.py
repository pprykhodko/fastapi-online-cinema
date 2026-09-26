from sqlalchemy import delete, func, select

from src.repositories.base import BaseRepository
from src.database.models import (
    CommentLikeModel,
    MovieCommentModel
)


class CommentRepository(BaseRepository):
    async def get_comment(self, comment_id: int) -> MovieCommentModel | None:
        return await self.db.get(MovieCommentModel, comment_id)

    async def list_comments(
            self,
            movie_id: int,
            page: int,
            per_page: int
    ) -> tuple[list[MovieCommentModel], int]:
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
        return await self.db.scalar(
            select(CommentLikeModel)
            .where(
                CommentLikeModel.user_id == user_id,
                CommentLikeModel.comment_id == comment_id
            )
        )

    async def save(self, item: MovieCommentModel | CommentLikeModel) -> None:
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)

    async def delete_like(self, user_id: int, comment_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(CommentLikeModel)
            .where(
                CommentLikeModel.user_id == user_id,
                CommentLikeModel.comment_id == comment_id
            )
            .returning(CommentLikeModel.id)
        )

        return deleted_id is not None

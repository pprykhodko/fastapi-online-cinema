from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    CommentLikeModel, MovieCommentModel, MovieModel, UserModel,
)


class CommentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_movie(
            self, movie_id: int, lock: bool = False
    ) -> MovieModel | None:
        stmt = select(MovieModel).where(
            MovieModel.id == movie_id, MovieModel.is_deleted.is_(False)
            )

        if lock:
            stmt = stmt.with_for_update()

        return await self.db.scalar(stmt)

    async def get_comment(self, comment_id: int) -> MovieCommentModel | None:
        return await self.db.get(MovieCommentModel, comment_id)

    async def list_comments(
            self, movie_id: int, page: int, per_page: int
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

    async def get_email(self, user_id: int) -> str | None:
        return await self.db.scalar(
            select(UserModel.email)
            .where(
                UserModel.id == user_id, UserModel.is_active.is_(True)
            )
        )

    async def get_like(
            self, user_id: int, comment_id: int
    ) -> CommentLikeModel | None:
        return await self.db.scalar(
            select(CommentLikeModel)
            .where(
                CommentLikeModel.user_id == user_id, CommentLikeModel.comment_id == comment_id
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
                CommentLikeModel.user_id == user_id, CommentLikeModel.comment_id == comment_id
            ).returning(CommentLikeModel.id)
        )

        return deleted_id is not None

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

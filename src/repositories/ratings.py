from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import MovieModel, MovieRatingModel


class RatingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def movie_exists(self, movie_id: int, lock: bool = False) -> bool:
        stmt = select(MovieModel.id).where(
            MovieModel.id == movie_id, MovieModel.is_deleted.is_(False),
            )

        if lock:
            stmt = stmt.with_for_update()

        return await self.db.scalar(stmt) is not None

    async def get_rating(
            self, user_id: int, movie_id: int,
    ) -> MovieRatingModel | None:
        return await self.db.scalar(select(MovieRatingModel).where(
            MovieRatingModel.user_id == user_id,
            MovieRatingModel.movie_id == movie_id,
            ))

    async def save(self, rating: MovieRatingModel) -> None:
        self.db.add(rating)
        await self.db.flush()
        await self.db.refresh(rating)

    async def delete(self, user_id: int, movie_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(MovieRatingModel).where(
                MovieRatingModel.user_id == user_id,
                MovieRatingModel.movie_id == movie_id,
                ).returning(MovieRatingModel.id)
        )

        return deleted_id is not None

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

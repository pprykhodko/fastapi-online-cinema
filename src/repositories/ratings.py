from sqlalchemy import delete, select

from src.repositories.base import BaseRepository
from src.database.models import MovieRatingModel


class RatingRepository(BaseRepository):
    async def get_rating(self, user_id: int, movie_id: int) -> MovieRatingModel | None:
        return await self.db.scalar(
            select(MovieRatingModel)
            .where(
                MovieRatingModel.user_id == user_id,
                MovieRatingModel.movie_id == movie_id
            )
        )

    async def save(self, rating: MovieRatingModel) -> None:
        self.db.add(rating)
        await self.db.flush()
        await self.db.refresh(rating)

    async def delete(self, user_id: int, movie_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(MovieRatingModel)
            .where(
                MovieRatingModel.user_id == user_id,
                MovieRatingModel.movie_id == movie_id
            )
            .returning(MovieRatingModel.id)
        )

        return deleted_id is not None

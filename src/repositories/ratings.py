from sqlalchemy import delete, select

from src.repositories.base import BaseRepository
from src.database.models import MovieRatingModel


class RatingRepository(BaseRepository):
    async def get_rating(self, user_id: int, movie_id: int) -> MovieRatingModel | None:
        """
        Look up the user rating record for the movie.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            MovieRatingModel | None: Matching database record(s), or None when allowed
                and not found.
        """
        return await self.db.scalar(
            select(MovieRatingModel)
            .where(
                MovieRatingModel.user_id == user_id,
                MovieRatingModel.movie_id == movie_id
            )
        )

    async def save(self, rating: MovieRatingModel) -> None:
        """
        Add and flush the supplied record without committing the shared transaction.

        Args:
            rating (MovieRatingModel): IMDb rating to validate.
        """
        self.db.add(rating)
        await self.db.flush()
        await self.db.refresh(rating)

    async def delete(self, user_id: int, movie_id: int) -> bool:
        """
        Delete the matching record without committing and report whether it existed.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            bool: True if a matching record was deleted; otherwise False.
        """
        deleted_id = await self.db.scalar(
            delete(MovieRatingModel)
            .where(
                MovieRatingModel.user_id == user_id,
                MovieRatingModel.movie_id == movie_id
            )
            .returning(MovieRatingModel.id)
        )

        return deleted_id is not None

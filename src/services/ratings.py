from fastapi import HTTPException, status

from src.services.database_errors import database_errors
from src.database.models import MovieRatingModel
from src.repositories.ratings import RatingRepository
from src.repositories.movies import MovieRepository
from src.services.movie_checks import get_movie_or_404
from src.schemas.interactions import (
    MovieRatingRequestSchema,
    MovieRatingResponseSchema
)


class RatingService:
    def __init__(
            self,
            repository: RatingRepository,
            movie_repository: MovieRepository
    ):
        """
        Initialize RatingService with its required dependencies.

        Args:
            repository (RatingRepository): Repository used for database operations and
                the shared transaction.
            movie_repository (MovieRepository): Repository for movie data using the
                shared session.
        """
        self.repository = repository
        self.movie_repository = movie_repository

    async def get_rating(
            self,
            user_id: int,
            movie_id: int
    ) -> MovieRatingResponseSchema:
        """
        Return the user rating for the selected movie.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            MovieRatingResponseSchema: User movie score and record timestamps.

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
        async with database_errors(
                self.repository,
                detail="Ratings are temporarily unavailable"
        ):
            await get_movie_or_404(self.movie_repository, movie_id)

            rating = await self.repository.get_rating(user_id, movie_id)

        if rating is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You have not rated this movie"
            )

        return MovieRatingResponseSchema.model_validate(rating)

    async def set_rating(
            self,
            user_id: int,
            movie_id: int,
            data: MovieRatingRequestSchema
    ) -> tuple[MovieRatingResponseSchema, bool]:
        """
        Create or replace the user movie rating on the 1-10 scale.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.
            data (MovieRatingRequestSchema): Integer movie score from 1 to 10.

        Returns:
            tuple[MovieRatingResponseSchema, bool]: Response data and True if a new
                record was created.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        async with database_errors(
                self.repository,
                detail="The rating could not be saved",
                conflict_detail="Rating data changed. Please repeat the request."
        ):
            await get_movie_or_404(self.movie_repository, movie_id, lock=True)

            rating = await self.repository.get_rating(user_id, movie_id)
            created = rating is None

            if rating is None:
                rating = MovieRatingModel(
                    user_id=user_id,
                    movie_id=movie_id,
                    score=data.score
                )

            else:
                rating.score = data.score

            await self.repository.save(rating)
            response = MovieRatingResponseSchema.model_validate(rating)
            await self.repository.commit()

            return response, created

    async def delete_rating(self, user_id: int, movie_id: int) -> None:
        """
        Remove the user rating for the selected movie.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
        async with database_errors(
                self.repository,
                detail="The rating could not be removed"
        ):
            deleted = await self.repository.delete(user_id, movie_id)

            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="You have not rated this movie"
                )

            await self.repository.commit()

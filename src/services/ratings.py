from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import MovieRatingModel
from src.repositories.ratings import RatingRepository
from src.schemas.interactions import (
    MovieRatingRequestSchema, MovieRatingResponseSchema,
)


class RatingService:
    def __init__(self, repository: RatingRepository):
        self.repository = repository

    async def get_rating(
            self, user_id: int, movie_id: int,
    ) -> MovieRatingResponseSchema:
        try:
            if not await self.repository.movie_exists(movie_id):
                raise HTTPException(404, "Movie not found.")

            rating = await self.repository.get_rating(user_id, movie_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Ratings are temporarily unavailable.",
            ) from error

        if rating is None:
            raise HTTPException(404, "You have not rated this movie.")

        return MovieRatingResponseSchema.model_validate(rating)

    async def set_rating(
            self, user_id: int, movie_id: int, data: MovieRatingRequestSchema,
    ) -> tuple[MovieRatingResponseSchema, bool]:
        try:
            if not await self.repository.movie_exists(movie_id, lock=True):
                raise HTTPException(404, "Movie not found.")

            rating = await self.repository.get_rating(user_id, movie_id)
            created = rating is None

            if rating is None:
                rating = MovieRatingModel(
                    user_id=user_id, movie_id=movie_id, score=data.score,
                )

            else:
                rating.score = data.score
            await self.repository.save(rating)
            response = MovieRatingResponseSchema.model_validate(rating)
            await self.repository.commit()

            return response, created

        except HTTPException:
            await self.repository.rollback()
            raise

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "Rating data changed. Please repeat the request.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The rating could not be saved.",
            ) from error

    async def delete_rating(self, user_id: int, movie_id: int) -> None:
        try:
            deleted = await self.repository.delete(user_id, movie_id)

            if not deleted:
                raise HTTPException(404, "You have not rated this movie.")

            await self.repository.commit()

        except HTTPException:
            await self.repository.rollback()
            raise

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The rating could not be removed.",
            ) from error

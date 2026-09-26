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
        self.repository = repository
        self.movie_repository = movie_repository

    async def get_rating(
            self,
            user_id: int,
            movie_id: int
    ) -> MovieRatingResponseSchema:
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

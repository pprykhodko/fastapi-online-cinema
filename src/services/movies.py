from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from src.repositories.movies import MovieRepository
from src.schemas.movies import (
    MovieListItemResponseSchema, MovieListQuerySchema, MovieListResponseSchema,
)


class MovieService:
    def __init__(self, repository: MovieRepository):
        self.repository = repository

    async def list_movies(
        self, query: MovieListQuerySchema,
    ) -> MovieListResponseSchema:
        try:
            movies, total = await self.repository.list_movies(query)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The movie catalog is temporarily unavailable.",
            ) from error

        return MovieListResponseSchema(
            items=[MovieListItemResponseSchema.model_validate(movie)
                   for movie in movies],
            total=total, page=query.page, per_page=query.per_page,
        )

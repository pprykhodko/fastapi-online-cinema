from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import MovieFavoriteModel
from src.repositories.favorites import FavoriteRepository
from src.schemas.interactions import (
    MovieFavoriteListQuerySchema, MovieFavoriteListResponseSchema,
    MovieFavoriteResponseSchema,
)


class FavoriteService:
    def __init__(self, repository: FavoriteRepository):
        self.repository = repository

    async def list_favorites(
            self, user_id: int, query: MovieFavoriteListQuerySchema
    ) -> MovieFavoriteListResponseSchema:
        try:
            favorites, total = await self.repository.list_favorites(
                user_id, query
            )

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Favorites are temporarily unavailable."
            ) from error

        return MovieFavoriteListResponseSchema(
            items=[MovieFavoriteResponseSchema.model_validate(favorite)
                   for favorite in favorites],
            total=total, page=query.page, per_page=query.per_page
        )

    async def add_favorite(
            self, user_id: int, movie_id: int,
    ) -> MovieFavoriteResponseSchema:
        try:
            movie = await self.repository.get_movie(movie_id)

            if movie is None:
                raise HTTPException(404, "Movie not found.")

            favorite = MovieFavoriteModel(user_id=user_id, movie=movie)
            await self.repository.add(favorite)

            response = MovieFavoriteResponseSchema.model_validate(favorite)
            await self.repository.commit()

            return response

        except HTTPException:
            await self.repository.rollback()
            raise

        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "The movie is already in favorites or its data changed.",
            ) from error

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(503, "Favorite could not be saved.") from error

    async def delete_favorite(self, user_id: int, movie_id: int) -> None:
        try:
            deleted = await self.repository.delete(user_id, movie_id)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "Favorite could not be removed.",
            ) from error

        if not deleted:
            raise HTTPException(404, "Movie is not in your favorites.")

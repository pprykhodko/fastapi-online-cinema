from fastapi import HTTPException, status

from src.services.database_errors import database_errors
from src.database.models import MovieFavoriteModel
from src.repositories.favorites import FavoriteRepository
from src.repositories.movies import MovieRepository
from src.services.movie_checks import get_movie_or_404
from src.schemas.interactions import (
    MovieFavoriteListQuerySchema, MovieFavoriteListResponseSchema,
    MovieFavoriteResponseSchema,
)


class FavoriteService:
    def __init__(
            self,
            repository: FavoriteRepository,
            movie_repository: MovieRepository
    ):
        self.repository = repository
        self.movie_repository = movie_repository

    async def list_favorites(
            self,
            user_id: int,
            query: MovieFavoriteListQuerySchema
    ) -> MovieFavoriteListResponseSchema:
        async with database_errors(
                self.repository,
                detail="Favorites are temporarily unavailable"
        ):
            movies, total = await self.movie_repository.list_movies(
                query,
                favorite_user_id=user_id
            )
            favorites = await self.repository.get_for_movies(
                user_id,
                [movie.id for movie in movies]
            )

        return MovieFavoriteListResponseSchema(
            items=[
                MovieFavoriteResponseSchema.model_validate(favorite)
                for favorite in favorites
            ],
            total=total,
            page=query.page,
            per_page=query.per_page
        )

    async def add_favorite(
            self,
            user_id: int,
            movie_id: int
    ) -> MovieFavoriteResponseSchema:
        async with database_errors(
                self.repository,
                detail="Favorite could not be saved.",
                conflict_detail="The movie is already in favorites or its data changed"
        ):
            movie = await get_movie_or_404(
                self.movie_repository,
                movie_id,
                lock=True,
                with_relations=True
            )

            favorite = MovieFavoriteModel(user_id=user_id, movie=movie)
            await self.repository.add(favorite)

            response = MovieFavoriteResponseSchema.model_validate(favorite)
            await self.repository.commit()

            return response

    async def delete_favorite(self, user_id: int, movie_id: int) -> None:
        async with database_errors(
                self.repository,
                detail="Favorite could not be removed"
        ):
            deleted = await self.repository.delete(user_id, movie_id)

            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Movie is not in your favorites"
                )

            await self.repository.commit()

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
        """
        Initialize FavoriteService with its required dependencies.

        Args:
            repository (FavoriteRepository): Repository used for database operations and
                the shared transaction.
            movie_repository (MovieRepository): Repository for movie data using the
                shared session.
        """
        self.repository = repository
        self.movie_repository = movie_repository

    async def list_favorites(
            self,
            user_id: int,
            query: MovieFavoriteListQuerySchema
    ) -> MovieFavoriteListResponseSchema:
        """
        Return the user favorites with catalog pagination, search, filtering and
        sorting.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            query (MovieFavoriteListQuerySchema): Validated pagination and any supported
                search, sort or filter options.

        Returns:
            MovieFavoriteListResponseSchema: Favorite records in requested catalog order
                and pagination totals.

        Raises:
            HTTPException: The requested data cannot be loaded from the database.
        """
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
        """
        Save a non-deleted movie to the user favorites, rejecting duplicates.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            MovieFavoriteResponseSchema: Favorite record, movie details and time added.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
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
        """
        Remove the selected movie from the user favorites.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
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

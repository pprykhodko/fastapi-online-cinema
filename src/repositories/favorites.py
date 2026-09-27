from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from src.repositories.base import BaseRepository
from src.database.models import MovieFavoriteModel


class FavoriteRepository(BaseRepository):
    async def get_for_movies(
            self,
            user_id: int,
            movie_ids: list[int]
    ) -> list[MovieFavoriteModel]:
        """
        Load the user favorites in the order of the supplied movie IDs.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_ids (list[int]): Movie IDs to include in the operation.

        Returns:
            list[MovieFavoriteModel]: Requested database record(s).
        """
        if not movie_ids:
            return []

        favorites = await self.db.scalars(
            select(MovieFavoriteModel)
            .where(
                MovieFavoriteModel.user_id == user_id,
                MovieFavoriteModel.movie_id.in_(movie_ids)
            )
            .options(joinedload(MovieFavoriteModel.movie)))
        by_movie = {favorite.movie_id: favorite for favorite in favorites}

        return [by_movie[movie_id] for movie_id in movie_ids if movie_id in by_movie]

    async def add(self, favorite: MovieFavoriteModel) -> None:
        """
        Add and flush the supplied record without committing the shared transaction.

        Args:
            favorite (MovieFavoriteModel): ORM record supplied for this database
                operation.
        """
        self.db.add(favorite)
        await self.db.flush()

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
            delete(MovieFavoriteModel)
            .where(
                MovieFavoriteModel.user_id == user_id,
                MovieFavoriteModel.movie_id == movie_id
            )
            .returning(MovieFavoriteModel.id)
        )

        return deleted_id is not None

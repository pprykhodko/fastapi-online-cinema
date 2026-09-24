from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.database.models import MovieFavoriteModel


class FavoriteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_movies(
        self, user_id: int, movie_ids: list[int],
    ) -> list[MovieFavoriteModel]:
        if not movie_ids:
            return []

        favorites = await self.db.scalars(
            select(MovieFavoriteModel).where(
                MovieFavoriteModel.user_id == user_id,
                MovieFavoriteModel.movie_id.in_(movie_ids),
            ).options(joinedload(MovieFavoriteModel.movie))
        )
        by_movie = {favorite.movie_id: favorite for favorite in favorites}

        return [by_movie[movie_id] for movie_id in movie_ids
                if movie_id in by_movie]

    async def add(self, favorite: MovieFavoriteModel) -> None:
        self.db.add(favorite)
        await self.db.flush()

    async def delete(self, user_id: int, movie_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(MovieFavoriteModel).where(
                MovieFavoriteModel.user_id == user_id,
                MovieFavoriteModel.movie_id == movie_id,
            ).returning(MovieFavoriteModel.id)
        )
        return deleted_id is not None

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

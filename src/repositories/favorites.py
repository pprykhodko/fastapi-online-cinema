from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.database.models import MovieFavoriteModel, MovieModel
from src.repositories.movies import MovieRepository
from src.schemas.interactions import MovieFavoriteListQuerySchema


class FavoriteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_favorites(
        self, user_id: int, query: MovieFavoriteListQuerySchema,
    ) -> tuple[list[MovieFavoriteModel], int]:
        movies, total = await MovieRepository(self.db).list_movies(
            query, favorite_user_id=user_id,
        )

        if not movies:
            return [], total

        favorites = await self.db.scalars(
            select(MovieFavoriteModel).where(
                MovieFavoriteModel.user_id == user_id,
                MovieFavoriteModel.movie_id.in_(
                    [movie.id for movie in movies],
                ),
            ).options(joinedload(MovieFavoriteModel.movie))
        )
        by_movie = {favorite.movie_id: favorite for favorite in favorites}

        return [by_movie[movie.id] for movie in movies
                if movie.id in by_movie], total

    async def get_movie(self, movie_id: int) -> MovieModel | None:
        return await MovieRepository(self.db).get_movie(
            movie_id, for_update=True
        )

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
        await self.db.commit()

        return deleted_id is not None

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

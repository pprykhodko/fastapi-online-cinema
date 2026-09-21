from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import GenreModel, MovieModel
from src.database.models.movies import MoviesGenresModel


class GenreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_genres(self):
        movie_count = (
            select(func.count())
            .select_from(MoviesGenresModel)
            .join(MovieModel, MovieModel.id == MoviesGenresModel.c.movie_id)
            .where(
                MoviesGenresModel.c.genre_id == GenreModel.id,
                MovieModel.is_deleted.is_(False),
            )
            .correlate(GenreModel)
            .scalar_subquery()
        )
        result = await self.db.execute(
            select(GenreModel, movie_count).order_by(GenreModel.id)
        )

        return result.all()

    async def get_genre(self, genre_id: int) -> GenreModel | None:
        return await self.db.get(GenreModel, genre_id)

    async def save(self, genre: GenreModel) -> None:
        self.db.add(genre)
        await self.db.commit()

    async def delete(self, genre_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(GenreModel).where(GenreModel.id == genre_id)
            .returning(GenreModel.id)
        )
        await self.db.commit()

        return deleted_id is not None

    async def rollback(self) -> None:
        await self.db.rollback()

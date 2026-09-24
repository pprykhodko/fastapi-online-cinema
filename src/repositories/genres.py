from sqlalchemy import func, select

from src.repositories.base import NamedEntityRepository
from src.database.models import GenreModel, MovieModel
from src.database.models.movies import MoviesGenresModel


class GenreRepository(NamedEntityRepository[GenreModel]):
    model = GenreModel

    async def list_genres(self):
        movie_count = (
            select(func.count())
            .select_from(MoviesGenresModel)
            .join(MovieModel, MovieModel.id == MoviesGenresModel.c.movie_id)
            .where(MoviesGenresModel.c.genre_id == GenreModel.id, MovieModel.is_deleted.is_(False))
            .correlate(GenreModel)
            .scalar_subquery()
        )
        result = await self.db.execute(select(GenreModel, movie_count).order_by(GenreModel.id))

        return result.all()

    async def get_genre(self, genre_id: int) -> GenreModel | None:
        return await self.get_by_id(genre_id)

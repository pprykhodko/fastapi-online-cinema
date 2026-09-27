from sqlalchemy import func, select

from src.repositories.base import NamedEntityRepository
from src.database.models import GenreModel, MovieModel
from src.database.models.movies import MoviesGenresModel


class GenreRepository(NamedEntityRepository[GenreModel]):
    model = GenreModel

    async def list_genres(self):
        """
        List genres with the count of non-deleted movies in each.

        The caller controls the transaction commit.

        Returns:
            Sequence: Genre records paired with their non-deleted movie counts.
        """
        movie_count = (
            select(func.count())
            .select_from(MoviesGenresModel)
            .join(MovieModel, MovieModel.id == MoviesGenresModel.c.movie_id)
            .where(
                MoviesGenresModel.c.genre_id == GenreModel.id,
                MovieModel.is_deleted.is_(False)
            )
            .correlate(GenreModel)
            .scalar_subquery()
        )
        result = await self.db.execute(
            select(GenreModel, movie_count)
            .order_by(GenreModel.id)
        )

        return result.all()

    async def get_genre(self, genre_id: int) -> GenreModel | None:
        """
        Look up the genre by its ID.

        The caller controls the transaction commit.

        Args:
            genre_id (int): ID of the genre.

        Returns:
            GenreModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        return await self.get_by_id(genre_id)

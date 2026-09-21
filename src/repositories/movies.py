from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import (
    DirectorModel, GenreModel, MovieModel, StarModel,
)
from src.schemas.movies import MovieListQuerySchema


class MovieRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_movies(
        self, query: MovieListQuerySchema,
    ) -> tuple[list[MovieModel], int]:
        stmt = select(MovieModel).where(MovieModel.is_deleted.is_(False))

        if query.year is not None:
            stmt = stmt.where(MovieModel.year == query.year)

        if query.min_imdb is not None:
            stmt = stmt.where(MovieModel.imdb >= query.min_imdb)

        if query.genre_id is not None:
            stmt = stmt.where(MovieModel.genres.any(
                GenreModel.id == query.genre_id,
            ))

        if query.search is not None:
            stmt = stmt.where(or_(
                MovieModel.name.icontains(query.search, autoescape=True),
                MovieModel.description.icontains(
                    query.search, autoescape=True,
                ),
                MovieModel.stars.any(
                    StarModel.name.icontains(query.search, autoescape=True),
                ),
                MovieModel.directors.any(
                    DirectorModel.name.icontains(
                        query.search, autoescape=True,
                    ),
                ),
            ))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(count_stmt)
        sort_column = {
            "price": MovieModel.price,
            "year": MovieModel.year,
            "popularity": MovieModel.votes,
        }[query.sort_by]
        order = (
            sort_column.asc() if query.sort_order == "asc"
            else sort_column.desc()
        )
        stmt = (
            stmt.options(selectinload(MovieModel.genres))
            .order_by(order.nulls_last(), MovieModel.id.asc())
            .offset((query.page - 1) * query.per_page)
            .limit(query.per_page)
        )

        movies = await self.db.scalars(stmt)
        return list(movies.all()), total or 0

    async def rollback(self) -> None:
        await self.db.rollback()

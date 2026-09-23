from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import (
    CartItemModel, CertificationModel, DirectorModel, GenreModel, MovieModel,
    OrderItemModel, OrderModel, OrderStatusEnum, PaymentModel,
    PaymentStatusEnum, StarModel, MovieFavoriteModel,
)
from src.schemas.movies import MovieListQuerySchema


class MovieRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_movies(
            self, query: MovieListQuerySchema, favorite_user_id: int | None = None,
    ) -> tuple[list[MovieModel], int]:
        stmt = select(MovieModel).where(MovieModel.is_deleted.is_(False))

        if favorite_user_id is not None:
            stmt = stmt.where(MovieModel.favorites.any(
                MovieFavoriteModel.user_id == favorite_user_id
                )
            )

        if query.year is not None:
            stmt = stmt.where(MovieModel.year == query.year)

        if query.min_imdb is not None:
            stmt = stmt.where(MovieModel.imdb >= query.min_imdb)

        if query.genre_id is not None:
            stmt = stmt.where(MovieModel.genres.any(
                GenreModel.id == query.genre_id
                )
            )

        if query.search is not None:
            stmt = stmt.where(or_(
                MovieModel.name.icontains(query.search, autoescape=True),
                MovieModel.description.icontains(
                    query.search, autoescape=True
                ),
                MovieModel.stars.any(
                    StarModel.name.icontains(query.search, autoescape=True)
                ),
                MovieModel.directors.any(
                    DirectorModel.name.icontains(
                        query.search, autoescape=True
                    )
                )
            )
            )

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

    async def get_movie(
            self, movie_id: int, for_update: bool = False,
    ) -> MovieModel | None:
        stmt = select(MovieModel).where(
            MovieModel.id == movie_id, MovieModel.is_deleted.is_(False),
            ).options(
            selectinload(MovieModel.genres), selectinload(MovieModel.stars),
            selectinload(MovieModel.directors),
            selectinload(MovieModel.certification),
        )

        if for_update:
            stmt = stmt.with_for_update()

        return await self.db.scalar(stmt)

    async def get_relations(self, data):
        certification = await self.db.get(
            CertificationModel, data.certification_id,
        )
        genres = list((await self.db.scalars(
            select(GenreModel).where(GenreModel.id.in_(data.genre_ids))
        )).all())
        stars = list((await self.db.scalars(
            select(StarModel).where(StarModel.id.in_(data.star_ids))
        )).all())
        directors = list((await self.db.scalars(
            select(DirectorModel)
            .where(DirectorModel.id.in_(data.director_ids))
        )).all())

        return certification, genres, stars, directors

    async def has_purchases(self, movie_id: int) -> bool:
        stmt = select(OrderItemModel.id).join(OrderModel).where(
            OrderItemModel.movie_id == movie_id,
            or_(
                OrderModel.status == OrderStatusEnum.PAID,
                OrderModel.payments.any(PaymentModel.status.in_([
                    PaymentStatusEnum.SUCCESSFUL, PaymentStatusEnum.REFUNDED,
                ])),
                ),
            ).limit(1)

        return await self.db.scalar(stmt) is not None

    async def cart_count(self, movie_id: int) -> int:
        return await self.db.scalar(
            select(func.count()).select_from(CartItemModel)
            .where(CartItemModel.movie_id == movie_id)
        ) or 0

    async def remove_from_carts(self, movie_id: int) -> None:
        await self.db.execute(
            delete(CartItemModel).where(CartItemModel.movie_id == movie_id)
        )

    async def flush_movie(self, movie: MovieModel) -> None:
        self.db.add(movie)
        await self.db.flush()

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

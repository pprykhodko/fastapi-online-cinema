from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from src.repositories.base import BaseRepository
from src.database.models import (
    CartItemModel,
    CertificationModel,
    DirectorModel,
    GenreModel,
    MovieModel,
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
    PaymentModel,
    PaymentStatusEnum,
    StarModel,
    MovieFavoriteModel,
    MovieReactionModel,
    MovieRatingModel
)
from src.schemas.movies import MovieListQuerySchema


class MovieRepository(BaseRepository):
    async def list_movies(
            self,
            query: MovieListQuerySchema,
            favorite_user_id: int | None = None
    ) -> tuple[list[MovieModel], int]:
        """
        Return visible movies using pagination, search, filters and sorting.

        The caller controls the transaction commit.

        Args:
            query (MovieListQuerySchema): Validated pagination and any supported search,
                sort or filter options.
            favorite_user_id (int | None): Restrict results to this user favorites; None
                disables this filter.

        Returns:
            tuple[list[MovieModel], int]: Records on this page and the total count
                before pagination.
        """
        stmt = select(MovieModel).where(MovieModel.is_deleted.is_(False))

        if favorite_user_id is not None:
            stmt = stmt.where(
                MovieModel.favorites.any(
                    MovieFavoriteModel.user_id == favorite_user_id
                )
            )

        if query.year is not None:
            stmt = stmt.where(MovieModel.year == query.year)

        if query.min_imdb is not None:
            stmt = stmt.where(MovieModel.imdb >= query.min_imdb)

        if query.genre_id is not None:
            stmt = stmt.where(MovieModel.genres.any(GenreModel.id == query.genre_id))

        if query.search is not None:
            stmt = (
                stmt.where(
                    or_(
                        MovieModel.name.icontains(query.search, autoescape=True),
                        MovieModel.description.icontains(query.search, autoescape=True),
                        MovieModel.stars.any(
                            StarModel.name.icontains(query.search, autoescape=True)
                        ),
                        MovieModel.directors.any(
                            DirectorModel.name.icontains(query.search, autoescape=True))
                    )
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(count_stmt)
        sort_column = {
            "price": MovieModel.price,
            "year": MovieModel.year,
            "popularity": MovieModel.votes
        }[query.sort_by]
        order = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        stmt = (
            stmt.options(selectinload(MovieModel.genres))
            .order_by(order.nulls_last(), MovieModel.id.asc())
            .offset((query.page - 1) * query.per_page)
            .limit(query.per_page)
        )

        movies = await self.db.scalars(stmt)

        return list(movies.all()), total or 0

    async def average_ratings(self, movie_ids: list[int]) -> dict[int, float]:
        """
        Calculate the mean user rating for each requested movie with ratings.

        The caller controls the transaction commit.

        Args:
            movie_ids (list[int]): Movie IDs to include in the operation.

        Returns:
            dict[int, float]: Movie IDs mapped to their mean user score; unrated movies
                are omitted.
        """
        if not movie_ids:
            return {}

        rows = await self.db.execute(
            select(MovieRatingModel.movie_id, func.avg(MovieRatingModel.score))
            .where(MovieRatingModel.movie_id.in_(movie_ids))
            .group_by(MovieRatingModel.movie_id)
        )

        return {movie_id: float(average) for movie_id, average in rows}

    async def reaction_counts(self, movie_ids: list[int]) -> dict[int, dict[str, int]]:
        """
        Count likes and dislikes for the requested movies.

        The caller controls the transaction commit.

        Args:
            movie_ids (list[int]): Movie IDs to include in the operation.

        Returns:
            dict: Movie IDs mapped to likes_count and dislikes_count; movies without
                reactions are omitted.
        """
        if not movie_ids:
            return {}

        rows = await self.db.execute(
            select(
                MovieReactionModel.movie_id,
                MovieReactionModel.reaction,
                func.count()
            )
            .where(MovieReactionModel.movie_id.in_(movie_ids))
            .group_by(MovieReactionModel.movie_id, MovieReactionModel.reaction)
        )
        counts: dict[int, dict[str, int]] = {}

        for movie_id, reaction, count in rows:
            counts.setdefault(movie_id, {"likes_count": 0, "dislikes_count": 0})
            key = "likes_count" if reaction == "like" else "dislikes_count"
            counts[movie_id][key] = count

        return counts

    async def get_movie(
            self,
            movie_id: int,
            for_update: bool = False,
            with_relations: bool = True
    ) -> MovieModel | None:
        """
        Return the selected non-deleted movie with its related catalog data.

        The caller controls the transaction commit.

        Args:
            movie_id (int): ID of the movie, not the cart or order item.
            for_update (bool): Request a row lock for this transaction when supported by
                the database.
            with_relations (bool): Eagerly load catalog relationships when True.

        Returns:
            MovieModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.id == movie_id,
                MovieModel.is_deleted.is_(False)
            )
        )

        if with_relations:
            stmt = stmt.options(
                selectinload(MovieModel.genres),
                selectinload(MovieModel.stars),
                selectinload(MovieModel.directors),
                selectinload(MovieModel.certification),
            )

        if for_update:
            stmt = stmt.with_for_update()

        return await self.db.scalar(stmt)

    async def get_relations(self, data):
        """
        Load the certification, genres, actors and directors referenced by movie input.

        The caller controls the transaction commit.

        Args:
            data: Validated request fields, including IDs or values used by this
                operation.

        Returns:
            tuple: Certification or None, followed by genre, actor and director lists.
        """
        certification = await self.db.get(CertificationModel, data.certification_id)
        genres = list(
            (
                await self.db.scalars(
                    select(GenreModel)
                    .where(GenreModel.id.in_(data.genre_ids))
                )
            ).all()
        )
        stars = list(
            (
                await self.db.scalars(
                    select(StarModel)
                    .where(StarModel.id.in_(data.star_ids))
                )
            ).all()
        )
        directors = list((await self.db.scalars(
            select(DirectorModel)
            .where(DirectorModel.id.in_(data.director_ids)))).all())

        return certification, genres, stars, directors

    async def has_purchases(self, movie_id: int) -> bool:
        """
        Check for paid orders or successful/refunded payments that prevent movie
        deletion.

        The caller controls the transaction commit.

        Args:
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            bool: Whether existing financial records prevent deleting the movie.
        """
        stmt = (select(OrderItemModel.id)
                .join(OrderModel)
                .where(
            OrderItemModel.movie_id == movie_id,
            or_(OrderModel.status == OrderStatusEnum.PAID,
                OrderModel.payments
                .any(PaymentModel.status.in_(
                    [PaymentStatusEnum.SUCCESSFUL, PaymentStatusEnum.REFUNDED]
                )
                )
                )
        ).limit(1)
                )

        return await self.db.scalar(stmt) is not None

    async def get_checkout_movies(self, movie_ids: list[int]) -> list[MovieModel]:
        """
        Load and lock checkout movies in ID order, including soft-deleted rows.

        The caller controls the transaction commit.

        Args:
            movie_ids (list[int]): Movie IDs to include in the operation.

        Returns:
            list[MovieModel]: Requested database record(s).
        """
        stmt = (
            select(MovieModel)
            .where(MovieModel.id.in_(movie_ids))
            .order_by(MovieModel.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        return list((await self.db.scalars(stmt)).all())

    async def cart_count(self, movie_id: int) -> int:
        """
        Count cart entries containing the selected movie.

        The caller controls the transaction commit.

        Args:
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            int: Number of cart entries containing this movie.
        """
        return await self.db.scalar(
            select(func.count())
            .select_from(CartItemModel)
            .where(CartItemModel.movie_id == movie_id)
        ) or 0

    async def remove_from_carts(self, movie_id: int) -> None:
        """
        Remove the movie from all carts without committing.

        Args:
            movie_id (int): ID of the movie, not the cart or order item.
        """
        await self.db.execute(
            delete(CartItemModel)
            .where(CartItemModel.movie_id == movie_id)
        )

    async def flush_movie(self, movie: MovieModel) -> None:
        """
        Add and flush a movie without committing the transaction.

        Args:
            movie (MovieModel): ORM record supplied for this database operation.
        """
        self.db.add(movie)
        await self.db.flush()

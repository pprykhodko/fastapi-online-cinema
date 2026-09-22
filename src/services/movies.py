from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.repositories.movies import MovieRepository
from src.database.models import MovieModel
from src.schemas.movies import (
    MovieListItemResponseSchema, MovieListQuerySchema, MovieListResponseSchema,
    MovieCreateRequestSchema, MovieDetailResponseSchema,
)


class MovieService:
    def __init__(self, repository: MovieRepository):
        self.repository = repository

    async def get_movie(self, movie_id: int) -> MovieDetailResponseSchema:
        try:
            movie = await self.repository.get_movie(movie_id)
        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The movie is temporarily unavailable.",
            ) from error
        if movie is None:
            raise HTTPException(404, "Movie not found.")
        return MovieDetailResponseSchema.model_validate(movie)

    async def save_movie(
        self, data: MovieCreateRequestSchema, movie_id: int | None = None,
    ) -> MovieDetailResponseSchema:
        try:
            if movie_id is None:
                movie = MovieModel()
            else:
                existing = await self.repository.get_movie(
                    movie_id, for_update=True,
                )
                if existing is None:
                    raise HTTPException(404, "Movie not found.")
                movie = existing

            certification, genres, stars, directors = (
                await self.repository.get_relations(data)
            )
            if certification is None:
                raise HTTPException(422, "Certification does not exist.")
            for field, ids, records in (
                ("genre_ids", data.genre_ids, genres),
                ("star_ids", data.star_ids, stars),
                ("director_ids", data.director_ids, directors),
            ):
                if len(ids) != len(records):
                    raise HTTPException(422, f"Unknown IDs in {field}.")

            values = data.model_dump(exclude={
                "certification_id", "genre_ids", "star_ids", "director_ids",
            })
            for field, value in values.items():
                setattr(movie, field, value)
            movie.certification = certification
            movie.genres = genres
            movie.stars = stars
            movie.directors = directors
            await self.repository.flush_movie(movie)
            response = MovieDetailResponseSchema.model_validate(movie)
            await self.repository.commit()
            return response
        except HTTPException:
            await self.repository.rollback()
            raise
        except IntegrityError as error:
            await self.repository.rollback()
            raise HTTPException(
                409, "Movie conflicts with existing data. Check name, year, "
                "duration and referenced records.",
            ) from error
        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The movie could not be saved.",
            ) from error

    async def delete_movie(self, movie_id: int, confirm: bool) -> None:
        try:
            movie = await self.repository.get_movie(movie_id, for_update=True)
            if movie is None:
                raise HTTPException(404, "Movie not found.")
            if await self.repository.has_purchases(movie_id):
                raise HTTPException(
                    409, "A purchased movie cannot be deleted.",
                )
            count = await self.repository.cart_count(movie_id)
            if count and not confirm:
                raise HTTPException(
                    409, f"Movie exists in {count} cart(s). Repeat with "
                    "confirm=true to remove it from carts and the catalog.",
                )
            await self.repository.remove_from_carts(movie_id)
            movie.is_deleted = True
            await self.repository.commit()
        except HTTPException:
            await self.repository.rollback()
            raise
        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                503, "The movie could not be deleted.",
            ) from error

    async def list_movies(
        self, query: MovieListQuerySchema,
    ) -> MovieListResponseSchema:
        try:
            movies, total = await self.repository.list_movies(query)

        except SQLAlchemyError as error:
            await self.repository.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The movie catalog is temporarily unavailable.",
            ) from error

        return MovieListResponseSchema(
            items=[MovieListItemResponseSchema.model_validate(movie)
                   for movie in movies],
            total=total, page=query.page, per_page=query.per_page,
        )

from fastapi import HTTPException, status

from src.services.database_errors import database_errors
from src.repositories.movies import MovieRepository
from src.services.movie_checks import get_movie_or_404
from src.database.models import MovieModel
from src.schemas.movies import (
    MovieListQuerySchema, MovieListResponseSchema,
    MovieCreateRequestSchema, MovieDetailResponseSchema,
    MovieCatalogItemResponseSchema,
)


class MovieService:
    def __init__(self, repository: MovieRepository):
        self.repository = repository

    async def get_movie(self, movie_id: int) -> MovieDetailResponseSchema:
        async with database_errors(self.repository, detail="The movie is temporarily unavailable"):
            movie = await get_movie_or_404(self.repository, movie_id, with_relations=True)

        return MovieDetailResponseSchema.model_validate(movie)

    async def save_movie(
            self,
            data: MovieCreateRequestSchema,
            movie_id: int | None = None
    ) -> MovieDetailResponseSchema:
        async with database_errors(
                self.repository,
                detail="The movie could not be saved",
                conflict_detail="Movie conflicts with existing data. Check name, year, duration and referenced records."
        ):
            if movie_id is None:
                movie = MovieModel()

            else:
                movie = await get_movie_or_404(self.repository, movie_id, lock=True, with_relations=True)

            certification, genres, stars, directors = await self.repository.get_relations(data)

            if certification is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Certification does not exist"
                )

            for field, ids, records in (
                    ("genre_ids", data.genre_ids, genres),
                    ("star_ids", data.star_ids, stars),
                    ("director_ids", data.director_ids, directors),
            ):
                if len(ids) != len(records):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Unknown IDs in {field}"
                    )

            values = data.model_dump(exclude={"certification_id", "genre_ids", "star_ids", "director_ids"})

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

    async def delete_movie(self, movie_id: int, confirm: bool) -> None:
        async with database_errors(self.repository, detail="The movie could not be deleted"):
            movie = await get_movie_or_404(self.repository, movie_id, lock=True, with_relations=True)

            if await self.repository.has_purchases(movie_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A purchased movie cannot be deleted"
                )

            count = await self.repository.cart_count(movie_id)

            if count and not confirm:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Movie exists in {count} cart(s). Repeat with confirm=true to remove it from carts and the catalog."
                )

            await self.repository.remove_from_carts(movie_id)
            movie.is_deleted = True
            await self.repository.commit()

    async def list_movies(self, query: MovieListQuerySchema) -> MovieListResponseSchema:
        async with database_errors(self.repository, detail="The movie catalog is temporarily unavailable"):
            movies, total = await self.repository.list_movies(query)
            counts = await self.repository.reaction_counts([movie.id for movie in movies])
            averages = await self.repository.average_ratings([movie.id for movie in movies])

        items = []

        for movie in movies:
            item = MovieCatalogItemResponseSchema.model_validate(movie)
            movie_counts = counts.get(movie.id, {})
            item.likes_count = movie_counts.get("likes_count", 0)
            item.dislikes_count = movie_counts.get("dislikes_count", 0)
            item.average_rating = averages.get(movie.id)
            items.append(item)

        return MovieListResponseSchema(items=items, total=total, page=query.page, per_page=query.per_page)

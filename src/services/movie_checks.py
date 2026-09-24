from fastapi import HTTPException, status

from src.database.models import MovieModel
from src.repositories.movies import MovieRepository


async def get_movie_or_404(
        repository: MovieRepository,
        movie_id: int,
        lock: bool = False,
        with_relations: bool = False
) -> MovieModel:
    movie = await repository.get_movie(movie_id, for_update=lock, with_relations=with_relations)

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found"
        )

    return movie

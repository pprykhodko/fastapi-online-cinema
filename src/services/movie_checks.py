from fastapi import HTTPException, status

from src.database.models import MovieModel
from src.repositories.movies import MovieRepository


async def get_movie_or_404(
        repository: MovieRepository,
        movie_id: int,
        lock: bool = False,
        with_relations: bool = False
) -> MovieModel:
    """
    Load a non-deleted movie or raise a not-found error.

    Args:
        repository (MovieRepository): Repository used for database operations and the
            shared transaction.
        movie_id (int): ID of the movie, not the cart or order item.
        lock (bool): Request a row lock for this transaction when supported by the
            database.
        with_relations (bool): Eagerly load catalog relationships when True.

    Returns:
        MovieModel: Requested database record(s).

    Raises:
        HTTPException: The movie is missing or soft-deleted.
    """
    movie = await repository.get_movie(
        movie_id,
        for_update=lock,
        with_relations=with_relations
    )

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found"
        )

    return movie

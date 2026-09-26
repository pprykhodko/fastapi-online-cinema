import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import MovieFavoriteModel, MovieModel, UserModel


def test_favorites_persist_links_and_timestamp(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel]
) -> None:
    user, other_user = catalog_users
    movie, other_movie = catalog_movies
    favorite = MovieFavoriteModel(user=user, movie=movie)
    db_session.add_all(
        [
            favorite,
            MovieFavoriteModel(user=other_user, movie=movie),
            MovieFavoriteModel(user=user, movie=other_movie)
        ]
    )
    db_session.commit()

    assert favorite.added_at is not None
    assert favorite.user is user
    assert favorite.movie is movie
    assert favorite in user.favorite_movies
    assert favorite in movie.favorites
    assert len(user.favorite_movies) == 2
    assert len(movie.favorites) == 2


def test_favorites_reject_duplicate_and_allow_readding_after_removal(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel]
) -> None:
    user, _ = catalog_users
    movie, _ = catalog_movies
    favorite = MovieFavoriteModel(user=user, movie=movie)
    db_session.add(favorite)
    db_session.commit()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(
                MovieFavoriteModel(
                    user_id=user.id,
                    movie_id=movie.id
                )
            )
            db_session.flush()

    user.favorite_movies.remove(favorite)
    db_session.commit()
    assert db_session.scalars(select(MovieFavoriteModel)).all() == []
    assert db_session.get(MovieModel, movie.id) is movie

    db_session.add(MovieFavoriteModel(user=user, movie=movie))
    db_session.commit()
    assert len(user.favorite_movies) == 1

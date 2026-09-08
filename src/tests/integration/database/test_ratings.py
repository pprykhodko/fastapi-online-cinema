import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import MovieModel, MovieRatingModel, UserModel


def test_ratings_are_per_user_and_can_be_updated(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    user, other_user = catalog_users
    movie, _ = catalog_movies
    rating = MovieRatingModel(user=user, movie=movie, score=1)
    db_session.add_all([
        rating, MovieRatingModel(user=other_user, movie=movie, score=10),
    ])
    db_session.commit()
    rating_id = rating.id

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(MovieRatingModel(
                user_id=user.id, movie_id=movie.id, score=9,
            ))
            db_session.flush()

    rating.score = 8
    db_session.commit()
    assert rating.id == rating_id
    assert rating.score == 8
    assert rating.created_at is not None
    assert rating.updated_at is not None
    assert rating in user.movie_ratings
    assert rating in movie.ratings
    assert len(db_session.scalars(select(MovieRatingModel)).all()) == 2
    assert movie.imdb == 7.5
    assert movie.votes == 100


@pytest.mark.parametrize("score", [0, 11, None])
def test_rating_database_constraints_reject_invalid_scores(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
    score: int | None,
) -> None:
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(insert(MovieRatingModel).values(
                user_id=catalog_users[0].id,
                movie_id=catalog_movies[0].id,
                score=score,
            ))

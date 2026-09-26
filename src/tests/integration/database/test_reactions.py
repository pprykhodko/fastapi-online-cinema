import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import (
    MovieModel,
    MovieReactionEnum,
    MovieReactionModel,
    UserModel
)


def test_users_can_change_reactions_but_cannot_like_and_dislike_at_once(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel]
) -> None:
    user, other_user = catalog_users
    movie, _ = catalog_movies
    reaction = MovieReactionModel(user=user, movie=movie, reaction="like")
    db_session.add_all([
        reaction,
        MovieReactionModel(user=other_user, movie=movie, reaction="dislike")
    ])
    db_session.commit()
    reaction_id = reaction.id

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(MovieReactionModel(
                user_id=user.id, movie_id=movie.id, reaction="dislike"
            ))
            db_session.flush()

    reaction.reaction = MovieReactionEnum.DISLIKE
    db_session.commit()
    assert reaction.id == reaction_id
    assert reaction.reaction is MovieReactionEnum.DISLIKE
    assert reaction.created_at is not None
    assert reaction.updated_at is not None
    assert reaction in user.movie_reactions
    assert reaction in movie.reactions
    assert len(db_session.scalars(select(MovieReactionModel)).all()) == 2


@pytest.mark.parametrize("reaction", ["love", "LIKE", None])
def test_database_rejects_unknown_reactions_without_orm_validation(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel],
        reaction: str | None
) -> None:
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text(
                "INSERT INTO movie_reactions (user_id, movie_id, reaction) "
                "VALUES (:user_id, :movie_id, :reaction)"
            ), {
                "user_id": catalog_users[0].id,
                "movie_id": catalog_movies[0].id,
                "reaction": reaction
            })

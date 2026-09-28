import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import (
    Base,
    CommentLikeModel,
    MovieCommentModel,
    MovieFavoriteModel,
    MovieModel,
    MovieRatingModel,
    MovieReactionModel,
    UserModel
)


@pytest.mark.parametrize("target", ["user", "movie"])
@pytest.mark.parametrize("load_relationships", [True, False])
def test_deleting_user_or_movie_cleans_up_interactions(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel],
        target: str,
        load_relationships: bool
) -> None:
    user, other_user = catalog_users
    movie, _ = catalog_movies
    comment = MovieCommentModel(user=user, movie=movie, content="Original.")
    reply = MovieCommentModel(
        user=other_user, movie=movie, parent=comment, content="Reply."
    )
    db_session.add_all([
        MovieFavoriteModel(user=user, movie=movie),
        MovieRatingModel(user=user, movie=movie, score=8),
        MovieReactionModel(user=user, movie=movie, reaction="like"),
        comment, reply,
        CommentLikeModel(user=user, comment=comment),
        CommentLikeModel(user=other_user, comment=reply)
    ])
    db_session.commit()
    if load_relationships:
        assert len(user.favorite_movies) == len(movie.favorites) == 1
        assert len(user.movie_ratings) == len(movie.ratings) == 1
        assert len(user.movie_reactions) == len(movie.reactions) == 1
        assert len(movie.comments) == 2
        assert len(user.movie_comments) == len(user.comment_likes) == 1
    db_session.delete(user if target == "user" else movie)
    db_session.commit()
    for model in (
            MovieFavoriteModel, MovieRatingModel, MovieReactionModel,
            MovieCommentModel, CommentLikeModel
    ):
        assert db_session.scalars(select(model)).all() == []
    assert db_session.get(UserModel, other_user.id) is other_user


@pytest.mark.parametrize(
    ("model", "extra_values", "reference"),
    [
        (MovieFavoriteModel, {}, "movie_id"),
        (MovieFavoriteModel, {}, "user_id"),
        (MovieRatingModel, {"score": 5}, "movie_id"),
        (MovieRatingModel, {"score": 5}, "user_id"),
        (MovieReactionModel, {"reaction": "like"}, "movie_id"),
        (MovieReactionModel, {"reaction": "like"}, "user_id"),
        (MovieCommentModel, {"content": "Test."}, "movie_id"),
        (MovieCommentModel, {"content": "Test."}, "user_id"),
        (MovieCommentModel, {"content": "Test."}, "parent_id")
    ]
)
def test_interactions_reject_nonexistent_references(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel],
        model: type[Base],
        extra_values: dict[str, object],
        reference: str
) -> None:
    values = {
        "user_id": catalog_users[0].id,
        "movie_id": catalog_movies[0].id,
        **extra_values,
        reference: -1
    }
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(insert(model).values(**values))


@pytest.mark.parametrize("reference", ["user_id", "comment_id"])
def test_comment_likes_reject_nonexistent_references(
        db_session: Session,
        catalog_users: tuple[UserModel, UserModel],
        catalog_movies: tuple[MovieModel, MovieModel],
        reference: str
) -> None:
    comment = MovieCommentModel(
        user=catalog_users[0], movie=catalog_movies[0], content="Test."
    )
    db_session.add(comment)
    db_session.commit()
    values = {"user_id": catalog_users[0].id, "comment_id": comment.id}
    values[reference] = -1
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(insert(CommentLikeModel).values(**values))

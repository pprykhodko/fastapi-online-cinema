import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import (
    CommentLikeModel,
    MovieCommentModel,
    MovieModel,
    UserModel,
)


def test_comments_support_multiple_posts_replies_and_likes(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    user, other_user = catalog_users
    movie, _ = catalog_movies
    comment = MovieCommentModel(user=user, movie=movie, content="  Great!  ")
    reply = MovieCommentModel(
        user=other_user, movie=movie, parent=comment, content="I agree.",
    )
    nested_reply = MovieCommentModel(
        user=user, movie=movie, parent=reply, content="Thanks!",
    )
    another_comment = MovieCommentModel(
        user=user, movie=movie, content="The soundtrack is great too.",
    )
    likes = [
        CommentLikeModel(user=user, comment=comment),
        CommentLikeModel(user=other_user, comment=comment),
    ]
    db_session.add_all([comment, reply, nested_reply, another_comment, *likes])
    db_session.commit()

    assert comment.content == "Great!"
    assert comment.parent is None
    assert comment.created_at is not None
    assert comment.updated_at is not None
    assert comment.replies == [reply]
    assert reply.parent is comment
    assert nested_reply.parent is reply
    assert len(movie.comments) == 4
    assert len(user.movie_comments) == 3
    assert len(comment.likes) == 2
    assert likes[0].created_at is not None
    assert likes[0] in user.comment_likes

    comment.content = "  Updated comment. "
    db_session.commit()
    assert comment.content == "Updated comment."
    assert comment.updated_at >= comment.created_at


def test_comment_likes_cannot_be_duplicated_and_can_be_removed(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    user, other_user = catalog_users
    comment = MovieCommentModel(
        user=user, movie=catalog_movies[0], content="Great film!",
    )
    like = CommentLikeModel(user=other_user, comment=comment)
    db_session.add(like)
    db_session.commit()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(CommentLikeModel(
                user_id=other_user.id, comment_id=comment.id,
            ))
            db_session.flush()

    comment.likes.remove(like)
    db_session.commit()
    assert db_session.scalars(select(CommentLikeModel)).all() == []
    assert db_session.get(MovieCommentModel, comment.id) is comment
    db_session.add(CommentLikeModel(user=other_user, comment=comment))
    db_session.commit()
    assert len(comment.likes) == 1


@pytest.mark.parametrize("assign_parent_object", [True, False])
def test_reply_must_belong_to_parent_movie(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
    assign_parent_object: bool,
) -> None:
    user, other_user = catalog_users
    movie, other_movie = catalog_movies
    parent = MovieCommentModel(user=user, movie=movie, content="Original.")
    db_session.add(parent)
    db_session.commit()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            reply = MovieCommentModel(
                user_id=other_user.id,
                movie_id=other_movie.id,
                content="Wrong movie.",
            )
            if assign_parent_object:
                reply.parent = parent
            else:
                reply.parent_id = parent.id
            db_session.add(reply)
            db_session.flush()
    assert len(db_session.scalars(select(MovieCommentModel)).all()) == 1


def test_detaching_reply_keeps_its_movie(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    movie = catalog_movies[0]
    parent = MovieCommentModel(
        user=catalog_users[0], movie=movie, content="Original.",
    )
    reply = MovieCommentModel(
        user=catalog_users[1], movie=movie, parent=parent, content="Reply.",
    )
    db_session.add(reply)
    db_session.commit()
    reply.parent = None
    db_session.commit()
    assert reply.parent_id is None
    assert reply.movie_id == movie.id
    assert reply.movie is movie


def test_comment_cannot_be_its_own_parent(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(insert(MovieCommentModel).values(
                id=500,
                parent_id=500,
                user_id=catalog_users[0].id,
                movie_id=catalog_movies[0].id,
                content="Invalid self-reference.",
            ))


@pytest.mark.parametrize("content", ["", "   ", None])
def test_database_rejects_empty_comments_without_orm_validation(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
    content: str | None,
) -> None:
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(insert(MovieCommentModel).values(
                user_id=catalog_users[0].id,
                movie_id=catalog_movies[0].id,
                content=content,
            ))


@pytest.mark.parametrize("load_relationships", [True, False])
def test_deleting_comment_cascades_to_thread_and_likes(
    db_session: Session,
    catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
    load_relationships: bool,
) -> None:
    user, other_user = catalog_users
    movie = catalog_movies[0]
    parent = MovieCommentModel(user=user, movie=movie, content="Original.")
    child = MovieCommentModel(
        user=other_user, movie=movie, parent=parent, content="Reply.",
    )
    grandchild = MovieCommentModel(
        user=user, movie=movie, parent=child, content="Nested reply.",
    )
    unrelated = MovieCommentModel(
        user=other_user, movie=movie, content="Independent thread.",
    )
    db_session.add_all([
        parent, child, grandchild, unrelated,
        CommentLikeModel(user=other_user, comment=parent),
        CommentLikeModel(user=user, comment=child),
        CommentLikeModel(user=other_user, comment=grandchild),
    ])
    db_session.commit()
    if load_relationships:
        assert parent.replies == [child]
        assert child.replies == [grandchild]
        assert len(parent.likes) == 1
        assert len(child.likes) == 1
    db_session.delete(parent)
    db_session.commit()
    assert db_session.scalars(select(MovieCommentModel)).all() == [unrelated]
    assert db_session.scalars(select(CommentLikeModel)).all() == []
    assert db_session.get(MovieModel, movie.id) is movie
    assert db_session.get(UserModel, other_user.id) is other_user

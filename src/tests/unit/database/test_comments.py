from typing import Any

import pytest

from src.database import CommentLikeModel, MovieCommentModel
from src.database.validators import validate_comment_content


@pytest.mark.parametrize(
    ("content", "expected"),
    [("  Great film! \n", "Great film!"), ("Перша\nдруга", "Перша\nдруга")],
)
def test_comment_normalizes_surrounding_whitespace(
    content: str, expected: str,
) -> None:
    assert validate_comment_content(content) == expected
    comment = MovieCommentModel(user_id=1, movie_id=2, content=content)
    assert comment.content == expected


@pytest.mark.parametrize("content", ["", "   ", "\t\r\n", "\u2003", None, 1])
def test_comment_rejects_empty_or_non_text_content(content: Any) -> None:
    with pytest.raises(ValueError, match="Comment must"):
        validate_comment_content(content)
    with pytest.raises(ValueError, match="Comment must"):
        MovieCommentModel(user_id=1, movie_id=2, content=content)


def test_comment_validation_also_applies_to_updates() -> None:
    comment = MovieCommentModel(user_id=1, movie_id=2, content="Great film!")
    with pytest.raises(ValueError):
        comment.content = "   "
    assert comment.content == "Great film!"


def test_comment_and_like_representations() -> None:
    comment = MovieCommentModel(
        id=1, user_id=2, movie_id=3, parent_id=4, content="I agree.",
    )
    like = CommentLikeModel(id=5, user_id=2, comment_id=1)
    assert repr(comment) == (
        "<MovieCommentModel(id=1, user_id=2, movie_id=3, parent_id=4)>"
    )
    assert repr(like) == "<CommentLikeModel(id=5, user_id=2, comment_id=1)>"

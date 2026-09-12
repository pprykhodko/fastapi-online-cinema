from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.database import MovieReactionEnum
from src.schemas.interactions import (
    MovieCommentCreateRequestSchema, MovieCommentListQuerySchema,
    MovieCommentListResponseSchema,
    MovieFavoriteCreateRequestSchema, MovieFavoriteListResponseSchema,
    MovieRatingRequestSchema, MovieReactionRequestSchema,
)


@pytest.mark.parametrize("score", [1, 5, 10])
def test_rating_request_accepts_integer_scores(score: int) -> None:
    assert MovieRatingRequestSchema(score=score).score == score


@pytest.mark.parametrize("score", [0, 11, 5.5, 5.0, True, "5", None])
def test_rating_request_rejects_invalid_scores(score: Any) -> None:
    with pytest.raises(ValidationError):
        MovieRatingRequestSchema.model_validate({"score": score})


@pytest.mark.parametrize("reaction", list(MovieReactionEnum))
def test_reaction_request_parses_allowed_enum_values(
    reaction: MovieReactionEnum,
) -> None:
    request = MovieReactionRequestSchema.model_validate({
        "reaction": reaction.value,
    })
    assert request.reaction is reaction


@pytest.mark.parametrize("reaction", ["love", "LIKE", "", None, 1])
def test_reaction_request_rejects_unknown_values(reaction: Any) -> None:
    with pytest.raises(ValidationError):
        MovieReactionRequestSchema.model_validate({"reaction": reaction})


def test_comments_support_posts_and_replies() -> None:
    comment = MovieCommentCreateRequestSchema(content="  Great movie!  ")
    reply = MovieCommentCreateRequestSchema(content="I agree.", parent_id=1)
    assert comment.content == "Great movie!"
    assert comment.parent_id is None
    assert reply.parent_id == 1


@pytest.mark.parametrize("content", ["", " \n\t ", None, 123])
def test_comment_request_rejects_empty_or_non_text_content(
    content: Any,
) -> None:
    with pytest.raises(ValidationError):
        MovieCommentCreateRequestSchema.model_validate({"content": content})


@pytest.mark.parametrize("parent_id", [0, -1, True, 1.5, "1"])
def test_comment_request_rejects_invalid_parent_ids(parent_id: Any) -> None:
    with pytest.raises(ValidationError):
        MovieCommentCreateRequestSchema.model_validate({
            "content": "Reply", "parent_id": parent_id,
        })


def test_favorite_request_accepts_a_movie_id() -> None:
    assert MovieFavoriteCreateRequestSchema(movie_id=1).movie_id == 1


@pytest.mark.parametrize("movie_id", [0, -1, True, 1.5, "1", None])
def test_favorite_request_rejects_invalid_movie_ids(movie_id: Any) -> None:
    with pytest.raises(ValidationError):
        MovieFavoriteCreateRequestSchema.model_validate({"movie_id": movie_id})


@pytest.mark.parametrize(("schema", "data"), [
    (MovieRatingRequestSchema, {"score": 5}),
    (MovieReactionRequestSchema, {"reaction": "like"}),
    (MovieCommentCreateRequestSchema, {"content": "Great!"}),
    (MovieFavoriteCreateRequestSchema, {"movie_id": 1}),
])
def test_interaction_requests_reject_user_ids(
    schema: type[BaseModel], data: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({**data, "user_id": 999})


def test_comment_pagination_and_empty_lists() -> None:
    query = MovieCommentListQuerySchema.model_validate({"page": "2"})
    assert query.page == 2
    assert query.per_page == 10
    with pytest.raises(ValidationError):
        MovieCommentListQuerySchema(per_page=101)
    for schema in (
        MovieCommentListResponseSchema, MovieFavoriteListResponseSchema,
    ):
        response = schema(items=[], total=0, page=1, per_page=10)
        assert response.total == 0
        assert response.items == []

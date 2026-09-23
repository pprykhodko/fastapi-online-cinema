from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.database import (
    CertificationModel,
    CommentLikeModel,
    DirectorModel,
    GenreModel,
    MovieCommentModel,
    MovieFavoriteModel,
    MovieModel,
    MovieRatingModel,
    MovieReactionModel,
    StarModel,
    UserModel,
)
from src.schemas.interactions import (
    CommentLikeResponseSchema,
    MovieCommentCreateRequestSchema,
    MovieCommentListResponseSchema,
    MovieCommentResponseSchema,
    MovieFavoriteListResponseSchema,
    MovieFavoriteResponseSchema,
    MovieRatingRequestSchema,
    MovieRatingResponseSchema,
    MovieReactionRequestSchema,
    MovieReactionResponseSchema,
)
from src.schemas.movies import (
    MovieCreateRequestSchema,
    MovieDetailResponseSchema,
    MovieCatalogItemResponseSchema,
    MovieListResponseSchema,
)


def test_movie_schemas_support_creation_and_nested_orm_responses(
    db_session: Session,
) -> None:
    certification = CertificationModel(name="R")
    genre = GenreModel(name="Action")
    star = StarModel(name="Keanu Reeves")
    director = DirectorModel(name="Lana Wachowski")
    db_session.add_all([certification, genre, star, director])
    db_session.flush()
    request = MovieCreateRequestSchema.model_validate({
        "name": "  The Matrix  ", "year": 1999, "time": 136, "imdb": 8.7,
        "votes": 2_000_000, "description": "A science-fiction film.",
        "price": "9.99", "meta_score": 73, "gross": 467_200_000.0,
        "certification_id": certification.id, "genre_ids": [genre.id],
        "star_ids": [star.id], "director_ids": [director.id],
    })
    movie = MovieModel(**request.model_dump(exclude={
        "genre_ids", "star_ids", "director_ids",
    }))
    movie.genres = [genre]
    movie.stars = [star]
    movie.directors = [director]
    db_session.add(movie)
    db_session.commit()
    movie_id = movie.id
    db_session.expunge_all()
    stored_movie = db_session.scalars(
        select(MovieModel).where(MovieModel.id == movie_id).options(
            selectinload(MovieModel.genres),
            selectinload(MovieModel.stars),
            selectinload(MovieModel.directors),
            selectinload(MovieModel.certification),
        )
    ).one()
    db_session.expunge_all()

    detail = MovieDetailResponseSchema.model_validate(stored_movie)
    data = detail.model_dump(mode="json")
    assert data["name"] == "The Matrix"
    assert data["price"] == "9.99"
    assert data["uuid"] == str(stored_movie.uuid)
    assert data["certification"]["name"] == "R"
    assert data["genres"][0]["name"] == "Action"
    assert data["stars"][0]["name"] == "Keanu Reeves"
    assert data["directors"][0]["name"] == "Lana Wachowski"
    item = MovieCatalogItemResponseSchema.model_validate(stored_movie)
    page = MovieListResponseSchema(items=[item], total=1, page=1, per_page=10)
    assert page.items[0].id == movie_id
    assert "description" not in page.items[0].model_dump()


def test_favorite_schema_loads_movie_details_without_a_session(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    favorite = MovieFavoriteModel(
        user=catalog_users[0], movie=catalog_movies[0],
    )
    db_session.add(favorite)
    db_session.commit()
    favorite_id = favorite.id
    db_session.expunge_all()
    stored_favorite = db_session.scalars(
        select(MovieFavoriteModel)
        .where(MovieFavoriteModel.id == favorite_id)
        .options(selectinload(MovieFavoriteModel.movie)
                 .selectinload(MovieModel.genres))
    ).one()
    db_session.expunge_all()

    item = MovieFavoriteResponseSchema.model_validate(stored_favorite)
    page = MovieFavoriteListResponseSchema(
        items=[item], total=1, page=1, per_page=10,
    )
    assert page.items[0].movie.name == "First movie"
    assert page.items[0].movie.genres == []
    assert item.added_at is not None
    assert "user" not in item.model_dump()


def test_interaction_schemas_serialize_persisted_records(
    db_session: Session, catalog_users: tuple[UserModel, UserModel],
    catalog_movies: tuple[MovieModel, MovieModel],
) -> None:
    user_id = catalog_users[0].id
    movie_id = catalog_movies[0].id
    rating_request = MovieRatingRequestSchema(score=8)
    reaction_request = MovieReactionRequestSchema.model_validate({
        "reaction": "like",
    })
    comment_request = MovieCommentCreateRequestSchema(content="  Great!  ")
    rating = MovieRatingModel(
        user_id=user_id, movie_id=movie_id, **rating_request.model_dump(),
    )
    reaction = MovieReactionModel(
        user_id=user_id, movie_id=movie_id, **reaction_request.model_dump(),
    )
    comment = MovieCommentModel(
        user_id=user_id, movie_id=movie_id, **comment_request.model_dump(),
    )
    db_session.add_all([rating, reaction, comment])
    db_session.flush()
    reply_request = MovieCommentCreateRequestSchema(
        content="I agree.", parent_id=comment.id,
    )
    reply = MovieCommentModel(
        user_id=catalog_users[1].id, movie_id=movie_id,
        **reply_request.model_dump(),
    )
    like = CommentLikeModel(user_id=user_id, comment_id=comment.id)
    db_session.add_all([reply, like])
    db_session.commit()

    rating_data = MovieRatingResponseSchema.model_validate(rating)
    reaction_data = MovieReactionResponseSchema.model_validate(reaction)
    comment_data = MovieCommentResponseSchema.model_validate(comment)
    reply_data = MovieCommentResponseSchema.model_validate(reply)
    like_data = CommentLikeResponseSchema.model_validate(like)
    assert rating_data.score == 8
    assert rating_data.created_at is not None
    assert reaction_data.model_dump(mode="json")["reaction"] == "like"
    assert comment_data.content == "Great!"
    assert comment_data.parent_id is None
    assert reply_data.parent_id == comment_data.id
    assert like_data.comment_id == comment_data.id
    assert like_data.created_at is not None
    page = MovieCommentListResponseSchema(
        items=[comment_data, reply_data], total=2, page=1, per_page=10,
    )
    assert len(page.items) == 2
    assert "email" not in page.model_dump_json()

from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import (
    Float,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
)

from src.database import Base
from src.database.models.movies import (
    CertificationModel,
    DirectorModel,
    GenreModel,
    MovieModel,
    MoviesDirectorsModel,
    MoviesGenresModel,
    MoviesStarsModel,
    StarModel,
)
from src.database.validators.movies import (
    validate_duration,
    validate_imdb_rating,
    validate_meta_score,
    validate_name,
    validate_non_negative_decimal,
    validate_non_negative_float,
    validate_votes,
)


@pytest.mark.parametrize("name", ["", "   "])
def test_validate_name_rejects_empty_values(name: str) -> None:
    with pytest.raises(ValueError):
        validate_name(name)


def test_validate_name_strips_whitespace() -> None:
    assert validate_name("  The Matrix  ") == "The Matrix"


@pytest.mark.parametrize("duration", [0, -1])
def test_validate_duration_rejects_non_positive_values(
    duration: int,
) -> None:
    with pytest.raises(ValueError):
        validate_duration(duration)


@pytest.mark.parametrize("rating", [-0.1, 10.1])
def test_validate_imdb_rating_rejects_out_of_range_values(
    rating: float,
) -> None:
    with pytest.raises(ValueError):
        validate_imdb_rating(rating)


def test_validate_votes_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        validate_votes(-1)


@pytest.mark.parametrize("score", [-0.1, 100.1])
def test_validate_meta_score_rejects_out_of_range_values(
    score: float,
) -> None:
    with pytest.raises(ValueError):
        validate_meta_score(score)


def test_validate_non_negative_decimal_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        validate_non_negative_decimal(Decimal("-0.01"), "price")


def test_validate_non_negative_float_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        validate_non_negative_float(-0.01, "gross")


def test_named_models_normalize_names() -> None:
    names = [
        GenreModel(name="  Action ").name,
        StarModel(name="  Keanu Reeves ").name,
        DirectorModel(name="  Lana Wachowski ").name,
        CertificationModel(name="  R ").name,
    ]

    assert names == [
        "Action",
        "Keanu Reeves",
        "Lana Wachowski",
        "R",
    ]


def test_movie_model_validates_and_normalizes_values() -> None:
    movie = MovieModel(
        name="  The Matrix  ",
        year=1999,
        time=136,
        imdb=8.7,
        votes=2_000_000,
        meta_score=73,
        gross=467_200_000.0,
        description="A hacker discovers the nature of reality.",
        price=Decimal("9.99"),
        certification_id=1,
    )

    assert movie.name == "The Matrix"
    assert movie.year == 1999
    assert movie.price == Decimal("9.99")


def test_movie_columns_match_assignment_schema() -> None:
    movie_table = cast(Table, MovieModel.__table__)
    genre_table = cast(Table, GenreModel.__table__)
    star_table = cast(Table, StarModel.__table__)
    director_table = cast(Table, DirectorModel.__table__)
    certification_table = cast(Table, CertificationModel.__table__)

    assert cast(String, movie_table.c.name.type).length == 250
    assert isinstance(movie_table.c.gross.type, Float)
    assert movie_table.c.price.nullable is True
    assert movie_table.c.is_deleted.nullable is False
    assert cast(String, genre_table.c.name.type).length == 100
    assert cast(String, star_table.c.name.type).length == 100
    assert cast(String, director_table.c.name.type).length == 100
    assert cast(String, certification_table.c.name.type).length == 100


def test_movie_identity_has_unique_constraint() -> None:
    movie_table = cast(Table, MovieModel.__table__)
    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in movie_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("name", "year", "time") in unique_columns


@pytest.mark.parametrize(
    ("table", "expected_columns"),
    [
        (MoviesGenresModel, {"movie_id", "genre_id"}),
        (MoviesDirectorsModel, {"movie_id", "director_id"}),
        (MoviesStarsModel, {"movie_id", "star_id"}),
    ],
)
def test_association_tables_use_composite_primary_keys(
    table,
    expected_columns: set[str],
) -> None:
    assert {column.name for column in table.primary_key.columns} == (
        expected_columns
    )


def test_metadata_creates_complete_schema_in_sqlite() -> None:
    engine = create_engine("sqlite://")

    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    assert {
        "certifications",
        "directors",
        "genres",
        "movie_directors",
        "movie_genres",
        "movie_stars",
        "movies",
        "stars",
    }.issubset(table_names)


@pytest.mark.parametrize(("price", "deleted", "available"), [
    (None, False, False), (Decimal("0"), False, True),
    (Decimal("9.99"), False, True), (None, True, False),
    (Decimal("0"), True, False), (Decimal("9.99"), True, False),
])
def test_purchase_availability_uses_price_and_deletion_flag(
    price: Decimal | None, deleted: bool, available: bool,
) -> None:
    movie = MovieModel(price=price, is_deleted=deleted)
    assert movie.is_available_for_purchase is available


def test_new_movie_defaults_to_not_deleted_before_insert() -> None:
    movie = MovieModel(price=Decimal("0"))
    assert movie.is_available_for_purchase is True


@pytest.mark.parametrize("value", [None, 0, 1, "false", "true"])
def test_movie_deletion_flag_requires_boolean(value: Any) -> None:
    with pytest.raises(ValueError):
        MovieModel(is_deleted=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_movie_gross_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError):
        MovieModel(gross=value)

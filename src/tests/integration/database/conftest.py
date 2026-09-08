from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database import (
    Base,
    CertificationModel,
    MovieModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Use an isolated in-memory database with real foreign key enforcement."""
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            Base.metadata.create_all(connection)
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def catalog_users(db_session: Session) -> tuple[UserModel, UserModel]:
    group = UserGroupModel(name=UserGroupEnum.USER)
    users = (
        UserModel(
            email="first@example.com", group=group,
            _hashed_password="unused-in-database-tests",
        ),
        UserModel(
            email="second@example.com", group=group,
            _hashed_password="unused-in-database-tests",
        ),
    )
    db_session.add_all(users)
    db_session.commit()
    return users


@pytest.fixture
def catalog_movies(db_session: Session) -> tuple[MovieModel, MovieModel]:
    certification = CertificationModel(name="PG-13")
    movies = tuple(
        MovieModel(
            name=name,
            year=2020,
            time=120,
            imdb=7.5,
            votes=100,
            description="A test movie.",
            price=Decimal("9.99"),
            certification=certification,
        )
        for name in ("First movie", "Second movie")
    )
    db_session.add_all(movies)
    db_session.commit()
    return movies[0], movies[1]

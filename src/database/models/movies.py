from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DECIMAL,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database.models.base import Base
from src.database.validators import movies as validators

if TYPE_CHECKING:
    from src.database.models.cart import CartItemModel
    from src.database.models.comments import MovieCommentModel
    from src.database.models.favorites import MovieFavoriteModel
    from src.database.models.orders import OrderItemModel
    from src.database.models.ratings import MovieRatingModel
    from src.database.models.reactions import MovieReactionModel


MoviesGenresModel = Table(
    "movie_genres",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

MoviesDirectorsModel = Table(
    "movie_directors",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "director_id",
        ForeignKey("directors.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

MoviesStarsModel = Table(
    "movie_stars",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "star_id",
        ForeignKey("stars.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class GenreModel(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    movies: Mapped[List[MovieModel]] = relationship(
        secondary=MoviesGenresModel,
        back_populates="genres",
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        return validators.validate_name(value)

    def __repr__(self) -> str:
        return f"<GenreModel(id={self.id}, name={self.name!r})>"


class StarModel(Base):
    __tablename__ = "stars"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    movies: Mapped[List[MovieModel]] = relationship(
        secondary=MoviesStarsModel,
        back_populates="stars",
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        return validators.validate_name(value)

    def __repr__(self) -> str:
        return f"<StarModel(id={self.id}, name={self.name!r})>"


class DirectorModel(Base):
    __tablename__ = "directors"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    movies: Mapped[List[MovieModel]] = relationship(
        secondary=MoviesDirectorsModel,
        back_populates="directors",
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        return validators.validate_name(value)

    def __repr__(self) -> str:
        return f"<DirectorModel(id={self.id}, name={self.name!r})>"


class CertificationModel(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    movies: Mapped[List[MovieModel]] = relationship(
        back_populates="certification"
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        return validators.validate_name(value)

    def __repr__(self) -> str:
        return f"<CertificationModel(id={self.id}, name={self.name!r})>"


class MovieModel(Base):
    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint(
            "name",
            "year",
            "time",
            name="uq_movies_name_year_time",
        ),
        CheckConstraint("time > 0", name="positive_duration"),
        CheckConstraint(
            "imdb >= 0 AND imdb <= 10",
            name="valid_imdb_rating",
        ),
        CheckConstraint("votes >= 0", name="non_negative_votes"),
        CheckConstraint(
            "meta_score IS NULL OR "
            "(meta_score >= 0 AND meta_score <= 100)",
            name="valid_meta_score",
        ),
        CheckConstraint(
            "gross IS NULL OR gross >= 0",
            name="non_negative_gross",
        ),
        CheckConstraint("price >= 0", name="non_negative_price"),
        CheckConstraint("price <= 99999999.99", name="valid_price_limit"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    uuid: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
        unique=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    time: Mapped[int] = mapped_column(Integer, nullable=False)
    imdb: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    votes: Mapped[int] = mapped_column(Integer, nullable=False)
    meta_score: Mapped[Optional[float]] = mapped_column(Float)
    gross: Mapped[Optional[float]] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
    )
    certification_id: Mapped[int] = mapped_column(
        ForeignKey("certifications.id", ondelete="RESTRICT"),
        nullable=False,
    )

    certification: Mapped[CertificationModel] = relationship(
        back_populates="movies"
    )
    genres: Mapped[List[GenreModel]] = relationship(
        secondary=MoviesGenresModel,
        back_populates="movies",
    )
    directors: Mapped[List[DirectorModel]] = relationship(
        secondary=MoviesDirectorsModel,
        back_populates="movies",
    )
    stars: Mapped[List[StarModel]] = relationship(
        secondary=MoviesStarsModel,
        back_populates="movies",
    )
    cart_items: Mapped[List[CartItemModel]] = relationship(
        back_populates="movie",
        passive_deletes=True,
    )
    order_items: Mapped[List[OrderItemModel]] = relationship(
        back_populates="movie",
        passive_deletes=True,
    )
    favorites: Mapped[List[MovieFavoriteModel]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    ratings: Mapped[List[MovieRatingModel]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reactions: Mapped[List[MovieReactionModel]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    comments: Mapped[List[MovieCommentModel]] = relationship(
        back_populates="movie", passive_deletes="all",
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        return validators.validate_name(value)

    @validates("time")
    def validate_time(self, _key: str, value: int) -> int:
        return validators.validate_duration(value)

    @validates("imdb")
    def validate_imdb(self, _key: str, value: float) -> float:
        return validators.validate_imdb_rating(value)

    @validates("votes")
    def validate_votes(self, _key: str, value: int) -> int:
        return validators.validate_votes(value)

    @validates("meta_score")
    def validate_meta_score(
        self,
        _key: str,
        value: Optional[float],
    ) -> Optional[float]:
        return validators.validate_meta_score(value)

    @validates("gross")
    def validate_gross(
        self,
        _key: str,
        value: Optional[float],
    ) -> Optional[float]:
        return validators.validate_non_negative_float(value, "gross")

    @validates("price")
    def validate_price(self, _key: str, value: Decimal) -> Decimal:
        validated_price = validators.validate_non_negative_decimal(
            value,
            "price",
        )
        if validated_price is None:
            raise ValueError("Price must not be null.")
        return validated_price

    @classmethod
    def default_order_by(cls):
        return [cls.id.desc()]

    def __repr__(self) -> str:
        return (
            f"<MovieModel(id={self.id}, name={self.name!r}, "
            f"year={self.year})>"
        )

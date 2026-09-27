from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database.models.base import Base
from src.database.validators.ratings import validate_user_rating

if TYPE_CHECKING:
    from src.database.models.accounts import UserModel
    from src.database.models.movies import MovieModel


class MovieRatingModel(Base):
    __tablename__ = "movie_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_movie_ratings"),
        CheckConstraint(
            "score >= 1 AND score <= 10", name="valid_user_rating",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="movie_ratings")
    movie: Mapped[MovieModel] = relationship(back_populates="ratings")

    @validates("score")
    def validate_score(self, _key: str, value: int) -> int:
        """
        Require an integer rating from 1 to 10, rejecting booleans.

        Args:
            _key (str): SQLAlchemy attribute name; unused by the validator.
            value (int): Field value to validate or normalize.

        Returns:
            int: Validated value, normalized when applicable.

        Raises:
            ValueError: The value does not satisfy the validation rules.
        """
        return validate_user_rating(value)

    def __repr__(self) -> str:
        """
        Return a short record representation for debugging.

        Returns:
            str: Model name and identifying fields for debugging.
        """
        return (
            f"<MovieRatingModel(id={self.id}, user_id={self.user_id}, "
            f"movie_id={self.movie_id}, score={self.score})>"
        )

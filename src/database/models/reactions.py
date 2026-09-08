from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database.models.base import Base
from src.database.validators.reactions import validate_movie_reaction

if TYPE_CHECKING:
    from src.database.models.accounts import UserModel
    from src.database.models.movies import MovieModel


class MovieReactionEnum(str, enum.Enum):
    LIKE = "like"
    DISLIKE = "dislike"


class MovieReactionModel(Base):
    __tablename__ = "movie_reactions"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_movie_reactions"),
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
    reaction: Mapped[MovieReactionEnum] = mapped_column(
        Enum(
            MovieReactionEnum,
            name="movie_reaction_enum",
            native_enum=False,
            length=7,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_type: [
                item.value for item in enum_type
            ],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="movie_reactions")
    movie: Mapped[MovieModel] = relationship(back_populates="reactions")

    @validates("reaction")
    def validate_reaction(self, _key: str, value: str) -> MovieReactionEnum:
        return MovieReactionEnum(validate_movie_reaction(value))

    def __repr__(self) -> str:
        return (
            f"<MovieReactionModel(id={self.id}, user_id={self.user_id}, "
            f"movie_id={self.movie_id}, reaction={self.reaction})>"
        )

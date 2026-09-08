from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models.base import Base

if TYPE_CHECKING:
    from src.database.models.accounts import UserModel
    from src.database.models.movies import MovieModel


class MovieFavoriteModel(Base):
    __tablename__ = "movie_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_movie_favorites"),
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
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="favorite_movies")
    movie: Mapped[MovieModel] = relationship(back_populates="favorites")

    def __repr__(self) -> str:
        return (
            f"<MovieFavoriteModel(id={self.id}, user_id={self.user_id}, "
            f"movie_id={self.movie_id})>"
        )

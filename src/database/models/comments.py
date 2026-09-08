from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database.models.base import Base
from src.database.validators.comments import validate_comment_content

if TYPE_CHECKING:
    from src.database.models.accounts import UserModel
    from src.database.models.movies import MovieModel


class MovieCommentModel(Base):
    __tablename__ = "movie_comments"
    __table_args__ = (
        UniqueConstraint("id", "movie_id", name="uq_movie_comments_id_movie"),
        ForeignKeyConstraint(
            ["parent_id", "movie_id"],
            ["movie_comments.id", "movie_comments.movie_id"],
            name="fk_movie_comments_parent_same_movie",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="comment_not_own_parent",
        ),
        CheckConstraint(
            "length(trim(content)) > 0", name="non_empty_comment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="movie_comments")
    movie: Mapped[MovieModel] = relationship(back_populates="comments")
    # Only parent_id is written by this relationship. movie_id is owned by
    # movie; the composite foreign key still enforces the same-film rule.
    parent: Mapped[Optional[MovieCommentModel]] = relationship(
        back_populates="replies", remote_side=[id], foreign_keys=[parent_id],
    )
    replies: Mapped[List[MovieCommentModel]] = relationship(
        back_populates="parent",
        foreign_keys=[parent_id],
        passive_deletes="all",
    )
    likes: Mapped[List[CommentLikeModel]] = relationship(
        back_populates="comment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @validates("content")
    def validate_content(self, _key: str, value: str) -> str:
        return validate_comment_content(value)

    def __repr__(self) -> str:
        return (
            f"<MovieCommentModel(id={self.id}, user_id={self.user_id}, "
            f"movie_id={self.movie_id}, parent_id={self.parent_id})>"
        )


class CommentLikeModel(Base):
    __tablename__ = "comment_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="uq_comment_likes"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("movie_comments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="comment_likes")
    comment: Mapped[MovieCommentModel] = relationship(back_populates="likes")

    def __repr__(self) -> str:
        return (
            f"<CommentLikeModel(id={self.id}, user_id={self.user_id}, "
            f"comment_id={self.comment_id})>"
        )

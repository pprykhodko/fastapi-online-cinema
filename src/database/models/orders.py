from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    CheckConstraint, DateTime, DECIMAL, Enum, ForeignKey, Integer, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database.models.base import Base
from src.database.validators import orders as validators

if TYPE_CHECKING:
    from src.database.models.accounts import UserModel
    from src.database.models.movies import MovieModel
    from src.database.models.payments import PaymentItemModel, PaymentModel


class OrderStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"


class OrderModel(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "total_amount >= 0 AND total_amount <= 99999999.99",
            name="valid_order_total_amount",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[OrderStatusEnum] = mapped_column(
        Enum(
            OrderStatusEnum,
            name="order_status_enum",
            native_enum=False,
            length=50,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_type: [
                item.value for item in enum_type
            ],
        ),
        nullable=False,
        default=OrderStatusEnum.PENDING,
        server_default=OrderStatusEnum.PENDING.value,
    )
    total_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))

    user: Mapped[UserModel] = relationship(back_populates="orders")
    items: Mapped[List[OrderItemModel]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[List[PaymentModel]] = relationship(
        back_populates="order",
        passive_deletes=True,
    )

    @validates("status")
    def validate_status(self, _key: str, value: str) -> OrderStatusEnum:
        return OrderStatusEnum(validators.validate_order_status(value))

    @validates("total_amount")
    def validate_total_amount(
        self,
        _key: str,
        value: Optional[Decimal],
    ) -> Optional[Decimal]:
        return validators.validate_total_amount(value)

    def __repr__(self) -> str:
        return (
            f"<OrderModel(id={self.id}, user_id={self.user_id}, "
            f"status={self.status})>"
        )


class OrderItemModel(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(
            "price_at_order >= 0 AND price_at_order <= 99999999.99",
            name="valid_price_at_order",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price_at_order: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
    )

    order: Mapped[OrderModel] = relationship(back_populates="items")
    movie: Mapped[MovieModel] = relationship(back_populates="order_items")
    payment_items: Mapped[List[PaymentItemModel]] = relationship(
        back_populates="order_item",
        passive_deletes=True,
    )

    @validates("price_at_order")
    def validate_price_at_order(
        self,
        _key: str,
        value: Decimal,
    ) -> Decimal:
        return validators.validate_price_at_order(value)

    def __repr__(self) -> str:
        return (
            f"<OrderItemModel(id={self.id}, order_id={self.order_id}, "
            f"movie_id={self.movie_id})>"
        )

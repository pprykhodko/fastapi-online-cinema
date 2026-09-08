from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    DECIMAL,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database.models.base import Base
from src.database.validators import payments as validators

if TYPE_CHECKING:
    from src.database.models.accounts import UserModel
    from src.database.models.orders import OrderItemModel, OrderModel


class PaymentStatusEnum(str, enum.Enum):
    SUCCESSFUL = "successful"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class PaymentModel(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "amount >= 0 AND amount <= 99999999.99",
            name="valid_payment_amount",
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
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[PaymentStatusEnum] = mapped_column(
        Enum(
            PaymentStatusEnum,
            name="payment_status_enum",
            native_enum=False,
            length=50,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_type: [
                item.value for item in enum_type
            ],
        ),
        nullable=False,
        default=PaymentStatusEnum.SUCCESSFUL,
        server_default=PaymentStatusEnum.SUCCESSFUL.value,
    )
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
    )
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped[UserModel] = relationship(back_populates="payments")
    order: Mapped[OrderModel] = relationship(back_populates="payments")
    items: Mapped[List[PaymentItemModel]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @validates("status")
    def validate_status(self, _key: str, value: str) -> PaymentStatusEnum:
        return PaymentStatusEnum(validators.validate_payment_status(value))

    @validates("amount")
    def validate_amount(self, _key: str, value: Decimal) -> Decimal:
        return validators.validate_payment_amount(value)

    def __repr__(self) -> str:
        return (
            f"<PaymentModel(id={self.id}, user_id={self.user_id}, "
            f"order_id={self.order_id}, status={self.status})>"
        )


class PaymentItemModel(Base):
    __tablename__ = "payment_items"
    __table_args__ = (
        CheckConstraint(
            "price_at_payment >= 0 AND price_at_payment <= 99999999.99",
            name="valid_price_at_payment",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price_at_payment: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
    )

    payment: Mapped[PaymentModel] = relationship(back_populates="items")
    order_item: Mapped[OrderItemModel] = relationship(
        back_populates="payment_items"
    )

    @validates("price_at_payment")
    def validate_price_at_payment(
        self,
        _key: str,
        value: Decimal,
    ) -> Decimal:
        return validators.validate_price_at_payment(value)

    def __repr__(self) -> str:
        return (
            f"<PaymentItemModel(id={self.id}, payment_id={self.payment_id}, "
            f"order_item_id={self.order_item_id})>"
        )

from sqlalchemy import or_, select

from src.database.models import (
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
    PaymentModel,
    PaymentStatusEnum
)
from src.repositories.base import BaseRepository


class OrderRepository(BaseRepository):
    async def purchased_movie_ids(self, user_id: int, movie_ids: list[int]) -> set[int]:
        if not movie_ids:
            return set()

        stmt = select(OrderItemModel.movie_id).join(OrderModel).where(
            OrderModel.user_id == user_id,
            OrderItemModel.movie_id.in_(movie_ids),
            or_(
                OrderModel.status == OrderStatusEnum.PAID,
                OrderModel.payments.any(PaymentModel.status == PaymentStatusEnum.SUCCESSFUL),
                )
        )

        return set((await self.db.scalars(stmt)).all())

    async def pending_movie_ids(self, user_id: int, movie_ids: list[int]) -> set[int]:
        if not movie_ids:
            return set()

        stmt = select(OrderItemModel.movie_id).join(OrderModel).where(
            OrderModel.user_id == user_id,
            OrderModel.status == OrderStatusEnum.PENDING,
            OrderItemModel.movie_id.in_(movie_ids),
            )

        return set((await self.db.scalars(stmt)).all())

    async def add_order(self, order: OrderModel) -> None:
        self.db.add(order)
        await self.db.flush()

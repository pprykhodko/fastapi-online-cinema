from datetime import datetime, time, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from src.database.models import (
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
    PaymentModel,
    PaymentStatusEnum
)
from src.repositories.base import BaseRepository
from src.schemas.orders import AdminOrderListQuerySchema, OrderListQuerySchema


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

    async def get_order(self, order_id: int, user_id: int, lock: bool = False) -> OrderModel | None:
        stmt = (
            select(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.user_id == user_id)
            .options(selectinload(OrderModel.items).selectinload(OrderItemModel.movie))
        )

        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)

        return await self.db.scalar(stmt)

    async def has_completed_payment(self, order_id: int) -> bool:
        stmt = (
            select(PaymentModel.id)
            .where(
                PaymentModel.order_id == order_id,
                PaymentModel.status.in_([PaymentStatusEnum.SUCCESSFUL,PaymentStatusEnum.REFUNDED]))
            .limit(1)
        )

        return await self.db.scalar(stmt) is not None

    async def list_orders(
            self,
            query: OrderListQuerySchema | AdminOrderListQuerySchema,
            user_id: int | None = None
    ) -> tuple[list[OrderModel], int]:
        filters = []

        if user_id is not None:
            filters.append(OrderModel.user_id == user_id)

        if isinstance(query, AdminOrderListQuerySchema):
            if query.user_id is not None:
                filters.append(OrderModel.user_id == query.user_id)

            if query.status is not None:
                filters.append(OrderModel.status == query.status)

            if query.date_from is not None:
                filters.append(OrderModel.created_at >= datetime.combine(query.date_from, time.min, timezone.utc))

            if query.date_to is not None:
                filters.append(OrderModel.created_at <= datetime.combine(query.date_to, time.max, timezone.utc))

        total = await self.db.scalar(select(func.count()).select_from(OrderModel).where(*filters)) or 0
        stmt = (
            select(OrderModel).where(*filters)
            .options(selectinload(OrderModel.items).selectinload(OrderItemModel.movie))
            .order_by(OrderModel.created_at.desc(), OrderModel.id.desc())
            .offset((query.page - 1) * query.per_page).limit(query.per_page)
        )

        return list((await self.db.scalars(stmt)).all()), total

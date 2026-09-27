from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from src.database.models import (
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
    PaymentModel,
    PaymentCheckoutModel,
    PaymentStatusEnum
)
from src.repositories.base import BaseRepository
from src.repositories.transaction_filters import transaction_filters
from src.schemas.orders import AdminOrderListQuerySchema, OrderListQuerySchema


class OrderRepository(BaseRepository):
    async def get_by_id(self, order_id: int, lock: bool = False) -> OrderModel | None:
        """
        Look up the record by primary key without applying an ownership check.

        The caller controls the transaction commit.

        Args:
            order_id (int): ID of the order.
            lock (bool): Request a row lock for this transaction when supported by the
                database.

        Returns:
            OrderModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        stmt = (
            select(OrderModel)
            .where(OrderModel.id == order_id)
            .options(selectinload(OrderModel.items))
        )

        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)

        return await self.db.scalar(stmt)

    async def has_checkout(self, order_id: int) -> bool:
        """
        Check whether any persisted Stripe checkout exists for the order.

        The caller controls the transaction commit.

        Args:
            order_id (int): ID of the order.

        Returns:
            bool: Whether the order has a checkout record in any state.
        """
        return await self.db.scalar(
            select(PaymentCheckoutModel.id)
            .where(PaymentCheckoutModel.order_id == order_id)
        ) is not None

    async def purchased_movie_ids(self, user_id: int, movie_ids: list[int]) -> set[int]:
        """
        Find requested movie IDs covered by a paid order or successful payment for the
        user.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_ids (list[int]): Movie IDs to include in the operation.

        Returns:
            set[int]: Matching movie IDs from the supplied list.
        """
        if not movie_ids:
            return set()

        stmt = select(OrderItemModel.movie_id).join(OrderModel).where(
            OrderModel.user_id == user_id,
            OrderItemModel.movie_id.in_(movie_ids),
            or_(
                OrderModel.status == OrderStatusEnum.PAID,
                OrderModel.payments.any(
                    PaymentModel.status == PaymentStatusEnum.SUCCESSFUL
                )
            )
        )

        return set((await self.db.scalars(stmt)).all())

    async def pending_movie_ids(self, user_id: int, movie_ids: list[int]) -> set[int]:
        """
        Find requested movie IDs already present in the user pending orders.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_ids (list[int]): Movie IDs to include in the operation.

        Returns:
            set[int]: Matching movie IDs from the supplied list.
        """
        if not movie_ids:
            return set()

        stmt = select(OrderItemModel.movie_id).join(OrderModel).where(
            OrderModel.user_id == user_id,
            OrderModel.status == OrderStatusEnum.PENDING,
            OrderItemModel.movie_id.in_(movie_ids),
            )

        return set((await self.db.scalars(stmt)).all())

    async def add_order(self, order: OrderModel) -> None:
        """
        Add and flush an order and its items without committing.

        Args:
            order (OrderModel): Order with its loaded items and saved prices.
        """
        self.db.add(order)
        await self.db.flush()

    async def get_order(
            self,
            order_id: int,
            user_id: int,
            lock: bool = False
    ) -> OrderModel | None:
        """
        Load the owned order with its items and movies, optionally locking it.

        The caller controls the transaction commit.

        Args:
            order_id (int): ID of the order.
            user_id (int): ID of the account whose data is being accessed.
            lock (bool): Request a row lock for this transaction when supported by the
                database.

        Returns:
            OrderModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        stmt = (
            select(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.user_id == user_id)
            .options(selectinload(OrderModel.items).selectinload(OrderItemModel.movie))
        )

        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)

        return await self.db.scalar(stmt)

    async def has_completed_payment(self, order_id: int) -> bool:
        """
        Check whether the order has a successful or refunded payment.

        The caller controls the transaction commit.

        Args:
            order_id (int): ID of the order.

        Returns:
            bool: Whether the order has a successful or refunded payment.
        """
        stmt = (
            select(PaymentModel.id)
            .where(
                PaymentModel.order_id == order_id,
                PaymentModel.status.in_(
                    [PaymentStatusEnum.SUCCESSFUL, PaymentStatusEnum.REFUNDED]
                )
            ).limit(1)
        )

        return await self.db.scalar(stmt) is not None

    async def list_orders(
            self,
            query: OrderListQuerySchema | AdminOrderListQuerySchema,
            user_id: int | None = None
    ) -> tuple[list[OrderModel], int]:
        """
        Return paginated order history, optionally restricted to an owner.

        The caller controls the transaction commit.

        Args:
            query (OrderListQuerySchema | AdminOrderListQuerySchema): Validated
                pagination and any supported search, sort or filter options.
            user_id (int | None): ID of the account whose data is being accessed.

        Returns:
            tuple[list[OrderModel], int]: Records on this page and the total count
                before pagination.
        """
        filters = transaction_filters(OrderModel, query, user_id)

        total = await self.db.scalar(
            select(func.count())
            .select_from(OrderModel)
            .where(*filters)
        ) or 0
        stmt = (
            select(OrderModel).where(*filters)
            .options(selectinload(OrderModel.items).selectinload(OrderItemModel.movie))
            .order_by(OrderModel.created_at.desc(), OrderModel.id.desc())
            .offset((query.page - 1) * query.per_page).limit(query.per_page)
        )

        return list((await self.db.scalars(stmt)).all()), total

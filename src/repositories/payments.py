from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.database.models import (
    MovieModel,
    OrderItemModel,
    PaymentCheckoutModel,
    PaymentItemModel,
    PaymentModel,
    PaymentStatusEnum,
    UserModel
)
from src.repositories.base import BaseRepository
from src.repositories.transaction_filters import transaction_filters
from src.schemas.payments import AdminPaymentListQuerySchema, PaymentListQuerySchema


class PaymentRepository(BaseRepository):
    async def checkout_for_order(self, order_id: int) -> PaymentCheckoutModel | None:
        """
        Load fresh checkout state by order ID.

        The caller controls the transaction commit.

        Args:
            order_id (int): ID of the order.

        Returns:
            PaymentCheckoutModel | None: Matching database record(s), or None when
                allowed and not found.
        """
        return await self.db.scalar(
            select(PaymentCheckoutModel)
            .where(PaymentCheckoutModel.order_id == order_id)
            .execution_options(populate_existing=True)
        )

    async def checkout_for_session(
            self,
            session_id: str
    ) -> PaymentCheckoutModel | None:
        """
        Look up saved checkout state by Stripe session ID.

        The caller controls the transaction commit.

        Args:
            session_id (str): Stripe Checkout session ID.

        Returns:
            PaymentCheckoutModel | None: Matching database record(s), or None when
                allowed and not found.
        """
        return await self.db.scalar(
            select(PaymentCheckoutModel)
            .where(PaymentCheckoutModel.session_id == session_id)
        )

    async def add(self, record: PaymentCheckoutModel | PaymentModel) -> None:
        """
        Add and flush the supplied record without committing the shared transaction.

        Args:
            record (PaymentCheckoutModel | PaymentModel): ORM record supplied for this
                database operation.
        """
        self.db.add(record)
        await self.db.flush()

    async def get_payment(
            self,
            payment_id: int,
            user_id: int | None = None
    ) -> PaymentModel | None:
        """
        Return payment details and the saved item prices.

        The caller controls the transaction commit.

        Args:
            payment_id (int): ID of the stored payment.
            user_id (int | None): ID of the account whose data is being accessed.

        Returns:
            PaymentModel | None: Matching database record(s), or None when allowed and
                not found.
        """
        stmt = (
            select(PaymentModel)
            .where(PaymentModel.id == payment_id)
            .options(selectinload(PaymentModel.items))
        )

        if user_id is not None:
            stmt = stmt.where(PaymentModel.user_id == user_id)

        return await self.db.scalar(stmt.execution_options(populate_existing=True))

    async def payment_by_external_id(self, external_id: str) -> PaymentModel | None:
        """
        Look up a payment using its Stripe transaction identifier.

        The caller controls the transaction commit.

        Args:
            external_id (str): Stripe transaction identifier stored on a payment.

        Returns:
            PaymentModel | None: Matching database record(s), or None when allowed and
                not found.
        """
        return await self.db.scalar(
            select(PaymentModel)
            .where(PaymentModel.external_payment_id == external_id)
        )

    async def user_email(self, user_id: int) -> str:
        """
        Load the email of an existing user for payment notifications.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            str: Email address of the selected account.
        """
        return (await self.db.scalars(
            select(UserModel.email)
            .where(UserModel.id == user_id))).one()

    async def list_payments(
            self,
            query: PaymentListQuerySchema | AdminPaymentListQuerySchema,
            user_id: int | None = None
    ) -> tuple[list[PaymentModel], int]:
        """
        Return paginated payment history, optionally restricted to an owner.

        The caller controls the transaction commit.

        Args:
            query (PaymentListQuerySchema | AdminPaymentListQuerySchema): Validated
                pagination and any supported search, sort or filter options.
            user_id (int | None): ID of the account whose data is being accessed.

        Returns:
            tuple[list[PaymentModel], int]: Records on this page and the total count
                before pagination.
        """
        filters = transaction_filters(PaymentModel, query, user_id)

        total = await self.db.scalar(
            select(func.count())
            .select_from(PaymentModel)
            .where(*filters)
        ) or 0
        stmt = (
            select(PaymentModel)
            .where(*filters)
            .options(selectinload(PaymentModel.items))
            .order_by(PaymentModel.created_at.desc(), PaymentModel.id.desc())
            .offset((query.page - 1) * query.per_page).limit(query.per_page)
        )

        return list((await self.db.scalars(stmt)).all()), total

    async def purchased_movies(
            self,
            user_id: int,
            page: int, per_page: int
    ) -> tuple[list[MovieModel], int]:
        """
        Return paginated movies covered by successful, non-refunded payments.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            page (int): Page number starting at 1.
            per_page (int): Maximum number of records on one page.

        Returns:
            tuple[list[MovieModel], int]: Records on this page and the total count
                before pagination.
        """
        purchased = (
            select(OrderItemModel.movie_id)
            .join(PaymentItemModel)
            .join(PaymentModel)
            .where(
                PaymentModel.user_id == user_id,
                PaymentModel.status == PaymentStatusEnum.SUCCESSFUL
            )
        )
        condition = MovieModel.id.in_(purchased)
        total = await self.db.scalar(
            select(func.count())
            .select_from(MovieModel)
            .where(condition)
        ) or 0
        stmt = (
            select(MovieModel)
            .where(condition)
            .options(selectinload(MovieModel.genres))
            .order_by(MovieModel.id).offset((page - 1) * per_page).limit(per_page)
        )

        return list((await self.db.scalars(stmt)).all()), total

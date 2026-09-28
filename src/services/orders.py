from decimal import Decimal

from fastapi import HTTPException, status

from src.database.models import OrderItemModel, OrderModel, OrderStatusEnum
from src.repositories.cart import CartRepository
from src.repositories.movies import MovieRepository
from src.repositories.orders import OrderRepository
from src.schemas.orders import (
    AdminOrderListQuerySchema,
    OrderCreateResponseSchema,
    OrderExcludedItemSchema,
    OrderListQuerySchema,
    OrderListResponseSchema,
    OrderResponseSchema
)
from src.services.database_errors import database_errors


class OrderService:
    def __init__(
            self,
            repository: OrderRepository,
            cart_repository: CartRepository,
            movie_repository: MovieRepository
    ):
        """
        Initialize OrderService with its required dependencies.

        Args:
            repository (OrderRepository): Repository used for database operations and
                the shared transaction.
            cart_repository (CartRepository): Repository for cart data using the shared
                session.
            movie_repository (MovieRepository): Repository for movie data using the
                shared session.
        """
        self.repository = repository
        self.cart_repository = cart_repository
        self.movie_repository = movie_repository

    async def list_orders(
            self,
            query: OrderListQuerySchema | AdminOrderListQuerySchema,
            user_id: int | None = None
    ) -> OrderListResponseSchema:
        """
        Return paginated order history, optionally restricted to an owner.

        Args:
            query (OrderListQuerySchema | AdminOrderListQuerySchema): Validated
                pagination and any supported search, sort or filter options.
            user_id (int | None): ID of the account whose data is being accessed.

        Returns:
            OrderListResponseSchema: Order records and pagination totals.

        Raises:
            HTTPException: The requested data cannot be loaded from the database.
        """
        async with database_errors(
                self.repository,
                detail="Orders are temporarily unavailable"
        ):
            orders, total = await self.repository.list_orders(query, user_id=user_id)

            return OrderListResponseSchema(
                items=[OrderResponseSchema.model_validate(order) for order in orders],
                total=total,
                page=query.page,
                per_page=query.per_page
            )

    async def get_owned_order(
            self,
            user_id: int,
            order_id: int,
            lock: bool = False
    ) -> OrderModel:
        """
        Load the order only if it belongs to the specified user, otherwise raise 404.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            order_id (int): ID of the order.
            lock (bool): Request a row lock for this transaction when supported by the
                database.

        Returns:
            OrderModel: Requested database record(s).

        Raises:
            HTTPException: The order is missing or belongs to another user.
        """
        order = await self.repository.get_order(order_id, user_id, lock=lock)

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        return order

    async def get_order(self, user_id: int, order_id: int) -> OrderResponseSchema:
        """
        Return the owned order with its items and historical prices.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            order_id (int): ID of the order.

        Returns:
            OrderResponseSchema: Order status, creation time, movies and historical item
                prices.

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
        async with database_errors(
                self.repository,
                detail="Order is temporarily unavailable"
        ):
            order = await self.get_owned_order(user_id, order_id)

            return OrderResponseSchema.model_validate(order)

    async def cancel_order(self, user_id: int, order_id: int) -> OrderResponseSchema:
        """
        Cancel an unpaid pending order that does not have a Stripe checkout.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            order_id (int): ID of the order.

        Returns:
            OrderResponseSchema: Order status, creation time, movies and historical item
                prices.

        Raises:
            HTTPException: The order is missing, paid, canceled, has a Stripe checkout
                or cannot be saved.
        """
        async with database_errors(
                self.repository,
                detail="Order could not be canceled"
        ):
            order = await self.get_owned_order(user_id, order_id, lock=True)

            if await self.repository.has_checkout(order.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This order has a Stripe checkout. "
                           "Cancel it through Payments, "
                           "or request a refund if paid."
                )

            if (
                    order.status == OrderStatusEnum.PAID
                    or await self.repository.has_completed_payment(order.id)
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A paid order cannot be canceled. "
                           "Request a payment refund instead."
                )

            if order.status != OrderStatusEnum.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only pending orders can be canceled"
                )

            order.status = OrderStatusEnum.CANCELED
            response = OrderResponseSchema.model_validate(order)
            await self.repository.commit()

            return response

    async def prepare_for_payment(self, user_id: int, order_id: int) -> OrderModel:
        """
        Validate and lock an order; the payment caller owns the final commit.

        No payment is created here. The caller must use this same DB session.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            order_id (int): ID of the order.

        Returns:
            OrderModel: Requested database record(s).

        Raises:
            HTTPException: The order is not payable, contains unavailable/purchased
                movies or its prices changed.
        """
        async with database_errors(
                self.repository,
                detail="Order validation is temporarily unavailable"
        ):
            order = await self.get_owned_order(user_id, order_id, lock=True)

            if (
                    order.status != OrderStatusEnum.PENDING
                    or await self.repository.has_completed_payment(order.id)
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only an unpaid pending order can be paid"
                )

            if not order.items:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The order has no movies"
                )

            movie_ids = [item.movie_id for item in order.items]
            checkout_movies = await self.movie_repository.get_checkout_movies(movie_ids)
            movies = {movie.id: movie for movie in checkout_movies}

            if await self.repository.purchased_movie_ids(user_id, movie_ids):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The order contains already purchased movies. "
                           "Cancel it and create a new order."
                )

            for item in order.items:
                movie = movies.get(item.movie_id)

                if movie is None or not movie.is_available_for_purchase:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The order contains unavailable movies. "
                               "Cancel it and create a new order."
                    )

                if movie.price != item.price_at_order:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Movie prices changed. Cancel the order and "
                               "create a new one to confirm the new prices."
                    )

            total = sum((item.price_at_order for item in order.items), Decimal("0.00"))

            if total > Decimal("99999999.99") or total != order.total_amount:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The order total is inconsistent. "
                           "Cancel it and create a new order."
                )

            return order

    async def checkout(self, user_id: int) -> OrderCreateResponseSchema:
        """
        Create a pending order from eligible cart items and report excluded movies.

        Steps:
        - Load cart movies and exclude unavailable or already purchased entries.
        - Reject movies that belong to another pending order.
        - Save eligible movies with a price snapshot and report excluded items.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            OrderCreateResponseSchema: Created order, or None if all items were
                excluded, plus exclusion reasons.

        Raises:
            HTTPException: The cart is missing/empty, movies overlap pending orders or
                saving the order fails.
        """
        async with database_errors(
                self.repository,
                detail="Order could not be created",
                conflict_detail="Cart data changed. Please try again."
        ):
            cart = await self.cart_repository.get_cart(user_id, lock=True)

            if cart is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart not found"
                )

            movie_ids = await self.cart_repository.get_movie_ids(cart.id)

            if not movie_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Your cart is empty"
                )

            checkout_movies = await self.movie_repository.get_checkout_movies(movie_ids)
            movies = {movie.id: movie for movie in checkout_movies}
            purchased = await self.repository.purchased_movie_ids(user_id, movie_ids)
            excluded = []
            available = []

            for movie_id in movie_ids:
                movie = movies.get(movie_id)

                if movie_id in purchased:
                    reason = "Movie has already been purchased"

                elif movie is None or not movie.is_available_for_purchase:
                    reason = "Movie is not available for purchase"

                else:
                    available.append(movie)
                    continue

                excluded.append(
                    OrderExcludedItemSchema(
                        movie_id=movie_id,
                        reason=reason)
                )

            pending = await self.repository.pending_movie_ids(
                user_id,
                [movie.id for movie in available]
            )

            if pending:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Movies already belong to a pending order: "
                           f"{', '.join(map(str, sorted(pending)))}"
                )

            response_order = None

            if available:
                total = sum(
                    (movie.price for movie in available if movie.price is not None),
                    Decimal("0.00")
                )

                if total > Decimal("99999999.99"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Order total exceeds the allowed amount"
                    )

                order = OrderModel(
                    user_id=user_id,
                    status=OrderStatusEnum.PENDING,
                    total_amount=total,
                    items=[
                        OrderItemModel(
                            movie=movie,
                            price_at_order=movie.price
                        ) for movie in available
                    ]
                )
                await self.repository.add_order(order)
                response_order = OrderResponseSchema.model_validate(order)
            await self.cart_repository.remove_items(
                cart.id,
                [item.movie_id for item in excluded]
            )
            await self.repository.commit()

            return OrderCreateResponseSchema(
                message="Order created. Payment is required"
                if response_order else "No movies available for purchase",
                order=response_order,
                excluded_items=excluded
            )

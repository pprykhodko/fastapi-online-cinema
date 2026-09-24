from decimal import Decimal

from fastapi import HTTPException, status

from src.database.models import OrderItemModel, OrderModel, OrderStatusEnum
from src.repositories.cart import CartRepository
from src.repositories.movies import MovieRepository
from src.repositories.orders import OrderRepository
from src.schemas.orders import OrderCreateResponseSchema, OrderExcludedItemSchema, OrderResponseSchema
from src.services.database_errors import database_errors


class OrderService:
    def __init__(
            self,
            repository: OrderRepository,
            cart_repository: CartRepository,
            movie_repository: MovieRepository
    ):
        self.repository = repository
        self.cart_repository = cart_repository
        self.movie_repository = movie_repository

    async def checkout(self, user_id: int) -> OrderCreateResponseSchema:
        async with database_errors(
                self.repository, detail="Order could not be created",
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

            movies = {movie.id: movie for movie in await self.movie_repository.get_checkout_movies(movie_ids)}
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

                excluded.append(OrderExcludedItemSchema(movie_id=movie_id, reason=reason))

            pending = await self.repository.pending_movie_ids(user_id, [movie.id for movie in available])

            if pending:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Movies already belong to a pending order: {', '.join(map(str, sorted(pending)))}",
                )

            response_order = None

            if available:
                total = sum((movie.price for movie in available if movie.price is not None), Decimal("0.00"))

                if total > Decimal("99999999.99"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Order total exceeds the allowed amount"
                    )

                order = OrderModel(
                    user_id=user_id,
                    status=OrderStatusEnum.PENDING,
                    total_amount=total,
                    items=[OrderItemModel(movie=movie, price_at_order=movie.price) for movie in available]
                )
                await self.repository.add_order(order)
                response_order = OrderResponseSchema.model_validate(order)
            await self.cart_repository.remove_items(cart.id, [item.movie_id for item in excluded])
            await self.repository.commit()

            return OrderCreateResponseSchema(
                message="Order created. Payment is required" if response_order else "No movies available for purchase",
                order=response_order,
                excluded_items=excluded
            )

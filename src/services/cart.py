from fastapi import HTTPException, status

from src.database.models import CartItemModel, CartModel
from src.repositories.cart import CartRepository
from src.repositories.movies import MovieRepository
from src.repositories.orders import OrderRepository
from src.schemas.cart import CartItemResponseSchema, CartResponseSchema
from src.services.database_errors import database_errors
from src.services.movie_checks import get_movie_or_404


class CartService:
    def __init__(
            self, repository: CartRepository,
            movie_repository: MovieRepository,
            order_repository: OrderRepository
    ):
        """
        Initialize CartService with its required dependencies.

        Args:
            repository (CartRepository): Repository used for database operations and the
                shared transaction.
            movie_repository (MovieRepository): Repository for movie data using the
                shared session.
            order_repository (OrderRepository): Repository for order data using the
                shared session.
        """
        self.repository = repository
        self.movie_repository = movie_repository
        self.order_repository = order_repository

    async def _get_cart(self, user_id: int, lock: bool = False) -> CartModel:
        """
        Load the user cart or raise 404, optionally requesting a row lock.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            lock (bool): Request a row lock for this transaction when supported by the
                database.

        Returns:
            CartModel: Requested database record(s).

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
        cart = await self.repository.get_cart(user_id, lock=lock)

        if cart is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cart not found"
            )

        return cart

    async def get_cart(self, user_id: int) -> CartResponseSchema:
        """
        Return the user cart with current movie prices, genres and release years.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Returns:
            CartResponseSchema: Cart ID, owner ID and items with current movie
                information.

        Raises:
            HTTPException: The requested record is missing or cannot be loaded.
        """
        async with database_errors(
                self.repository,
                detail="Cart is temporarily unavailable"
        ):
            cart = await self._get_cart(user_id)
            items = await self.repository.get_items(cart.id)

            return CartResponseSchema(
                id=cart.id,
                user_id=cart.user_id,
                items=[CartItemResponseSchema.model_validate(item) for item in items]
            )

    async def add_item(self, user_id: int, movie_id: int) -> CartItemResponseSchema:
        """
        Add an available movie to the cart unless it is duplicated or already purchased.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            CartItemResponseSchema: Saved cart item with movie information and time
                added.

        Raises:
            HTTPException: The movie is unavailable, purchased or duplicated, or the
                cart/database is unavailable.
        """
        async with database_errors(
                self.repository,
                detail="Movie could not be added to the cart",
                conflict_detail="The movie is already in the cart or its data changed"
        ):
            cart = await self._get_cart(user_id, lock=True)
            movie = await get_movie_or_404(
                self.movie_repository,
                movie_id,
                lock=True,
                with_relations=True
            )

            if not movie.is_available_for_purchase:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Movie is not available for purchase"
                )

            if await self.order_repository.purchased_movie_ids(user_id, [movie_id]):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You have already purchased this movie. "
                           "Repeat purchases are not allowed"
                )

            if await self.repository.get_item(cart.id, movie_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Movie is already in your cart"
                )

            item = CartItemModel(cart_id=cart.id, movie=movie)
            await self.repository.add_item(item)
            response = CartItemResponseSchema.model_validate(item)
            await self.repository.commit()
            return response

    async def remove_item(self, user_id: int, movie_id: int) -> None:
        """
        Remove the selected movie from the user cart.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            movie_id (int): ID of the movie, not the cart or order item.

        Raises:
            HTTPException: The record is missing or database constraints prevent
                removal.
        """
        async with database_errors(
                self.repository,
                detail="Cart item could not be removed"
        ):
            cart = await self._get_cart(user_id, lock=True)

            if not await self.repository.remove_item(cart.id, movie_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Movie is not in your cart"
                )

            await self.repository.commit()

    async def clear_cart(self, user_id: int) -> None:
        """
        Remove all items from the user cart without deleting the cart itself.

        Args:
            user_id (int): ID of the account whose data is being accessed.

        Raises:
            HTTPException: The target record is missing, conflicts with stored data or
                cannot be saved.
        """
        async with database_errors(self.repository, detail="Cart could not be cleared"):
            cart = await self._get_cart(user_id, lock=True)
            await self.repository.clear(cart.id)
            await self.repository.commit()

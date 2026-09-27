from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.database.models import CartItemModel, CartModel, MovieModel
from src.repositories.base import BaseRepository


class CartRepository(BaseRepository):
    def add_cart(self, user_id: int) -> None:
        """
        Stage an empty cart for the user without committing.

        Args:
            user_id (int): ID of the account whose data is being accessed.
        """
        self.db.add(CartModel(user_id=user_id))

    async def get_cart(self, user_id: int, lock: bool = False) -> CartModel | None:
        """
        Look up the user cart, optionally requesting a row lock.

        The caller controls the transaction commit.

        Args:
            user_id (int): ID of the account whose data is being accessed.
            lock (bool): Request a row lock for this transaction when supported by the
                database.

        Returns:
            CartModel | None: Matching database record(s), or None when allowed and not
                found.
        """
        stmt = select(CartModel).where(CartModel.user_id == user_id)

        if lock:
            stmt = stmt.with_for_update()

        return await self.db.scalar(stmt)

    async def get_items(self, cart_id: int) -> list[CartItemModel]:
        """
        Load cart items with their movies and genres in cart-item ID order.

        The caller controls the transaction commit.

        Args:
            cart_id (int): ID of the cart, not the user account.

        Returns:
            list[CartItemModel]: Requested database record(s).
        """
        stmt = (
            select(CartItemModel)
            .where(CartItemModel.cart_id == cart_id)
            .options(selectinload(CartItemModel.movie).selectinload(MovieModel.genres))
            .order_by(CartItemModel.id)
        )

        return list((await self.db.scalars(stmt)).all())

    async def get_item(self, cart_id: int, movie_id: int) -> CartItemModel | None:
        """
        Look up a movie entry in the selected cart.

        The caller controls the transaction commit.

        Args:
            cart_id (int): ID of the cart, not the user account.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            CartItemModel | None: Matching database record(s), or None when allowed and
                not found.
        """
        return await self.db.scalar(
            select(CartItemModel)
            .where(
                CartItemModel.cart_id == cart_id, CartItemModel.movie_id == movie_id
            )
        )

    async def get_movie_ids(self, cart_id: int) -> list[int]:
        """
        Return cart movie IDs in cart-item ID order.

        The caller controls the transaction commit.

        Args:
            cart_id (int): ID of the cart, not the user account.

        Returns:
            list[int]: Movie IDs in cart-item ID order.
        """
        stmt = (
            select(CartItemModel.movie_id)
            .where(CartItemModel.cart_id == cart_id)
            .order_by(CartItemModel.id)
        )

        return list((await self.db.scalars(stmt)).all())

    async def remove_items(self, cart_id: int, movie_ids: list[int]) -> None:
        """
        Remove selected movies from a cart without committing.

        Args:
            cart_id (int): ID of the cart, not the user account.
            movie_ids (list[int]): Movie IDs to include in the operation.
        """
        if not movie_ids:
            return

        await self.db.execute(
            delete(CartItemModel)
            .where(
                CartItemModel.cart_id == cart_id, CartItemModel.movie_id.in_(movie_ids)
            )
        )

    async def add_item(self, item: CartItemModel) -> None:
        """
        Add and flush a cart item without committing.

        Args:
            item (CartItemModel): ORM record supplied for this database operation.
        """
        self.db.add(item)
        await self.db.flush()

    async def remove_item(self, cart_id: int, movie_id: int) -> bool:
        """
        Delete a movie entry from the cart without committing.

        Args:
            cart_id (int): ID of the cart, not the user account.
            movie_id (int): ID of the movie, not the cart or order item.

        Returns:
            bool: True if a matching record was deleted; otherwise False.
        """
        deleted_id = await self.db.scalar(
            delete(CartItemModel).where(
                CartItemModel.cart_id == cart_id, CartItemModel.movie_id == movie_id,
                ).returning(CartItemModel.id)
        )
        return deleted_id is not None

    async def clear(self, cart_id: int) -> None:
        """
        Delete all items in a cart without deleting the cart or committing.

        Args:
            cart_id (int): ID of the cart, not the user account.
        """
        await self.db.execute(
            delete(CartItemModel)
            .where(CartItemModel.cart_id == cart_id)
        )

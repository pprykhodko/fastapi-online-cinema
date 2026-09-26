from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.database.models import CartItemModel, CartModel, MovieModel
from src.repositories.base import BaseRepository


class CartRepository(BaseRepository):
    def add_cart(self, user_id: int) -> None:
        self.db.add(CartModel(user_id=user_id))

    async def get_cart(self, user_id: int, lock: bool = False) -> CartModel | None:
        stmt = select(CartModel).where(CartModel.user_id == user_id)

        if lock:
            stmt = stmt.with_for_update()

        return await self.db.scalar(stmt)

    async def get_items(self, cart_id: int) -> list[CartItemModel]:
        stmt = (
            select(CartItemModel)
            .where(CartItemModel.cart_id == cart_id)
            .options(selectinload(CartItemModel.movie).selectinload(MovieModel.genres))
            .order_by(CartItemModel.id)
        )

        return list((await self.db.scalars(stmt)).all())

    async def get_item(self, cart_id: int, movie_id: int) -> CartItemModel | None:
        return await self.db.scalar(
            select(CartItemModel)
            .where(
                CartItemModel.cart_id == cart_id, CartItemModel.movie_id == movie_id
            )
        )

    async def get_movie_ids(self, cart_id: int) -> list[int]:
        stmt = (
            select(CartItemModel.movie_id)
            .where(CartItemModel.cart_id == cart_id)
            .order_by(CartItemModel.id)
        )

        return list((await self.db.scalars(stmt)).all())

    async def remove_items(self, cart_id: int, movie_ids: list[int]) -> None:
        if not movie_ids:
            return

        await self.db.execute(
            delete(CartItemModel)
            .where(
                CartItemModel.cart_id == cart_id, CartItemModel.movie_id.in_(movie_ids)
            )
        )

    async def add_item(self, item: CartItemModel) -> None:
        self.db.add(item)
        await self.db.flush()

    async def remove_item(self, cart_id: int, movie_id: int) -> bool:
        deleted_id = await self.db.scalar(
            delete(CartItemModel).where(
                CartItemModel.cart_id == cart_id, CartItemModel.movie_id == movie_id,
                ).returning(CartItemModel.id)
        )
        return deleted_id is not None

    async def clear(self, cart_id: int) -> None:
        await self.db.execute(
            delete(CartItemModel)
            .where(CartItemModel.cart_id == cart_id)
        )

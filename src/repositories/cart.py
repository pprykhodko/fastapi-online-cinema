from src.database.models import CartModel
from src.repositories.base import BaseRepository


class CartRepository(BaseRepository):
    def add_cart(self, user_id: int) -> None:
        self.db.add(CartModel(user_id=user_id))

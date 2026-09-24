from unittest.mock import AsyncMock

import pytest

from src.repositories.cart import CartRepository
from src.repositories.orders import OrderRepository


@pytest.mark.asyncio
async def test_excluded_items_are_deleted_in_one_scoped_query():
    db = AsyncMock()
    repository = CartRepository(db)
    await repository.remove_items(7, [1, 2, 3])
    db.execute.assert_awaited_once()
    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "cart_items.cart_id = 7" in sql
    assert "cart_items.movie_id IN (1, 2, 3)" in sql
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_exclusion_does_not_query_database():
    db = AsyncMock()
    await CartRepository(db).remove_items(7, [])
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["purchased_movie_ids", "pending_movie_ids"])
async def test_empty_movie_checks_do_not_query_database(method):
    db = AsyncMock()
    assert await getattr(OrderRepository(db), method)(1, []) == set()
    db.scalars.assert_not_awaited()

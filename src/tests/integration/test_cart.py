from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from src.api.dependencies import get_cart_service, get_order_service
from src.database.models import (
    CartItemModel, CartModel, CertificationModel, GenreModel, MovieModel,
    OrderItemModel, OrderModel, OrderStatusEnum, PaymentModel, PaymentStatusEnum,
    UserGroupEnum, UserGroupModel, UserModel,
)
from src.main import app
from src.repositories.cart import CartRepository
from src.repositories.orders import OrderRepository


URL = "/api/v1/cart/"


@pytest_asyncio.fixture
async def cart_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(email="other@example.com", group_id=user.group_id, _hashed_password="unused", is_active=True)
        db.add(other)
        await db.flush()
        other_id = other.id
        db.add_all([CartModel(user_id=user_id), CartModel(user_id=other_id)])
        genre = GenreModel(name="Drama")
        certification = CertificationModel(name="PG")
        for movie_id, price in [(1, "10.25"), (2, "0"), (3, None), (4, "5"), (5, "2.15")]:
            db.add(MovieModel(
                id=movie_id, name=f"Movie {movie_id}", year=2020, time=90,
                imdb=8, votes=5, description="Story", genres=[genre],
                certification=certification, price=Decimal(price) if price is not None else None,
                is_deleted=movie_id == 4,
            ))
        await db.commit()
    headers = {"Authorization": f"Bearer {manager.create_access_token(user_id)}"}
    other_headers = {"Authorization": f"Bearer {manager.create_access_token(other_id)}"}
    return client, sessions, user_id, other_id, headers, other_headers


async def seed_order(sessions, user_id, movie_ids, order_status=OrderStatusEnum.PAID, payment_status=None):
    async with sessions() as db:
        order = OrderModel(
            user_id=user_id, status=order_status, total_amount=Decimal("10"),
            items=[OrderItemModel(movie_id=movie_id, price_at_order=Decimal("10")) for movie_id in movie_ids],
        )
        db.add(order)
        await db.flush()
        if payment_status is not None:
            db.add(PaymentModel(user_id=user_id, order_id=order.id, status=payment_status, amount=Decimal("10")))
        await db.commit()
        return order.id


@pytest.mark.asyncio
async def test_cart_lifecycle_and_isolation(cart_api):
    client, sessions, user_id, _, headers, other_headers = cart_api
    empty = await client.get(URL, headers=headers)
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    cart_id = empty.json()["id"]
    assert empty.json()["user_id"] == user_id
    for auth in (headers, other_headers):
        added = await client.post(URL + "items/", headers=auth, json={"movie_id": 1})
        assert added.status_code == 201, added.text
        movie = added.json()["movie"]
        assert (movie["name"], movie["year"], movie["price"]) == ("Movie 1", 2020, "10.25")
        assert movie["genres"][0]["name"] == "Drama"
        assert added.json()["added_at"]
    assert (await client.post(URL + "items/", headers=headers, json={"movie_id": 1})).status_code == 409
    assert (await client.post(URL + "items/", headers=headers, json={"movie_id": 2})).status_code == 201
    assert len((await client.get(URL, headers=headers)).json()["items"]) == 2
    removed = await client.delete(URL + "items/1/", headers=headers)
    assert removed.status_code == 204 and not removed.content
    assert (await client.delete(URL + "items/1/", headers=headers)).status_code == 404
    assert len((await client.get(URL, headers=other_headers)).json()["items"]) == 1
    for _ in range(2):
        cleared = await client.delete(URL, headers=headers)
        assert cleared.status_code == 204 and not cleared.content
    assert (await client.get(URL, headers=headers)).json() == {"id": cart_id, "user_id": user_id, "items": []}
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(CartModel)) == 2
        assert await db.scalar(select(func.count()).select_from(CartItemModel)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("movie_id,expected", [(999, 404), (4, 404), (3, 409)])
async def test_unavailable_movie_cannot_be_added(cart_api, movie_id, expected):
    client, _, _, _, headers, _ = cart_api
    response = await client.post(URL + "items/", headers=headers, json={"movie_id": movie_id})
    assert response.status_code == expected
    assert (await client.get(URL, headers=headers)).json()["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("order_status,payment_status,owner,expected", [
    (OrderStatusEnum.PAID, None, "self", 409),
    (OrderStatusEnum.PENDING, PaymentStatusEnum.SUCCESSFUL, "self", 409),
    (OrderStatusEnum.CANCELED, None, "self", 201),
    (OrderStatusEnum.PENDING, None, "self", 201),
    (OrderStatusEnum.CANCELED, PaymentStatusEnum.CANCELED, "self", 201),
    (OrderStatusEnum.PAID, None, "other", 201),
])
async def test_purchase_check_is_user_specific(cart_api, order_status, payment_status, owner, expected):
    client, sessions, user_id, other_id, headers, _ = cart_api
    await seed_order(sessions, user_id if owner == "self" else other_id, [1], order_status, payment_status)
    response = await client.post(URL + "items/", headers=headers, json={"movie_id": 1})
    assert response.status_code == expected
    if expected == 409:
        assert "already purchased" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {}, {"movie_id": 0}, {"movie_id": -1}, {"movie_id": True},
    {"movie_id": "1"}, {"movie_id": 2**31}, {"movie_id": 1, "user_id": 2},
])
async def test_cart_validates_input(cart_api, payload):
    client, _, _, _, headers, _ = cart_api
    assert (await client.post(URL + "items/", headers=headers, json=payload)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("GET", ""), ("POST", "items/"), ("DELETE", "items/1/"),
    ("DELETE", ""), ("POST", "checkout/"), ("GET", "users/1/"),
])
@pytest.mark.parametrize("inactive", [False, True])
async def test_cart_requires_active_authentication(cart_api, method, path, inactive):
    client, sessions, user_id, _, headers, _ = cart_api
    if inactive:
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            user.is_active = False
            await db.commit()
    response = await client.request(method, URL + path, headers=headers if inactive else {}, json={"movie_id": 1})
    assert response.status_code == (403 if inactive else 401)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [
    (UserGroupEnum.USER, 403), (UserGroupEnum.MODERATOR, 403), (UserGroupEnum.ADMIN, 200),
])
async def test_only_admin_can_view_other_carts(cart_api, role, expected):
    client, sessions, user_id, other_id, headers, other_headers = cart_api
    await client.post(URL + "items/", headers=other_headers, json={"movie_id": 1})
    async with sessions() as db:
        if role != UserGroupEnum.USER:
            group = UserGroupModel(name=role)
            db.add(group)
            await db.flush()
            user = await db.get(UserModel, user_id)
            user.group_id = group.id
        await db.commit()
    response = await client.get(URL + f"users/{other_id}/", headers=headers)
    assert response.status_code == expected
    if expected == 200:
        assert response.json()["user_id"] == other_id
        assert len(response.json()["items"]) == 1
        assert (await client.get(URL + "users/9999/", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_unavailable_items_are_visible_and_removable(cart_api):
    client, sessions, _, _, headers, _ = cart_api
    await client.post(URL + "items/", headers=headers, json={"movie_id": 1})
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.is_deleted = True
        await db.commit()
    item = (await client.get(URL, headers=headers)).json()["items"][0]
    assert item["movie"]["is_available_for_purchase"] is False
    assert (await client.delete(URL + "items/1/", headers=headers)).status_code == 204


@pytest.mark.asyncio
async def test_checkout_creates_snapshot_and_keeps_cart_until_payment(cart_api):
    client, sessions, user_id, _, headers, _ = cart_api
    for movie_id in (1, 2, 5):
        assert (await client.post(URL + "items/", headers=headers, json={"movie_id": movie_id})).status_code == 201
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.price = Decimal("11.25")
        await db.commit()
    response = await client.post(URL + "checkout/", headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["excluded_items"] == []
    assert data["order"]["status"] == "pending"
    assert data["order"]["total_amount"] == "13.40"
    assert data["order"]["user_id"] == user_id
    assert len(data["order"]["items"]) == 3
    assert len((await client.get(URL, headers=headers)).json()["items"]) == 3
    assert (await client.post(URL + "checkout/", headers=headers)).status_code == 409
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(OrderModel)) == 1
        assert await db.scalar(select(func.count()).select_from(PaymentModel)) == 0
        movie = await db.get(MovieModel, 1)
        movie.price = Decimal("99")
        await db.commit()
    async with sessions() as db:
        price = await db.scalar(select(OrderItemModel.price_at_order).where(OrderItemModel.movie_id == 1))
        assert price == Decimal("11.25")


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_valid", [True, False])
async def test_checkout_excludes_purchased_and_unavailable_movies(cart_api, keep_valid):
    client, sessions, user_id, _, headers, _ = cart_api
    for movie_id in ([1, 2, 5] if keep_valid else [1, 2]):
        await client.post(URL + "items/", headers=headers, json={"movie_id": movie_id})
    await seed_order(sessions, user_id, [1])
    async with sessions() as db:
        movie = await db.get(MovieModel, 2)
        movie.price = None
        await db.commit()
    response = await client.post(URL + "checkout/", headers=headers)
    assert response.status_code == (201 if keep_valid else 200), response.text
    body = response.json()
    assert body["excluded_items"] == [
        {"movie_id": 1, "reason": "Movie has already been purchased"},
        {"movie_id": 2, "reason": "Movie is not available for purchase"},
    ]
    if keep_valid:
        assert body["order"]["total_amount"] == "2.15"
    else:
        assert body["order"] is None
    assert len((await client.get(URL, headers=headers)).json()["items"]) == (1 if keep_valid else 0)


@pytest.mark.asyncio
async def test_empty_checkout_does_not_create_order(cart_api):
    client, sessions, _, _, headers, _ = cart_api
    assert (await client.post(URL + "checkout/", headers=headers)).status_code == 400
    async with sessions() as db:
        assert await db.scalar(select(OrderModel)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add", "remove", "clear", "checkout"])
async def test_cart_commit_failure_rolls_back(cart_api, monkeypatch, operation):
    client, sessions, _, _, headers, _ = cart_api
    await client.post(URL + "items/", headers=headers, json={"movie_id": 1})

    async def fail_commit(self):
        await self.db.flush()
        raise OperationalError("private", {}, Exception())

    repository = OrderRepository if operation == "checkout" else CartRepository
    monkeypatch.setattr(repository, "commit", fail_commit)
    method, path, payload = {
        "add": ("POST", "items/", {"movie_id": 2}),
        "remove": ("DELETE", "items/1/", None),
        "clear": ("DELETE", "", None),
        "checkout": ("POST", "checkout/", None),
    }[operation]
    response = await client.request(method, URL + path, headers=headers, json=payload)
    assert response.status_code == 503
    assert "private" not in response.text
    async with sessions() as db:
        assert list((await db.scalars(select(CartItemModel.movie_id))).all()) == [1]
        assert await db.scalar(select(OrderModel)) is None


@pytest.mark.asyncio
async def test_cart_query_failure(cart_api, monkeypatch):
    client, _, _, _, headers, _ = cart_api
    monkeypatch.setattr(CartRepository, "get_cart", AsyncMock(side_effect=OperationalError("private", {}, Exception())))
    response = await client.get(URL, headers=headers)
    assert response.status_code == 503
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_cart_unique_conflict_returns_409(cart_api, monkeypatch):
    client, _, _, _, headers, _ = cart_api
    monkeypatch.setattr(CartRepository, "add_item", AsyncMock(side_effect=IntegrityError("private", {}, Exception())))
    response = await client.post(URL + "items/", headers=headers, json={"movie_id": 1})
    assert response.status_code == 409
    assert "private" not in response.text


def test_cart_dependencies_share_session():
    db = AsyncMock()
    service = get_cart_service(db=db)
    assert service.repository.db is db
    assert service.movie_repository.db is db
    assert service.order_repository.db is db
    assert isinstance(service.order_repository, OrderRepository)
    orders = get_order_service(db=db)
    assert orders.repository.db is db
    assert orders.cart_repository.db is db
    assert orders.movie_repository.db is db


def test_cart_openapi_contract():
    paths = app.openapi()["paths"]
    for path, methods in {
        URL: {"get", "delete"}, URL + "items/": {"post"},
        URL + "items/{movie_id}/": {"delete"}, URL + "users/{user_id}/": {"get"},
        URL + "checkout/": {"post"},
    }.items():
        assert set(paths[path]) == methods
        for method in methods:
            assert paths[path][method]["security"] == [{"HTTPBearer": []}]
            assert paths[path][method]["description"]


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["self", "other", "canceled"])
async def test_checkout_pending_overlap_and_exclusion_rollback(cart_api, target):
    client, sessions, user_id, other_id, headers, _ = cart_api
    for movie_id in (1, 2):
        await client.post(URL + "items/", headers=headers, json={"movie_id": movie_id})
    await seed_order(sessions, user_id, [1])
    await seed_order(
        sessions, other_id if target == "other" else user_id, [2],
        OrderStatusEnum.CANCELED if target == "canceled" else OrderStatusEnum.PENDING,
    )
    response = await client.post(URL + "checkout/", headers=headers)
    assert response.status_code == (409 if target == "self" else 201)
    # A rejected checkout must not partially remove the purchased item either.
    items = (await client.get(URL, headers=headers)).json()["items"]
    assert len(items) == (2 if target == "self" else 1)


@pytest.mark.asyncio
async def test_checkout_rejects_excessive_total(cart_api):
    client, sessions, _, _, headers, _ = cart_api
    for movie_id in (1, 2):
        await client.post(URL + "items/", headers=headers, json={"movie_id": movie_id})
    async with sessions() as db:
        for movie_id in (1, 2):
            movie = await db.get(MovieModel, movie_id)
            movie.price = Decimal("99999999.99")
        await db.commit()
    response = await client.post(URL + "checkout/", headers=headers)
    assert response.status_code == 409
    async with sessions() as db:
        assert await db.scalar(select(OrderModel)) is None


@pytest.mark.asyncio
async def test_checkout_excludes_deleted_movie(cart_api):
    client, sessions, _, _, headers, _ = cart_api
    await client.post(URL + "items/", headers=headers, json={"movie_id": 1})
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.is_deleted = True
        await db.commit()
    response = await client.post(URL + "checkout/", headers=headers)
    assert response.status_code == 200
    assert response.json()["order"] is None
    assert response.json()["excluded_items"][0]["movie_id"] == 1


@pytest.mark.asyncio
async def test_missing_cart_does_not_create_another_cart_on_read(cart_api):
    client, sessions, user_id, _, headers, _ = cart_api
    async with sessions() as db:
        cart = await db.scalar(select(CartModel).where(CartModel.user_id == user_id))
        await db.delete(cart)
        await db.commit()
    assert (await client.get(URL, headers=headers)).status_code == 404
    async with sessions() as db:
        assert await db.scalar(select(CartModel).where(CartModel.user_id == user_id)) is None


@pytest.mark.asyncio
async def test_failed_exclusion_rolls_back_flushed_order(cart_api, monkeypatch):
    client, sessions, _, _, headers, _ = cart_api
    for movie_id in (1, 2):
        await client.post(URL + "items/", headers=headers, json={"movie_id": movie_id})
    async with sessions() as db:
        movie = await db.get(MovieModel, 2)
        movie.price = None
        await db.commit()

    original_remove = CartRepository.remove_items

    async def fail_after_removing(self, cart_id, movie_ids):
        # The order has been flushed but not committed yet.
        assert await self.db.scalar(select(OrderModel)) is not None
        await original_remove(self, cart_id, movie_ids)
        raise OperationalError("private", {}, Exception())

    monkeypatch.setattr(CartRepository, "remove_items", fail_after_removing)
    response = await client.post(URL + "checkout/", headers=headers)
    assert response.status_code == 503
    async with sessions() as db:
        assert await db.scalar(select(OrderModel)) is None
        assert await db.scalar(select(OrderItemModel)) is None
        assert set((await db.scalars(select(CartItemModel.movie_id))).all()) == {1, 2}


@pytest.mark.asyncio
async def test_excluding_items_does_not_change_another_users_cart(cart_api):
    client, sessions, _, _, headers, other_headers = cart_api
    for auth in (headers, other_headers):
        await client.post(URL + "items/", headers=auth, json={"movie_id": 1})
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.price = None
        await db.commit()
    assert (await client.post(URL + "checkout/", headers=headers)).status_code == 200
    assert (await client.get(URL, headers=headers)).json()["items"] == []
    assert len((await client.get(URL, headers=other_headers)).json()["items"]) == 1


@pytest.mark.asyncio
async def test_checkout_missing_cart_returns_404(cart_api):
    client, sessions, user_id, _, headers, _ = cart_api
    async with sessions() as db:
        cart = await db.scalar(select(CartModel).where(CartModel.user_id == user_id))
        await db.delete(cart)
        await db.commit()
    assert (await client.post(URL + "checkout/", headers=headers)).status_code == 404

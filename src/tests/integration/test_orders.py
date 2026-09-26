from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from src.database.models import (
    CartItemModel,
    CartModel,
    CertificationModel,
    MovieModel,
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
    PaymentModel,
    PaymentStatusEnum,
    UserGroupEnum,
    UserGroupModel,
    UserModel
)
from src.main import app
from src.api.dependencies import get_order_service
from src.repositories.orders import OrderRepository


URL = "/api/v1/orders/"


@pytest_asyncio.fixture
async def orders_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(
            email="other@example.com",
            group_id=user.group_id,
            _hashed_password="unused",
            is_active=True
        )
        admin_group = UserGroupModel(name=UserGroupEnum.ADMIN)
        moderator_group = UserGroupModel(name=UserGroupEnum.MODERATOR)
        db.add_all([other, admin_group, moderator_group])
        await db.flush()
        admin = UserModel(
            email="admin@example.com",
            group_id=admin_group.id,
            _hashed_password="unused",
            is_active=True
        )
        moderator = UserModel(
            email="mod@example.com",
            group_id=moderator_group.id,
            _hashed_password="unused",
            is_active=True
        )
        db.add_all([admin, moderator])
        movie = MovieModel(
            id=1,
            name="Movie",
            year=2020,
            time=90,
            imdb=8,
            votes=5,
            description="Story",
            price=Decimal("20"),
            certification=CertificationModel(name="PG")
        )
        db.add(movie)
        cart = CartModel(user_id=user_id, items=[CartItemModel(movie=movie)])
        db.add(cart)
        for order_id, owner, order_status, date in [
            (1, user_id, OrderStatusEnum.PENDING, "2030-01-01T00:00:00"),
            (2, user_id, OrderStatusEnum.PAID, "2030-01-02T23:59:59.999999"),
            (3, user_id, OrderStatusEnum.CANCELED, "2030-01-03T00:00:00"),
            (4, other.id, OrderStatusEnum.PENDING, "2030-01-03T00:00:00")
        ]:
            db.add(
                OrderModel(
                    id=order_id,
                    user_id=owner,
                    status=order_status,
                    created_at=datetime.fromisoformat(date).replace(
                        tzinfo=timezone.utc
                    ),
                    total_amount=Decimal("1.25"),
                    items=[OrderItemModel(movie=movie, price_at_order=Decimal("1.25"))]
                )
            )
        await db.commit()
        headers = {
            role: {"Authorization": f"Bearer {manager.create_access_token(account_id)}"}
            for role, account_id in [
                ("user", user_id),
                ("other", other.id),
                ("admin", admin.id),
                ("moderator", moderator.id)
            ]
        }
    return client, sessions, user_id, other.id, headers


@pytest.mark.asyncio
async def test_own_orders_are_paginated_and_private(orders_api):
    client, _, user_id, _, headers = orders_api
    result = await client.get(
        URL, headers=headers["user"], params={"page": 1, "per_page": 2}
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["total"] == 3
    assert [order["id"] for order in body["items"]] == [3, 2]
    for order in body["items"]:
        assert order["user_id"] == user_id
        assert order["created_at"]
        assert order["total_amount"] == "1.25"
        assert order["items"][0]["price_at_order"] == "1.25"
    page2 = await client.get(
        URL, headers=headers["user"], params={"page": 2, "per_page": 2}
    )
    assert [order["id"] for order in page2.json()["items"]] == [1]
    assert (await client.get(URL, headers=headers["admin"])).json()["items"] == []
    assert (await client.get(URL, headers=headers["user"], params={"page": 99})).json()[
        "items"
    ] == []


@pytest.mark.asyncio
async def test_detail_preserves_history_for_deleted_movie(orders_api):
    client, sessions, _, _, headers = orders_api
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        movie.is_deleted = True
        await db.commit()
    response = await client.get(URL + "1/", headers=headers["user"])
    assert response.status_code == 200
    assert response.json()["items"][0]["movie"]["name"] == "Movie"
    assert response.json()["items"][0]["price_at_order"] == "1.25"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "4/"),
        ("PATCH", "4/cancel/"),
        ("GET", "999/"),
        ("PATCH", "999/cancel/")
    ]
)
async def test_other_and_missing_orders_return_same_404(orders_api, method, path):
    client, _, _, _, headers = orders_api
    response = await client.request(method, URL + path, headers=headers["user"])
    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}


@pytest.mark.asyncio
async def test_cancel_preserves_items_and_cart_and_can_order_again(orders_api):
    client, sessions, _, _, headers = orders_api
    # Remove the paid-order fixture from this scenario:
    # this movie must not be purchased.
    async with sessions() as db:
        order = await db.get(OrderModel, 2)
        order.status = OrderStatusEnum.CANCELED
        await db.commit()
    before = (await client.get(URL + "1/", headers=headers["user"])).json()
    response = await client.patch(URL + "1/cancel/", headers=headers["user"])
    assert response.status_code == 200, response.text
    assert response.json() == {**before, "status": "canceled"}
    assert (
        await client.patch(URL + "1/cancel/", headers=headers["user"])
    ).status_code == 409
    cart = await client.get("/api/v1/cart/", headers=headers["user"])
    assert len(cart.json()["items"]) == 1
    assert (
        await client.post("/api/v1/cart/checkout/", headers=headers["user"])
    ).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("order_id", [2, 3])
async def test_only_pending_order_can_be_canceled(orders_api, order_id):
    client, _, _, _, headers = orders_api
    before = (await client.get(URL + f"{order_id}/", headers=headers["user"])).json()
    response = await client.patch(URL + f"{order_id}/cancel/", headers=headers["user"])
    assert response.status_code == 409
    assert (
        await client.get(URL + f"{order_id}/", headers=headers["user"])
    ).json() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payment_status,expected",
    [
        (PaymentStatusEnum.SUCCESSFUL, 409),
        (PaymentStatusEnum.REFUNDED, 409),
        (PaymentStatusEnum.CANCELED, 200)
    ]
)
async def test_payment_record_prevents_cancellation_even_if_order_status_is_stale(
        orders_api, payment_status, expected
):
    client, sessions, user_id, _, headers = orders_api
    async with sessions() as db:
        db.add(
            PaymentModel(
                user_id=user_id,
                order_id=1,
                status=payment_status,
                amount=Decimal("1.25")
            )
        )
        await db.commit()
    response = await client.patch(URL + "1/cancel/", headers=headers["user"])
    assert response.status_code == expected
    async with sessions() as db:
        assert (await db.scalar(select(PaymentModel))).status == payment_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params,ids",
    [
        ({}, [4, 3, 2, 1]),
        ({"status": "pending"}, [4, 1]),
        ({"status": "paid"}, [2]),
        ({"status": "canceled"}, [3]),
        ({"date_from": "2030-01-02", "date_to": "2030-01-02"}, [2]),
        ({"date_from": "2030-01-03"}, [4, 3]),
        ({"date_to": "2030-01-01"}, [1]),
        ({"date_from": "2031-01-01"}, []),
        ({"user_id": 9999}, []),
        ({"date_to": "9999-12-31"}, [4, 3, 2, 1])
    ]
)
async def test_admin_order_filters(orders_api, params, ids):
    client, _, _, _, headers = orders_api
    response = await client.get(URL + "admin/", headers=headers["admin"], params=params)
    assert response.status_code == 200, response.text
    assert [order["id"] for order in response.json()["items"]] == ids
    assert response.json()["total"] == len(ids)


@pytest.mark.asyncio
async def test_admin_combines_filters_and_pagination(orders_api):
    client, _, user_id, _, headers = orders_api
    result = await client.get(
        URL + "admin/",
        headers=headers["admin"],
        params={
            "user_id": user_id,
            "date_from": "2030-01-01",
            "date_to": "2030-01-03",
            "per_page": 1,
            "page": 2
        }
    )
    assert result.status_code == 200
    assert result.json()["total"] == 3
    assert result.json()["items"][0]["id"] == 2
    result = await client.get(
        URL + "admin/",
        headers=headers["admin"],
        params={
            "user_id": user_id,
            "status": "pending",
            "date_from": "2030-01-02"
        }
    )
    assert result.json()["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "moderator"])
async def test_admin_list_rejects_other_roles(orders_api, role):
    client, _, _, _, headers = orders_api
    assert (await client.get(URL + "admin/", headers=headers[role])).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", ""),
        ("GET", "admin/"),
        ("GET", "1/"),
        ("PATCH", "1/cancel/")
    ]
)
@pytest.mark.parametrize("inactive", [False, True])
async def test_orders_require_active_authentication(orders_api, method, path, inactive):
    client, sessions, user_id, _, headers = orders_api
    if inactive:
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            user.is_active = False
            await db.commit()
    response = await client.request(
        method, URL + path, headers=headers["user"] if inactive else {}
    )
    assert response.status_code == (403 if inactive else 401)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "2030-02-01", "date_to": "2030-01-01"},
        {"date_to": "invalid"},
        {"user_id": 0},
        {"user_id": 2**31},
        {"status": "invalid"},
        {"page": 0},
        {"per_page": 101},
        {"extra": 1}
    ]
)
async def test_admin_filter_validation(orders_api, params):
    client, _, _, _, headers = orders_api
    assert (
        await client.get(URL + "admin/", headers=headers["admin"], params=params)
    ).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"per_page": 0},
        {"per_page": 101},
        {"user_id": 2},
        {"status": "paid"}
    ]
)
async def test_own_list_cannot_override_owner(orders_api, params):
    client, _, _, _, headers = orders_api
    assert (
        await client.get(URL, headers=headers["user"], params=params)
    ).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("order_id", ["0", "-1", "invalid", str(2**31)])
async def test_order_path_validation(orders_api, order_id):
    client, _, _, _, headers = orders_api
    assert (
        await client.get(URL + order_id + "/", headers=headers["user"])
    ).status_code == 422


@pytest.mark.asyncio
async def test_cancel_commit_failure_rolls_back(orders_api, monkeypatch):
    client, sessions, _, _, headers = orders_api

    async def fail_commit(self):
        await self.db.flush()
        raise OperationalError("private", {}, Exception())

    monkeypatch.setattr(OrderRepository, "commit", fail_commit)
    response = await client.patch(URL + "1/cancel/", headers=headers["user"])
    assert response.status_code == 503
    assert "private" not in response.text
    async with sessions() as db:
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.PENDING


@pytest.mark.asyncio
@pytest.mark.parametrize("path,method", [("", "list_orders"), ("1/", "get_order")])
async def test_order_read_failure_is_safe(orders_api, monkeypatch, path, method):
    client, _, _, _, headers = orders_api
    monkeypatch.setattr(
        OrderRepository,
        method,
        AsyncMock(side_effect=OperationalError("private", {}, Exception()))
    )
    response = await client.get(URL + path, headers=headers["user"])
    assert response.status_code == 503
    assert "private" not in response.text


def test_orders_openapi_contract():
    paths = app.openapi()["paths"]
    for suffix, method in [
        ("", "get"),
        ("admin/", "get"),
        ("{order_id}/", "get"),
        ("{order_id}/cancel/", "patch")
    ]:
        operation = paths[URL + suffix][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["description"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "free",
        "paid",
        "canceled",
        "payment",
        "empty",
        "purchased",
        "deleted",
        "unpriced",
        "price",
        "total"
    ]
)
async def test_pre_payment_validation_preserves_snapshots(orders_api, case):
    _, sessions, user_id, _, _ = orders_api
    async with sessions() as db:
        paid_order = await db.get(OrderModel, 2)
        paid_order.status = OrderStatusEnum.CANCELED
        movie = await db.get(MovieModel, 1)
        movie.price = Decimal("1.25")
        order = await OrderRepository(db).get_order(1, user_id)
        if case == "paid":
            order.status = OrderStatusEnum.PAID
        elif case == "canceled":
            order.status = OrderStatusEnum.CANCELED
        elif case == "payment":
            db.add(PaymentModel(user_id=user_id, order_id=1, amount=Decimal("1.25")))
        elif case == "empty":
            order.items.clear()
        elif case == "purchased":
            paid_order.status = OrderStatusEnum.PAID
        elif case == "deleted":
            movie.is_deleted = True
        elif case == "unpriced":
            movie.price = None
        elif case == "price":
            movie.price = Decimal("2.00")
        elif case == "total":
            order.total_amount = Decimal("0.50")
        elif case == "free":
            movie.price = Decimal("0")
            order.items[0].price_at_order = Decimal("0")
            order.total_amount = Decimal("0")
        await db.commit()
    async with sessions() as db:
        service = get_order_service(db=db)
        if case in {"valid", "free"}:
            order = await service.prepare_for_payment(user_id, 1)
            assert order.status == OrderStatusEnum.PENDING
            assert order.total_amount == (
                Decimal("0") if case == "free" else Decimal("1.25")
            )
            assert (
                db.in_transaction()
            )  # The payment caller still owns this transaction.
        else:
            with pytest.raises(HTTPException) as error:
                await service.prepare_for_payment(user_id, 1)
            assert error.value.status_code == 409
        await db.rollback()
    async with sessions() as db:
        item = await db.scalar(
            select(OrderItemModel).where(OrderItemModel.order_id == 1)
        )
        if case != "empty":
            assert item.price_at_order == (
                Decimal("0") if case == "free" else Decimal("1.25")
            )

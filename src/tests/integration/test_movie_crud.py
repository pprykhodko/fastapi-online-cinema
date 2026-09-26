from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api.dependencies import get_movie_service
from src.database.models import (
    CartItemModel, CartModel, CertificationModel, DirectorModel, GenreModel,
    MovieModel, OrderItemModel, OrderModel, OrderStatusEnum, PaymentModel,
    PaymentStatusEnum, StarModel, UserGroupModel, UserGroupEnum, UserModel
)
from src.main import app
from src.services.movies import MovieService
from src.repositories.movies import MovieRepository


URL = "/api/v1/movies/"


@pytest.fixture
def movie_data():
    return {
        "name": "Interstellar", "year": 2014, "time": 169, "imdb": 8.7,
        "votes": 100, "description": "Space adventure", "price": "9.99",
        "certification_id": 1, "genre_ids": [1], "star_ids": [1],
        "director_ids": [1], "meta_score": 74, "gross": 1000
    }


@pytest_asyncio.fixture
async def movies_api(login_api):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        group = await db.get(UserGroupModel, user.group_id)
        group.name = UserGroupEnum.MODERATOR
        certification = CertificationModel(id=1, name="PG-13")
        genre = GenreModel(id=1, name="Drama")
        star = StarModel(id=1, name="Matthew McConaughey")
        director = DirectorModel(id=1, name="Christopher Nolan")
        db.add_all([certification, genre, star, director])
        db.add(MovieModel(
            id=1, name="Existing", year=2020, time=90, imdb=7, votes=5,
            description="Story", price=Decimal("5"),
            certification=certification, genres=[genre], stars=[star],
            directors=[director]
        ))
        await db.commit()
    headers = {
        "Authorization": f"Bearer {manager.create_access_token(user_id)}"
    }
    return client, sessions, user_id, headers


@pytest.mark.asyncio
async def test_movie_crud(movies_api, movie_data):
    client, sessions, _, headers = movies_api
    created = await client.post(URL, headers=headers, json=movie_data)
    assert created.status_code == 201, created.text
    data = created.json()
    movie_id = data["id"]
    path = f"{URL}{movie_id}/"
    assert data["certification"]["name"] == "PG-13"
    assert data["genres"][0]["name"] == "Drama"
    assert data["stars"][0]["id"] == 1
    assert data["directors"][0]["id"] == 1
    assert (await client.get(path)).json() == data
    update = {**movie_data, "name": "Updated", "price": None}
    for field in ("genre_ids", "star_ids", "director_ids", "meta_score",
                  "gross"):
        update.pop(field)
    response = await client.put(path, headers=headers, json=update)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["uuid"] == data["uuid"]
    assert updated["genres"] == updated["stars"] == updated["directors"] == []
    assert updated["gross"] is updated["meta_score"] is None
    assert updated["is_available_for_purchase"] is False
    assert (await client.delete(path, headers=headers)).status_code == 204
    assert (await client.get(path)).status_code == 404
    missing = await client.put(path, headers=headers, json=update)
    assert missing.status_code == 404
    assert (await client.delete(path, headers=headers)).status_code == 404
    listing = (await client.get(URL)).json()
    assert listing["total"] == 1
    async with sessions() as db:
        assert (await db.get(MovieModel, movie_id)).is_deleted is True


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
@pytest.mark.parametrize("role", [None, "user", "moderator", "admin"])
async def test_movie_write_permissions(movies_api, movie_data, method, role):
    client, sessions, user_id, headers = movies_api
    if role is None:
        headers = {}
    else:
        async with sessions() as db:
            user = await db.get(UserModel, user_id)
            group = await db.get(UserGroupModel, user.group_id)
            group.name = UserGroupEnum(role)
            await db.commit()
    response = await client.request(
        method, URL if method == "POST" else URL + "1/", headers=headers,
        **({"json": movie_data} if method != "DELETE" else {})
    )
    expected = 401 if role is None else 403 if role == "user" else {
        "POST": 201, "PUT": 200, "DELETE": 204
    }[method]
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("field, value", [
    ("certification_id", 999), ("genre_ids", [999]), ("star_ids", [999]),
    ("director_ids", [999]), ("genre_ids", [1, 1]), ("genre_ids", [-1]),
    ("name", ""), ("imdb", 11), ("time", 0), ("price", "-1"),
    ("is_deleted", True)
])
async def test_invalid_movie_is_not_saved(
        movies_api, movie_data, method, field, value
):
    client, _, _, headers = movies_api
    before = (await client.get(URL + "1/")).json()
    response = await client.request(
        method, URL if method == "POST" else URL + "1/", headers=headers,
        json={**movie_data, field: value}
    )
    assert response.status_code == 422
    assert (await client.get(URL + "1/")).json() == before
    assert (await client.get(URL)).json()["total"] == 1


@pytest.mark.asyncio
async def test_duplicate_movie_rolls_back(movies_api, movie_data):
    client, _, _, headers = movies_api
    created = await client.post(URL, headers=headers, json=movie_data)
    assert created.status_code == 201
    duplicate = await client.post(URL, headers=headers, json=movie_data)
    assert duplicate.status_code == 409
    response = await client.put(URL + "1/", headers=headers, json=movie_data)
    assert response.status_code == 409
    assert (await client.get(URL + "1/")).json()["name"] == "Existing"


@pytest.mark.asyncio
async def test_cart_warning_and_confirmation(movies_api):
    client, sessions, user_id, headers = movies_api
    async with sessions() as db:
        cart = CartModel(user_id=user_id)
        cart.items = [CartItemModel(movie_id=1)]
        db.add(cart)
        await db.commit()
    response = await client.delete(URL + "1/", headers=headers)
    assert response.status_code == 409
    assert "confirm=true" in response.json()["detail"]
    assert (await client.get(URL + "1/")).status_code == 200
    async with sessions() as db:
        assert await db.scalar(select(CartItemModel.id)) is not None
    response = await client.delete(
        URL + "1/", headers=headers, params={"confirm": True}
    )
    assert response.status_code == 204
    async with sessions() as db:
        assert await db.scalar(select(CartItemModel.id)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("order_status, payment_status, expected", [
    ("paid", None, 409), ("pending", "successful", 409),
    ("canceled", "refunded", 409), ("pending", None, 204),
    ("canceled", "canceled", 204)
])
async def test_purchase_blocks_deletion(
        movies_api, order_status, payment_status, expected
):
    client, sessions, user_id, headers = movies_api
    async with sessions() as db:
        order = OrderModel(
            user_id=user_id, status=OrderStatusEnum(order_status)
        )
        order.items = [OrderItemModel(movie_id=1, price_at_order=Decimal("5"))]
        db.add(order)
        await db.flush()
        if payment_status:
            db.add(PaymentModel(
                user_id=user_id, order_id=order.id, amount=Decimal("5"),
                status=PaymentStatusEnum(payment_status)
            ))
        await db.commit()
    response = await client.delete(
        URL + "1/", headers=headers, params={"confirm": True}
    )
    assert response.status_code == expected
    async with sessions() as db:
        assert (await db.get(MovieModel, 1)).is_deleted == (expected == 204)
        item = await db.scalar(select(OrderItemModel))
        assert item.price_at_order == Decimal("5")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("movie_id, expected", [(999, 404), (0, 422)])
async def test_missing_movie(
        movies_api, movie_data, method, movie_id, expected
):
    client, _, _, headers = movies_api
    response = await client.request(
        method, f"{URL}{movie_id}/", headers=headers,
        **({"json": movie_data} if method == "PUT" else {})
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("method, failure", [
    ("GET", "get_movie"), ("POST", "get_relations"),
    ("DELETE", "get_movie")
])
async def test_database_errors(movies_api, movie_data, monkeypatch,
                               method, failure):
    client, _, _, headers = movies_api
    repository = AsyncMock()
    getattr(repository, failure).side_effect = SQLAlchemyError("secret")
    monkeypatch.setitem(app.dependency_overrides, get_movie_service,
                        lambda: MovieService(repository))
    response = await client.request(
        method, URL if method == "POST" else URL + "1/", headers=headers,
        **({"json": movie_data} if method == "POST" else {})
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    repository.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
async def test_failed_commit_rolls_back(
        movies_api, movie_data, monkeypatch, method
):
    client, sessions, user_id, headers = movies_api
    async with sessions() as db:
        cart = CartModel(user_id=user_id)
        cart.items = [CartItemModel(movie_id=1)]
        db.add(cart)
        await db.commit()
    before = (await client.get(URL + "1/")).json()

    async def fail_commit(self):
        await self.db.flush()
        raise SQLAlchemyError("private")

    monkeypatch.setattr(MovieRepository, "commit", fail_commit)
    response = await client.request(
        method, URL if method == "POST" else URL + "1/", headers=headers,
        params={"confirm": True} if method == "DELETE" else {},
        **({"json": movie_data} if method != "DELETE" else {})
    )
    assert response.status_code == 503
    assert (await client.get(URL + "1/")).json() == before
    assert (await client.get(URL)).json()["total"] == 1
    async with sessions() as db:
        assert await db.scalar(select(CartItemModel.id)) is not None


@pytest.mark.asyncio
async def test_price_update_preserves_order_price(movies_api, movie_data):
    client, sessions, user_id, headers = movies_api
    async with sessions() as db:
        order = OrderModel(user_id=user_id, status=OrderStatusEnum.PAID)
        order.items = [OrderItemModel(movie_id=1, price_at_order=Decimal("5"))]
        db.add(order)
        await db.commit()
    response = await client.put(URL + "1/", headers=headers, json=movie_data)
    assert response.status_code == 200
    async with sessions() as db:
        item = await db.scalar(select(OrderItemModel))
        assert item.price_at_order == Decimal("5")


def test_movie_crud_openapi():
    paths = app.openapi()["paths"]
    assert set(paths[URL]) == {"get", "post"}
    assert set(paths[URL + "{movie_id}/"]) == {"get", "put", "delete"}
    assert not paths[URL + "{movie_id}/"]["get"].get("security")
    assert paths[URL]["post"]["security"]

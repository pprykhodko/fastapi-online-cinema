import hashlib
import hmac
import json
import time
from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from src.core.config import Settings
from src.database.models import (
    CartItemModel, CartModel, CertificationModel, MovieModel, OrderItemModel, OrderModel,
    OrderStatusEnum, PaymentCheckoutModel, PaymentItemModel, PaymentModel, PaymentStatusEnum,
    UserGroupEnum, UserGroupModel, UserModel,
)
from src.main import app
from src.notifications.queue import EmailQueue, EmailQueueError, get_email_queue
from src.payments.stripe import CheckoutRejectedError, StripeGateway, get_stripe_gateway
from src.repositories.cart import CartRepository


URL = "/api/v1/payments/"


class FakeStripe(StripeGateway):
    def __init__(self):
        super().__init__(Settings(_env_file=None, STRIPE_SECRET_KEY="sk_test_example", STRIPE_WEBHOOK_SECRET="whsec_test"))
        self.sessions = {}
        self.refunds = {}
        self.create_calls = 0
        self.refund_calls = 0

    def client(self):
        return Mock()

    async def create_checkout(self, data, key):
        self.create_calls += 1
        price = data["line_items"][0]["price_data"]
        session = self.sessions.setdefault(key, {
            "id": f"cs_test_{key}", "url": f"https://checkout.stripe.com/{key}",
            "metadata": data["metadata"], "client_reference_id": data["client_reference_id"],
            "amount_total": sum(item["quantity"] * item["price_data"]["unit_amount"] for item in data["line_items"]),
            "currency": price["currency"],
            "mode": "payment", "status": "open", "payment_status": "unpaid", "payment_intent": None,
        })
        return deepcopy(session)

    async def retrieve_checkout(self, session_id):
        return deepcopy(next(session for session in self.sessions.values() if session["id"] == session_id))

    async def checkout_for_payment_intent(self, payment_intent):
        return deepcopy(next((session for session in self.sessions.values()
                              if session["payment_intent"] == payment_intent), None))

    async def expire_checkout(self, session_id):
        session = next(session for session in self.sessions.values() if session["id"] == session_id)
        session["status"] = "expired"
        return deepcopy(session)

    async def refund(self, payment_intent, amount, key):
        self.refund_calls += 1
        return self.refunds.setdefault("re_1", {
            "id": "re_1", "payment_intent": payment_intent, "amount": amount, "currency": "usd", "status": "succeeded",
        })

    async def retrieve_refund(self, refund_id):
        return deepcopy(self.refunds[refund_id])


@pytest_asyncio.fixture
async def payments_api(login_api, monkeypatch):
    client, sessions, manager, user_id = login_api
    async with sessions() as db:
        user = await db.get(UserModel, user_id)
        other = UserModel(email="other@example.com", group_id=user.group_id, _hashed_password="unused", is_active=True)
        admin_group = UserGroupModel(name=UserGroupEnum.ADMIN)
        mod_group = UserGroupModel(name=UserGroupEnum.MODERATOR)
        db.add_all([other, admin_group, mod_group])
        await db.flush()
        admin = UserModel(email="admin@example.com", group_id=admin_group.id, _hashed_password="unused", is_active=True)
        moderator = UserModel(email="mod@example.com", group_id=mod_group.id, _hashed_password="unused", is_active=True)
        certification = CertificationModel(name="PG")
        movies = [MovieModel(id=i, name=f"Movie {i}", year=2020, time=90, imdb=8, votes=5,
                            description="Story", price=Decimal("20"), certification=certification) for i in [1, 2]]
        db.add_all([admin, moderator, *movies])
        db.add(CartModel(user_id=user_id, items=[CartItemModel(movie=movie) for movie in movies]))
        db.add(OrderModel(id=1, user_id=user_id, total_amount=Decimal("20"),
                          items=[OrderItemModel(movie=movies[0], price_at_order=Decimal("20"))]))
        await db.commit()
        headers = {role: {"Authorization": f"Bearer {manager.create_access_token(account.id)}"}
                   for role, account in [("user", user), ("other", other), ("admin", admin), ("mod", moderator)]}
    gateway = FakeStripe()
    emails = AsyncMock(spec=EmailQueue)
    monkeypatch.setitem(app.dependency_overrides, get_stripe_gateway, lambda: gateway)
    monkeypatch.setitem(app.dependency_overrides, get_email_queue, lambda: emails)
    return client, sessions, headers, gateway, emails


async def post_event(client, data, kind="checkout.session.completed", **extra):
    payload = json.dumps({"id": "evt_test", "type": kind, "livemode": False, "data": {"object": data}, **extra}).encode()
    timestamp = str(int(time.time()))
    digest = hmac.new(b"whsec_test", timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
    return await client.post(URL + "webhook/", content=payload,
                             headers={"Stripe-Signature": f"t={timestamp},v1={digest}", "Content-Type": "application/json"})


async def start_payment(api):
    client, _, headers, gateway, _ = api
    response = await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    assert response.status_code == 200, response.text
    return next(iter(gateway.sessions.values()))


async def complete_payment(api):
    session = await start_payment(api)
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    response = await post_event(api[0], session)
    assert response.status_code == 200, response.text
    return session


@pytest.mark.asyncio
async def test_checkout_reuses_session_and_does_not_pay_order(payments_api):
    client, sessions, headers, gateway, _ = payments_api
    session = await start_payment(payments_api)
    second = await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    assert second.json()["checkout_url"] == session["url"]
    assert gateway.create_calls == 1
    assert (await client.get(URL, headers=headers["user"])).json()["total"] == 0
    assert (await client.get(URL + "return/", params={"session_id": session["id"]})).status_code == 200
    async with sessions() as db:
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.PENDING
        assert await db.scalar(select(func.count()).select_from(CartItemModel)) == 2


@pytest.mark.asyncio
async def test_success_is_atomic_and_duplicate_safe(payments_api):
    client, sessions, headers, _, emails = payments_api
    session = await complete_payment(payments_api)
    assert (await post_event(client, session)).status_code == 200
    # A late expired event cannot undo a completed payment.
    expired = dict(session, status="expired", payment_status="unpaid")
    assert (await post_event(client, expired, "checkout.session.expired")).status_code == 200
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(PaymentModel)) == 1
        assert await db.scalar(select(func.count()).select_from(PaymentItemModel)) == 1
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.PAID
        assert list((await db.scalars(select(CartItemModel.movie_id))).all()) == [2]
    emails.send_payment_confirmation.assert_awaited_once()
    history = (await client.get(URL, headers=headers["user"])).json()
    assert history["items"][0]["amount"] == "20.00"
    assert history["items"][0]["status"] == "successful"
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["items"][0]["id"] == 1
    assert "Payment successful" in (await client.get(URL + "return/", params={"session_id": session["id"]})).text


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("POST", "checkout/", {"order_id": 1}), ("POST", "checkout/1/cancel/", None),
    ("POST", "refund/", {"payment_id": 1}), ("GET", "1/", None),
])
async def test_other_users_cannot_access_payment(payments_api, method, path, body):
    client, _, headers, _, _ = payments_api
    await complete_payment(payments_api)
    for role in ["other", "admin", "mod"]:
        response = await client.request(method, URL + path, json=body, headers=headers[role])
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path,method", [("", "GET"), ("admin/", "GET"), ("purchased/", "GET"), ("checkout/", "POST"), ("refund/", "POST")])
async def test_authentication_required(payments_api, path, method):
    assert (await payments_api[0].request(method, URL + path, json={"order_id": 1})).status_code == 401


@pytest.mark.asyncio
async def test_admin_filters_and_private_history(payments_api):
    client, _, headers, _, _ = payments_api
    await complete_payment(payments_api)
    assert (await client.get(URL, headers=headers["other"])).json()["total"] == 0
    for role in ["user", "mod"]:
        assert (await client.get(URL + "admin/", headers=headers[role])).status_code == 403
    for filters, total in [({}, 1), ({"status": "refunded"}, 0), ({"date_to": "2000-01-01"}, 0),
                           ({"date_from": "2099-01-01"}, 0), ({"user_id": 999}, 0), ({"page": 20}, 1)]:
        result = await client.get(URL + "admin/", headers=headers["admin"], params=filters)
        assert result.status_code == 200, result.text
        assert result.json()["total"] == total


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"page": 0}, {"per_page": 101}, {"status": "pending"},
                                   {"page": 10**30}, {"user_id": 10**30},
                                   {"date_from": "2030-02-01", "date_to": "2030-01-01"}])
async def test_invalid_filters(payments_api, params):
    assert (await payments_api[0].get(URL + "admin/", headers=payments_api[2]["admin"], params=params)).status_code == 422


@pytest.mark.asyncio
async def test_cancel_expires_session_and_preserves_cart(payments_api):
    client, sessions, headers, _, emails = payments_api
    session = await start_payment(payments_api)
    assert (await client.patch("/api/v1/orders/1/cancel/", headers=headers["user"])).status_code == 409
    for _ in range(2):
        assert (await client.post(URL + "checkout/1/cancel/", headers=headers["user"])).status_code == 200
    assert (await post_event(client, session, "checkout.session.expired")).status_code == 200
    async with sessions() as db:
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.CANCELED
        assert await db.scalar(select(func.count()).select_from(CartItemModel)) == 2
        assert await db.scalar(select(func.count()).select_from(PaymentModel)) == 1
    assert (await client.get(URL, headers=headers["user"])).json()["items"][0]["status"] == "canceled"
    emails.send_payment_confirmation.assert_not_awaited()


@pytest.mark.asyncio
async def test_cannot_cancel_completed_or_pay_again(payments_api):
    await complete_payment(payments_api)
    client, _, headers, _, _ = payments_api
    assert (await client.post(URL + "checkout/1/cancel/", headers=headers["user"])).status_code == 409
    assert (await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("amount_total", 1), ("currency", "eur"), ("client_reference_id", "2"), ("mode", "setup")])
async def test_mismatched_signed_session_does_not_fulfill(payments_api, field, value):
    session = await start_payment(payments_api)
    data = dict(session, status="complete", payment_status="paid", payment_intent="pi_test")
    data[field] = value
    assert (await post_event(payments_api[0], data)).status_code == 400
    assert (await payments_api[0].get(URL, headers=payments_api[2]["user"])).json()["total"] == 0


@pytest.mark.asyncio
async def test_unsigned_and_wrong_mode_webhooks_rejected(payments_api):
    client = payments_api[0]
    assert (await client.post(URL + "webhook/", json={})).status_code == 400
    assert (await post_event(client, {}, livemode=True)).status_code == 400
    assert (await post_event(client, {}, kind="unrelated.event")).status_code == 200
    assert (await client.post(URL + "webhook/", content=b"x" * (1024 * 1024 + 1))).status_code == 413


@pytest.mark.asyncio
async def test_full_refund_is_idempotent_and_revokes_purchase(payments_api):
    await complete_payment(payments_api)
    client, sessions, headers, gateway, _ = payments_api
    for _ in range(2):
        response = await client.post(URL + "refund/", json={"payment_id": 1}, headers=headers["user"])
        assert response.status_code == 200, response.text
    assert gateway.refund_calls == 1
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 0
    async with sessions() as db:
        assert (await db.get(PaymentModel, 1)).status == PaymentStatusEnum.REFUNDED
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.CANCELED
    # A late success notification must not resurrect refunded access.
    assert (await post_event(client, next(iter(gateway.sessions.values())))).status_code == 200
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 0
    assert (await client.post("/api/v1/cart/items/", json={"movie_id": 1}, headers=headers["user"])).status_code == 201


@pytest.mark.asyncio
async def test_pending_refund_waits_for_confirmation(payments_api):
    await complete_payment(payments_api)
    client, _, headers, gateway, _ = payments_api
    gateway.refunds["re_1"] = {"id": "re_1", "payment_intent": "pi_test", "amount": 2000,
                                "currency": "usd", "status": "pending"}
    result = await client.post(URL + "refund/", json={"payment_id": 1}, headers=headers["user"])
    assert result.json()["message"] == "Refund is processing"
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 1
    gateway.refunds["re_1"]["status"] = "succeeded"
    assert (await post_event(client, gateway.refunds["re_1"], "refund.updated")).status_code == 200
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 0


@pytest.mark.asyncio
async def test_provider_timeout_keeps_request_for_safe_retry(payments_api, monkeypatch):
    client, sessions, headers, gateway, _ = payments_api
    original = gateway.create_checkout

    async def timeout_after_creation(data, key):
        await original(data, key)
        raise HTTPException(status_code=503, detail="Timeout")

    monkeypatch.setattr(gateway, "create_checkout", timeout_after_creation)
    assert (await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])).status_code == 503
    async with sessions() as db:
        reservation = await db.scalar(select(PaymentCheckoutModel))
        assert reservation.request_key
        assert reservation.session_id is None
    monkeypatch.setattr(gateway, "create_checkout", original)
    assert (await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])).status_code == 200
    assert len(gateway.sessions) == 1


@pytest.mark.asyncio
async def test_webhook_can_recover_session_id_not_saved_after_timeout(payments_api, monkeypatch):
    client, _, headers, gateway, _ = payments_api
    original = gateway.create_checkout

    async def timeout(data, key):
        await original(data, key)
        raise HTTPException(status_code=503, detail="Timeout")

    monkeypatch.setattr(gateway, "create_checkout", timeout)
    await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    session = next(iter(gateway.sessions.values()))
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    assert (await post_event(client, session)).status_code == 200
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 1


@pytest.mark.asyncio
async def test_email_broker_outage_does_not_rollback_payment_and_retry_recovers(payments_api):
    client, sessions, headers, _, emails = payments_api
    session = await start_payment(payments_api)
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    emails.send_payment_confirmation.side_effect = EmailQueueError()
    assert (await post_event(client, session)).status_code == 503
    async with sessions() as db:
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.PAID
        assert not (await db.scalar(select(PaymentCheckoutModel))).email_queued
    emails.send_payment_confirmation.side_effect = None
    assert (await post_event(client, session)).status_code == 200
    assert (await client.get(URL, headers=headers["user"])).json()["total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["price", "unavailable", "total", "purchased"])
async def test_invalid_order_is_not_sent_to_stripe(payments_api, problem):
    client, sessions, headers, gateway, _ = payments_api
    async with sessions() as db:
        movie = await db.get(MovieModel, 1)
        if problem == "price":
            movie.price = Decimal("21")
        elif problem == "unavailable":
            movie.is_deleted = True
        elif problem == "total":
            (await db.get(OrderModel, 1)).total_amount = Decimal("10")
        else:
            db.add(OrderModel(user_id=1, status=OrderStatusEnum.PAID, total_amount=Decimal("20"),
                              items=[OrderItemModel(movie_id=1, price_at_order=Decimal("20"))]))
        await db.commit()
    result = await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    assert result.status_code == 409, result.text
    assert gateway.create_calls == 0


@pytest.mark.asyncio
async def test_webhook_rollback_preserves_order_and_cart(payments_api, monkeypatch):
    client, sessions, headers, _, emails = payments_api
    session = await start_payment(payments_api)
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    original = CartRepository.remove_items
    monkeypatch.setattr(CartRepository, "remove_items", AsyncMock(side_effect=OperationalError("query", {}, Exception())))
    assert (await post_event(client, session)).status_code == 503
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(PaymentModel)) == 0
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.PENDING
        assert await db.scalar(select(func.count()).select_from(CartItemModel)) == 2
    emails.send_payment_confirmation.assert_not_awaited()
    monkeypatch.setattr(CartRepository, "remove_items", original)
    assert (await post_event(client, session)).status_code == 200
    assert (await client.get(URL + "1/", headers=headers["user"])).json()["status"] == "successful"


@pytest.mark.asyncio
async def test_canceled_payment_cannot_be_refunded_and_page_shows_cancellation(payments_api):
    client, _, headers, _, _ = payments_api
    session = await start_payment(payments_api)
    session["status"] = "expired"
    assert (await post_event(client, session, "checkout.session.expired")).status_code == 200
    assert (await client.post(URL + "refund/", json={"payment_id": 1}, headers=headers["user"])).status_code == 409
    assert "expired" in (await client.get(URL + "return/", params={"session_id": session["id"]})).text
    assert "not confirmed" in (await client.get(URL + "return/")).text


@pytest.mark.asyncio
async def test_free_order_does_not_require_card_charge(payments_api):
    client, sessions, headers, _, _ = payments_api
    async with sessions() as db:
        (await db.get(MovieModel, 1)).price = Decimal("0")
        (await db.get(OrderModel, 1)).total_amount = Decimal("0")
        (await db.scalar(select(OrderItemModel).where(OrderItemModel.order_id == 1))).price_at_order = Decimal("0")
        await db.commit()
    session = await start_payment(payments_api)
    session.update(status="complete", payment_status="no_payment_required")
    assert (await post_event(client, session)).status_code == 200
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 1
    assert (await client.post(URL + "refund/", json={"payment_id": 1}, headers=headers["user"])).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", ["0.01", "1000000.00"])
async def test_unsupported_stripe_amount(payments_api, amount):
    client, sessions, headers, gateway, _ = payments_api
    async with sessions() as db:
        (await db.get(MovieModel, 1)).price = Decimal(amount)
        (await db.get(OrderModel, 1)).total_amount = Decimal(amount)
        (await db.scalar(select(OrderItemModel).where(OrderItemModel.order_id == 1))).price_at_order = Decimal(amount)
        await db.commit()
    assert (await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])).status_code == 409
    assert gateway.create_calls == 0


@pytest.mark.asyncio
async def test_unsigned_return_query_cannot_mark_payment_paid(payments_api):
    client, sessions, _, _, _ = payments_api
    assert "processing" in (await client.get(URL + "return/", params={"session_id": "cs_forged"})).text
    async with sessions() as db:
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.PENDING


@pytest.mark.asyncio
async def test_failed_refund_is_saved_and_not_resubmitted(payments_api):
    session = await complete_payment(payments_api)
    client, _, headers, gateway, _ = payments_api
    gateway.refunds["re_1"] = {"id": "re_1", "payment_intent": "pi_test", "amount": 2000,
                                "currency": "usd", "status": "failed"}
    for _ in range(2):
        assert (await client.post(URL + "refund/", json={"payment_id": 1}, headers=headers["user"])).status_code == 409
    assert gateway.refund_calls == 1
    assert "Payment successful" in (await client.get(URL + "return/", params={"session_id": session["id"]})).text


@pytest.mark.asyncio
async def test_refund_event_before_payment_requests_retry(payments_api):
    session = await start_payment(payments_api)
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    assert (await post_event(payments_api[0], {"id": "re_1", "payment_intent": "pi_test"}, "refund.updated")).status_code == 503
    assert (await post_event(payments_api[0], {"id": "re_1"}, "refund.updated")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("amount", 1000), ("currency", "eur"), ("payment_intent", "pi_other")])
async def test_refund_mismatch_does_not_revoke_access(payments_api, field, value):
    await complete_payment(payments_api)
    client, _, headers, gateway, _ = payments_api
    refund = {"id": "re_1", "payment_intent": "pi_test", "amount": 2000, "currency": "usd", "status": "succeeded"}
    refund[field] = value
    gateway.refunds["re_1"] = refund
    assert (await client.post(URL + "refund/", json={"payment_id": 1}, headers=headers["user"])).status_code == 409
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 1


@pytest.mark.asyncio
async def test_unrelated_checkout_events_are_ignored(payments_api):
    client = payments_api[0]
    for data in [{}, {"metadata": {"order_id": "999", "request_key": "other"}},
                 {"metadata": {"order_id": "not-an-int", "request_key": "other"}}]:
        assert (await post_event(client, data)).status_code == 200


@pytest.mark.asyncio
async def test_incomplete_payment_not_fulfilled_and_missing_intent_rejected(payments_api):
    client, _, headers, _, _ = payments_api
    session = await start_payment(payments_api)
    session["status"] = "complete"
    assert (await post_event(client, session)).status_code == 200
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 0
    session["payment_status"] = "paid"
    assert (await post_event(client, session)).status_code == 400


@pytest.mark.asyncio
async def test_database_total_tampering_after_checkout_is_rejected(payments_api):
    client, sessions, _, _, _ = payments_api
    session = await start_payment(payments_api)
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    async with sessions() as db:
        (await db.get(OrderModel, 1)).total_amount = Decimal("19")
        await db.commit()
    assert (await post_event(client, session)).status_code == 409


@pytest.mark.asyncio
async def test_expired_uncertain_request_not_recreated(payments_api, monkeypatch):
    client, sessions, headers, gateway, _ = payments_api
    monkeypatch.setattr(gateway, "create_checkout", AsyncMock(side_effect=HTTPException(status_code=503, detail="Timeout")))
    await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    async with sessions() as db:
        (await db.scalar(select(PaymentCheckoutModel))).expires_at = 1
        await db.commit()
    response = await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    assert response.status_code == 409
    assert gateway.create_checkout.await_count == 1
    assert (await client.post(URL + "checkout/1/cancel/", headers=headers["user"])).status_code == 409


@pytest.mark.asyncio
async def test_checkout_provider_completed_before_webhook_cannot_cancel(payments_api):
    client, _, headers, _, _ = payments_api
    session = await start_payment(payments_api)
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    assert (await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])).status_code == 409
    assert (await client.post(URL + "checkout/1/cancel/", headers=headers["user"])).status_code == 409


@pytest.mark.asyncio
async def test_no_checkout_to_cancel(payments_api):
    assert (await payments_api[0].post(URL + "checkout/1/cancel/", headers=payments_api[2]["user"])).status_code == 404


@pytest.mark.asyncio
async def test_refunded_return_page(payments_api):
    session = await complete_payment(payments_api)
    await payments_api[0].post(URL + "refund/", json={"payment_id": 1}, headers=payments_api[2]["user"])
    assert "Payment refunded" in (await payments_api[0].get(URL + "return/", params={"session_id": session["id"]})).text


@pytest.mark.asyncio
async def test_definite_rejection_releases_order_but_timeout_does_not(payments_api, monkeypatch):
    client, sessions, headers, gateway, _ = payments_api
    monkeypatch.setattr(gateway, "create_checkout", AsyncMock(side_effect=CheckoutRejectedError()))
    result = await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    assert result.status_code == 409
    async with sessions() as db:
        assert (await db.get(OrderModel, 1)).status == OrderStatusEnum.CANCELED
        assert (await db.scalar(select(PaymentCheckoutModel))).status == "rejected"
        assert await db.scalar(select(func.count()).select_from(CartItemModel)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("path,data", [("checkout/", {"order_id": 10**30}), ("refund/", {"payment_id": 10**30}),
                                      ("checkout/", {"order_id": 1, "amount": 1})])
async def test_client_cannot_override_amount_or_overflow_identifiers(payments_api, path, data):
    assert (await payments_api[0].post(URL + path, json=data, headers=payments_api[2]["user"])).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("paid", [True, False])
async def test_checkout_retry_recovers_missed_webhook(payments_api, paid):
    client, sessions, headers, gateway, emails = payments_api
    session = await start_payment(payments_api)
    session.update(status="complete" if paid else "expired", payment_status="paid" if paid else "unpaid",
                   payment_intent="pi_test" if paid else None)
    response = await client.post(URL + "checkout/", json={"order_id": 1}, headers=headers["user"])
    assert response.status_code == 409
    async with sessions() as db:
        assert (await db.get(OrderModel, 1)).status == (OrderStatusEnum.PAID if paid else OrderStatusEnum.CANCELED)
        assert await db.scalar(select(func.count()).select_from(PaymentModel)) == 1
        assert await db.scalar(select(func.count()).select_from(CartItemModel)) == (1 if paid else 2)
    assert gateway.create_calls == 1
    # A late webhook after reconciliation does not duplicate the payment or email.
    assert (await post_event(client, session, "checkout.session.completed" if paid else "checkout.session.expired")).status_code == 200
    assert emails.send_payment_confirmation.await_count == int(paid)


@pytest.mark.asyncio
async def test_unrelated_refund_is_acknowledged_not_retried(payments_api):
    assert (await post_event(payments_api[0], {"id": "re_other", "payment_intent": "pi_other"}, "refund.updated")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("order_id", ["0", "2147483648", "9" * 100, "²"])
async def test_foreign_metadata_cannot_overflow_order_id(payments_api, order_id):
    assert (await post_event(payments_api[0], {"metadata": {"order_id": order_id, "request_key": "other"}})).status_code == 200


@pytest.mark.asyncio
async def test_multiple_stripe_line_items_match_stored_order_total(payments_api):
    client, sessions, headers, _, _ = payments_api
    async with sessions() as db:
        order = await db.get(OrderModel, 1)
        order.total_amount = Decimal("40")
        db.add(OrderItemModel(order_id=1, movie_id=2, price_at_order=Decimal("20")))
        await db.commit()
    session = await complete_payment(payments_api)
    assert session["amount_total"] == 4000
    async with sessions() as db:
        data = (await db.scalar(select(PaymentCheckoutModel))).request_data
        assert [item["price_data"]["product_data"]["name"] for item in data["line_items"]] == ["Movie 1", "Movie 2"]
    assert (await client.get(URL + "purchased/", headers=headers["user"])).json()["total"] == 2


@pytest.mark.asyncio
async def test_preexisting_aggregated_checkout_still_validates(payments_api):
    client, sessions, _, _, _ = payments_api
    session = await start_payment(payments_api)
    async with sessions() as db:
        checkout = await db.scalar(select(PaymentCheckoutModel))
        data = deepcopy(checkout.request_data)
        data["line_items"][0]["price_data"]["product_data"]["name"] = "Online Cinema order #1"
        checkout.request_data = data
        await db.commit()
    session.update(status="complete", payment_status="paid", payment_intent="pi_test")
    assert (await post_event(client, session)).status_code == 200

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, Mock

import pytest
import stripe
from fastapi import HTTPException

from src.core.config import Settings
from src.payments.stripe import CheckoutRejectedError, StripeGateway, get_stripe_gateway


def gateway(**kwargs):
    return StripeGateway(
        Settings(_env_file=None, STRIPE_SECRET_KEY="sk_test_example", **kwargs)
    )


def test_client_and_dependency_factory():
    assert isinstance(gateway().client(), stripe.StripeClient)
    assert isinstance(get_stripe_gateway(), StripeGateway)


@pytest.mark.parametrize(
    "key,live", [("", False), ("sk_live_example", False), ("sk_test_example", True)]
)
def test_missing_or_wrong_mode_api_key(key, live):
    provider = StripeGateway(
        Settings(_env_file=None, STRIPE_SECRET_KEY=key, STRIPE_LIVE_MODE=live)
    )
    with pytest.raises(HTTPException) as error:
        provider.client()
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_sdk_calls_use_durable_idempotency_keys(monkeypatch):
    provider = gateway()
    client = Mock()
    monkeypatch.setattr(provider, "client", lambda: client)
    for endpoint in [
        client.v1.checkout.sessions.create,
        client.v1.checkout.sessions.retrieve,
        client.v1.checkout.sessions.expire,
        client.v1.refunds.create,
        client.v1.refunds.retrieve
    ]:
        endpoint.return_value.to_dict.return_value = {"id": "example"}
    assert await provider.create_checkout({"mode": "payment"}, "stable-key") == {
        "id": "example"
    }
    client.v1.checkout.sessions.create.assert_called_once_with(
        {"mode": "payment"}, options={"idempotency_key": "stable-key"}
    )
    await provider.retrieve_checkout("cs_1")
    client.v1.checkout.sessions.retrieve.assert_called_once_with("cs_1")
    await provider.expire_checkout("cs_1")
    client.v1.checkout.sessions.expire.assert_called_once_with("cs_1")
    await provider.refund("pi_1", 100, "refund-key")
    client.v1.refunds.create.assert_called_once_with(
        {"payment_intent": "pi_1", "amount": 100},
        options={"idempotency_key": "refund-key"}
    )
    await provider.retrieve_refund("re_1")
    client.v1.refunds.retrieve.assert_called_once_with("re_1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception,code",
    [
        (stripe.CardError("private provider message", "card", "card_declined"), 402),
        (stripe.APIConnectionError("private provider message"), 503),
        (stripe.AuthenticationError("private provider message"), 503),
        (stripe.InvalidRequestError("private provider message", "session"), 409)
    ]
)
async def test_provider_errors_hide_private_details(exception, code):
    with pytest.raises(HTTPException) as error:
        await gateway()._call(Mock(side_effect=exception))
    assert error.value.status_code == code
    assert "private" not in error.value.detail


@pytest.mark.asyncio
async def test_definite_checkout_rejection_is_distinct_from_timeout():
    with pytest.raises(CheckoutRejectedError):
        await gateway()._call(
            Mock(
                side_effect=stripe.InvalidRequestError(
                    "private", "payment_method_types"
                )
            ),
            creating_checkout=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [[], [{"id": "cs_test"}]])
async def test_find_checkout_for_payment_intent(monkeypatch, items):
    provider = gateway()
    client = Mock()
    client.v1.checkout.sessions.list.return_value.to_dict.return_value = {"data": items}
    monkeypatch.setattr(provider, "client", lambda: client)
    assert await provider.checkout_for_payment_intent("pi_test") == (
        items[0] if items else None
    )
    client.v1.checkout.sessions.list.assert_called_once_with(
        {"payment_intent": "pi_test", "limit": 1}
    )


def signature(payload, timestamp):
    digest = hmac.new(
        b"whsec_test", f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_signature_verification():
    provider = gateway(STRIPE_WEBHOOK_SECRET="whsec_test")
    payload = json.dumps({"id": "evt_1", "livemode": False, "type": "test"}).encode()
    assert (
        provider.verify_event(payload, signature(payload, int(time.time())))["id"]
        == "evt_1"
    )
    for body, header in [
        (payload, ""),
        (payload, signature(payload, 1)),
        (payload + b" ", signature(payload, int(time.time()))),
        (b"not json", signature(b"not json", int(time.time())))
    ]:
        with pytest.raises(HTTPException) as error:
            provider.verify_event(body, header)
        assert error.value.status_code == 400


def test_missing_webhook_secret():
    with pytest.raises(HTTPException) as error:
        gateway().verify_event(b"{}", "")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_payment_email_queue_worker_and_template(monkeypatch):
    from src.notifications.emails import EmailSender
    from src.notifications.queue import EmailQueue
    from src.tasks import emails

    publish = Mock()
    monkeypatch.setattr(emails.send_email, "apply_async", publish)
    await EmailQueue().send_payment_confirmation("user@example.com", 4, "20.00", "usd")
    assert publish.call_args.kwargs["args"] == (
        "payment",
        "user@example.com",
        {"order_id": 4, "amount": "20.00", "currency": "usd"}
    )
    sender = EmailSender(Settings(_env_file=None))
    smtp = AsyncMock()
    monkeypatch.setattr(sender, "_send_email", smtp)
    monkeypatch.setattr(emails, "get_email_sender", lambda: sender)
    await emails.deliver_email(*publish.call_args.kwargs["args"])
    args = smtp.await_args.args
    assert args[0] == "user@example.com"
    assert "#4" in args[2] and "20.00 USD" in args[2]
    assert "#4" in args[3] and "20.00 USD" in args[3]

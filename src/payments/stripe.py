from functools import partial

import stripe
from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool

from src.core.config import Settings, get_settings


class CheckoutRejectedError(Exception):
    """Stripe explicitly rejected session creation; no payment session was created."""


class StripeGateway:
    def __init__(self, settings: Settings):
        """
        Initialize StripeGateway with its required dependencies.

        Args:
            settings (Settings): Application configuration used by this component.
        """
        self.settings = settings

    def client(self) -> stripe.StripeClient:
        """
        Build a Stripe client after checking the configured test or live secret-key
        prefix.

        Returns:
            stripe.StripeClient: Configured component ready for use.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
        """
        key = self.settings.STRIPE_SECRET_KEY.get_secret_value()
        prefix = "sk_live_" if self.settings.STRIPE_LIVE_MODE else "sk_test_"

        if not key.startswith(prefix):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe is not configured"
            )

        return stripe.StripeClient(
            key,
            max_network_retries=2,
            http_client=stripe.RequestsClient(timeout=15)
        )

    async def _call(
            self,
            function,
            *args,
            creating_checkout: bool = False,
            **kwargs
    ) -> dict:
        """
        Run a Stripe SDK call in a thread and translate provider errors to application
        errors.

        Args:
            function: Stripe SDK operation to execute in the thread pool.
            creating_checkout (bool): Distinguish a rejected checkout from other invalid
                provider requests.
            args: Positional arguments forwarded to the Stripe SDK operation.
            kwargs: Keyword arguments forwarded to the Stripe SDK operation.

        Returns:
            dict: Stripe response or event data.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
            CheckoutRejectedError: Stripe explicitly rejects checkout creation.
        """
        try:
            result = await run_in_threadpool(partial(function, *args, **kwargs))
            return result.to_dict()

        except stripe.CardError:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Payment declined. Try another card or contact your bank."
            )

        except stripe.InvalidRequestError:
            if creating_checkout:
                raise CheckoutRejectedError(
                    "Stripe rejected the checkout configuration"
                )

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stripe rejected this operation. "
                       "Refresh the payment status or contact support."
            )
        except stripe.StripeError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe is temporarily unavailable. Retry the same request."
            )

    async def create_checkout(self, data: dict, key: str) -> dict:
        """
        Create a Stripe Checkout session using a stable idempotency key.

        Args:
            data (dict): Stripe checkout request parameters with line items and prices
                in cents.
            key (str): Stable checkout/refund idempotency key.

        Returns:
            dict: Stripe response or event data.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
            CheckoutRejectedError: Stripe explicitly rejects checkout creation.
        """
        return await self._call(
            self.client().v1.checkout.sessions.create,
            data,
            options={
                "idempotency_key": key
            },
            creating_checkout=True
        )

    async def retrieve_checkout(self, session_id: str) -> dict:
        """
        Fetch the current checkout session from Stripe.

        Args:
            session_id (str): Stripe Checkout session ID.

        Returns:
            dict: Stripe response or event data.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
        """
        return await self._call(
            self.client().v1.checkout.sessions.retrieve,
            session_id
        )

    async def checkout_for_payment_intent(self, payment_intent: str) -> dict | None:
        """
        Find the first Stripe checkout associated with a payment intent.

        Args:
            payment_intent (str): Stripe PaymentIntent ID.

        Returns:
            dict | None: Matching Stripe checkout, or None if not found.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
        """
        result = await self._call(
            self.client().v1.checkout.sessions.list,
            {"payment_intent": payment_intent, "limit": 1}
        )

        return result["data"][0] if result["data"] else None

    async def expire_checkout(self, session_id: str) -> dict:
        """
        Ask Stripe to expire the checkout session.

        Args:
            session_id (str): Stripe Checkout session ID.

        Returns:
            dict: Stripe response or event data.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
        """
        return await self._call(
            self.client().v1.checkout.sessions.expire,
            session_id
        )

    async def refund(self, payment_intent: str, amount: int, key: str) -> dict:
        """
        Ask Stripe for a refund using the amount in cents and a stable idempotency key.

        Args:
            payment_intent (str): Stripe PaymentIntent ID.
            amount (int): Refund amount in the smallest currency unit (cents).
            key (str): Stable checkout/refund idempotency key.

        Returns:
            dict: Stripe response or event data.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
        """
        return await self._call(
            self.client().v1.refunds.create,
            {"payment_intent": payment_intent, "amount": amount},
            options={"idempotency_key": key}
        )

    async def retrieve_refund(self, refund_id: str) -> dict:
        """
        Fetch the current refund state from Stripe.

        Args:
            refund_id (str): Stripe refund ID.

        Returns:
            dict: Stripe response or event data.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
        """
        return await self._call(self.client().v1.refunds.retrieve, refund_id)

    def verify_event(self, payload: bytes, signature: str) -> dict:
        """
        Verify webhook signature and test/live mode before returning the Stripe event.

        Args:
            payload (bytes): Unmodified raw webhook request bytes.
            signature (str): Stripe-Signature header supplied with the webhook.

        Returns:
            dict: Stripe response or event data.

        Raises:
            HTTPException: Stripe configuration, request, signature or provider
                operation is invalid or unavailable.
        """
        secret = self.settings.STRIPE_WEBHOOK_SECRET.get_secret_value()

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe webhook is not configured"
            )

        try:
            event = (
                stripe.Webhook.construct_event(payload, signature, secret)
                .to_dict()
            )

        except (ValueError, stripe.SignatureVerificationError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Stripe webhook"
            )

        if event.get("livemode") != self.settings.STRIPE_LIVE_MODE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unexpected Stripe mode"
            )

        return event


def get_stripe_gateway() -> StripeGateway:
    """
    Build the Stripe gateway from application settings.

    Returns:
        StripeGateway: Configured component ready for use.
    """
    return StripeGateway(get_settings())

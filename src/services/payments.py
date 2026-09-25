import time
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import HttpUrl

from src.database.models import (
    OrderModel,
    OrderStatusEnum,
    PaymentCheckoutModel,
    PaymentItemModel,
    PaymentModel,
    PaymentStatusEnum
)
from src.notifications.queue import EmailQueue, EmailQueueError
from src.payments.checkout import build_checkout_data, checkout_amount
from src.payments.stripe import CheckoutRejectedError, StripeGateway
from src.repositories.payments import PaymentRepository
from src.schemas.movies import MovieListItemResponseSchema
from src.schemas.payments import (
    AdminPaymentListQuerySchema,
    PaymentCheckoutResponseSchema,
    PaymentListQuerySchema,
    PaymentListResponseSchema,
    PaymentRefundResponseSchema,
    PaymentResponseSchema,
    PurchasedMovieListResponseSchema
)
from src.services.database_errors import database_errors
from src.services.orders import OrderService


class PaymentService:
    def __init__(
            self,
            repository: PaymentRepository,
            orders: OrderService,
            gateway: StripeGateway,
            email_queue: EmailQueue
    ):
        self.repository = repository
        self.orders = orders
        self.gateway = gateway
        self.email_queue = email_queue

    async def list_payments(
            self,
            query: PaymentListQuerySchema | AdminPaymentListQuerySchema,
            user_id: int | None = None
    ) -> PaymentListResponseSchema:
        async with database_errors(self.repository, detail="Payments are temporarily unavailable"):
            records, total = await self.repository.list_payments(query, user_id)

            return PaymentListResponseSchema(
                items=[PaymentResponseSchema.model_validate(record) for record in records],
                total=total,
                page=query.page,
                per_page=query.per_page
            )

    async def get_payment(self, user_id: int, payment_id: int) -> PaymentResponseSchema:
        async with database_errors(self.repository, detail="Payment is temporarily unavailable"):
            payment = await self._owned_payment(user_id, payment_id)

            return PaymentResponseSchema.model_validate(payment)

    async def _owned_payment(self, user_id: int, payment_id: int) -> PaymentModel:
        payment = await self.repository.get_payment(payment_id, user_id)

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )

        return payment

    async def purchased_movies(self, user_id: int, query: PaymentListQuerySchema) -> PurchasedMovieListResponseSchema:
        async with database_errors(self.repository, detail="Purchased movies are temporarily unavailable"):
            movies, total = await self.repository.purchased_movies(user_id, query.page, query.per_page)

            return PurchasedMovieListResponseSchema(
                items=[MovieListItemResponseSchema.model_validate(movie) for movie in movies],
                total=total,
                page=query.page,
                per_page=query.per_page
            )

    async def create_checkout(self, user_id: int, order_id: int) -> PaymentCheckoutResponseSchema:
        async with database_errors(self.repository, detail="Payment checkout could not be saved"):
            order = await self.orders.get_owned_order(user_id, order_id, lock=True)
            checkout = await self.repository.checkout_for_order(order_id)

            if order.status != OrderStatusEnum.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only pending orders can be paid"
                )

            if checkout is None:
                order = await self.orders.prepare_for_payment(user_id, order_id)
                assert order.total_amount is not None
                amount = int(order.total_amount * 100)

                if 0 < amount < 50 or amount > 99999999:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe requires a zero total or a total between 0.50 and 999999.99 USD/EUR"
                    )
                self.gateway.client()
                key = str(uuid4())
                expires_at = int(time.time()) + 3600
                data = build_checkout_data(
                    order, self.gateway.settings.STRIPE_CURRENCY,
                    str(self.gateway.settings.PAYMENT_RETURN_URL), key, expires_at
                )
                checkout = PaymentCheckoutModel(
                    order_id=order_id,
                    request_key=key,
                    request_data=data, expires_at=expires_at
                )
                await self.repository.add(checkout)
                await self.repository.commit()
                order = await self.orders.get_owned_order(user_id, order_id, lock=True)
                checkout = await self.repository.checkout_for_order(order_id)
                assert checkout is not None

            if checkout.status not in {"creating", "open"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This checkout has already ended"
                )

            if checkout.session_id:
                session = await self.gateway.retrieve_checkout(checkout.session_id)

            else:
                if checkout.expires_at <= int(time.time()):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Checkout outcome is unknown. Wait for the Stripe webhook or contact support."
                    )

                try:
                    session = await self.gateway.create_checkout(checkout.request_data, checkout.request_key)

                except CheckoutRejectedError:
                    checkout.status = "rejected"
                    order.status = OrderStatusEnum.CANCELED
                    await self.repository.commit()
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stripe could not create checkout. Check payment-method configuration, then create a new order."
                    )

            self._validate_session(checkout, session)
            checkout.session_id = session["id"]

            if session["status"] != "open":
                await self._finalize_checkout(order, checkout, session)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Checkout has ended. Check payment history; create a new order if it expired."
                )

            checkout.status = "open"
            checkout.checkout_url = session["url"]
            response = PaymentCheckoutResponseSchema(order_id=order_id, checkout_url=HttpUrl(session["url"]))
            await self.repository.commit()

            return response

    def _validate_session(self, checkout: PaymentCheckoutModel, session: dict) -> None:
        price = checkout.request_data["line_items"][0]["price_data"]

        if (
                (session.get("metadata") or {}).get("request_key") != checkout.request_key
                or (session.get("metadata") or {}).get("order_id") != str(checkout.order_id)
                or session.get("client_reference_id") != str(checkout.order_id)
                or session.get("amount_total") != checkout_amount(checkout.request_data)
                or session.get("currency") != price["currency"]
                or session.get("mode") != "payment"
                or (checkout.session_id is not None and checkout.session_id != session.get("id"))
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stripe session does not match the order"
            )

    async def cancel_checkout(self, user_id: int, order_id: int) -> None:
        async with database_errors(self.repository, detail="Checkout could not be canceled"):
            order = await self.orders.get_owned_order(user_id, order_id, lock=True)
            checkout = await self.repository.checkout_for_order(order_id)

            if checkout is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Checkout not found"
                )

            if checkout.status in {"expired", "rejected"}:
                return

            if order.status != OrderStatusEnum.PENDING or not checkout.session_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checkout cannot be canceled now")

            session = await self.gateway.retrieve_checkout(checkout.session_id)

            if session["status"] == "open":
                session = await self.gateway.expire_checkout(checkout.session_id)

            if session["status"] != "expired":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment already processing or completed"
                )

            self._validate_session(checkout, session)
            await self._record_session(order, checkout, session)
            await self.repository.commit()

    async def _record_session(self, order: OrderModel, checkout: PaymentCheckoutModel, session: dict) -> None:
        paid = session.get("status") == "complete" and (
            session.get("payment_status") == "paid" or (
                session.get("payment_status") == "no_payment_required" and session.get("amount_total") == 0
            )
        )

        if checkout.payment_id is not None:
            return

        if not paid and session.get("status") != "expired":
            return

        amount = Decimal(session["amount_total"]) / 100
        total = sum((item.price_at_order for item in order.items), Decimal("0"))

        if amount != order.total_amount or total != amount:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stored order total no longer matches payment"
            )

        if paid and amount > 0 and not session.get("payment_intent"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Stripe payment intent"
            )

        payment = PaymentModel(
            user_id=order.user_id,
            order_id=order.id,
            amount=amount,
            currency=session["currency"],
            external_payment_id=(session.get("payment_intent") or session["id"]) if paid else session["id"],
            status=PaymentStatusEnum.SUCCESSFUL if paid else PaymentStatusEnum.CANCELED,
            items=[PaymentItemModel(order_item_id=item.id, price_at_payment=item.price_at_order) for item in order.items]
        )
        await self.repository.add(payment)
        checkout.payment_id = payment.id
        checkout.session_id = session["id"]
        checkout.status = "completed" if paid else "expired"
        order.status = OrderStatusEnum.PAID if paid else OrderStatusEnum.CANCELED

        if paid:
            cart = await self.orders.cart_repository.get_cart(order.user_id, lock=True)

            if cart is not None:
                await self.orders.cart_repository.remove_items(cart.id, [item.movie_id for item in order.items])

    async def _queue_confirmation(self, order: OrderModel, checkout: PaymentCheckoutModel) -> None:
        if checkout.status != "completed" or checkout.email_queued:
            return

        email = await self.repository.user_email(order.user_id)

        try:
            await self.email_queue.send_payment_confirmation(
                email,
                order.id,
                str(order.total_amount),
                checkout.request_data["line_items"][0]["price_data"]["currency"]
            )

        except EmailQueueError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment saved; email queue unavailable"
            )

        checkout.email_queued = True
        await self.repository.commit()

    async def _find_checkout(self, session: dict) -> PaymentCheckoutModel | None:
        metadata = session.get("metadata") or {}
        order_id = str(metadata.get("order_id", ""))

        if not order_id.isascii() or not order_id.isdigit() or len(order_id) > 10:
            return None

        if not 0 < int(order_id) <= 2**31 - 1 or not metadata.get("request_key"):
            return None

        checkout = await self.repository.checkout_for_order(int(order_id))

        if checkout is None or checkout.request_key != metadata["request_key"]:
            return None

        return checkout

    async def _finalize_checkout(self, order: OrderModel, checkout: PaymentCheckoutModel, session: dict) -> None:
        await self._record_session(order, checkout, session)
        await self.repository.commit()
        order = await self.orders.get_owned_order(order.user_id, order.id, lock=True)
        locked_checkout = await self.repository.checkout_for_order(order.id)
        assert locked_checkout is not None
        await self._queue_confirmation(order, locked_checkout)

    async def handle_event(self, event: dict) -> None:
        async with database_errors(self.repository, detail="Payment notification could not be saved"):
            kind = event.get("type", "")
            data = event.get("data", {}).get("object", {})

            if kind in {
                "checkout.session.completed",
                "checkout.session.async_payment_succeeded",
                "checkout.session.expired"
            }:
                checkout = await self._find_checkout(data)

                if checkout is None:
                    return

                order_id = checkout.order_id
                order = await self.orders.repository.get_by_id(order_id, lock=True)
                checkout = await self.repository.checkout_for_order(order_id)
                assert order is not None and checkout is not None
                self._validate_session(checkout, data)
                await self._finalize_checkout(order, checkout, data)

            elif kind in {"refund.created", "refund.updated", "refund.failed"}:
                external_id = data.get("payment_intent")

                if not external_id:
                    return

                payment = await self.repository.payment_by_external_id(external_id)

                if payment is None:
                    session = await self.gateway.checkout_for_payment_intent(external_id)

                    if session is None or await self._find_checkout(session) is None:
                        return

                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Payment not recorded yet"
                    )
                order = await self.orders.repository.get_by_id(payment.order_id, lock=True)
                assert order is not None
                checkout = await self.repository.checkout_for_order(order.id)

                if checkout is None:
                    return

                refund = await self.gateway.retrieve_refund(data["id"])
                await self._apply_refund(order, checkout, payment, refund)
                await self.repository.commit()

    async def _apply_refund(
            self,
            order: OrderModel,
            checkout: PaymentCheckoutModel,
            payment: PaymentModel,
            refund: dict
    ) -> None:
        currency = checkout.request_data["line_items"][0]["price_data"]["currency"]

        if (
                refund.get("payment_intent") != payment.external_payment_id
                or refund.get("amount") != int(payment.amount * 100) or refund.get("currency") != currency
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a matching full refund is supported"
            )
        checkout.refund_id = refund["id"]

        if refund.get("status") == "succeeded":
            payment.status = PaymentStatusEnum.REFUNDED
            order.status = OrderStatusEnum.CANCELED

    async def refund(self, user_id: int, payment_id: int) -> PaymentRefundResponseSchema:
        async with database_errors(self.repository, detail="Refund could not be saved"):
            payment = await self._owned_payment(user_id, payment_id)
            order = await self.orders.get_owned_order(user_id, payment.order_id, lock=True)
            payment = await self._owned_payment(user_id, payment_id)
            checkout = await self.repository.checkout_for_order(order.id)

            if payment.status == PaymentStatusEnum.REFUNDED:
                return PaymentRefundResponseSchema(payment_id=payment.id, message="Payment already refunded")

            if (
                    payment.status != PaymentStatusEnum.SUCCESSFUL or checkout is None
                    or not payment.external_payment_id or payment.amount == 0
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only a successful Stripe payment can be refunded"
                )

            if checkout.refund_id:
                refund = await self.gateway.retrieve_refund(checkout.refund_id)

            else:
                refund = await self.gateway.refund(
                    payment.external_payment_id,
                    int(payment.amount * 100),
                    f"refund-{checkout.request_key}"
                )
            await self._apply_refund(order, checkout, payment, refund)
            await self.repository.commit()

            if refund.get("status") in {"failed", "canceled"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Refund failed. Contact support before retrying."
                )

            message = "Payment refunded" if payment.status == PaymentStatusEnum.REFUNDED else "Refund is processing"

            return PaymentRefundResponseSchema(payment_id=payment.id, message=message)

    async def return_message(self, session_id: str | None) -> str:
        if not session_id:
            return "Payment was not confirmed. You can return to checkout or cancel it through the API."

        async with database_errors(self.repository, detail="Payment status unavailable"):
            checkout = await self.repository.checkout_for_session(session_id)

            if checkout is None or checkout.payment_id is None:
                return "Payment confirmation is processing. Check your payment history shortly."

            payment = await self.repository.get_payment(checkout.payment_id)
            assert payment is not None

            if payment.status == PaymentStatusEnum.SUCCESSFUL:
                return "Payment successful. Your movies are now in Purchased. You can close this page."

            if payment.status == PaymentStatusEnum.REFUNDED:
                return "Payment refunded. You can close this page."

            return "Checkout expired or was canceled. Your card was not charged by this checkout."

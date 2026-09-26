from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    status
)
from fastapi.responses import HTMLResponse

from src.api.dependencies import get_payment_service
from src.database.models import UserModel
from src.payments.stripe import StripeGateway, get_stripe_gateway
from src.schemas.common import ErrorResponseSchema, MessageResponseSchema
from src.schemas.payments import (
    AdminPaymentListQuerySchema,
    PaymentCheckoutResponseSchema,
    PaymentCreateRequestSchema,
    PaymentListQuerySchema,
    PaymentListResponseSchema,
    PaymentRefundRequestSchema,
    PaymentRefundResponseSchema,
    PaymentResponseSchema,
    PurchasedMovieListResponseSchema
)
from src.security.dependencies import get_current_admin, get_current_user
from src.services.payments import PaymentService


router = APIRouter(
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Access token required"
        },
        402: {
            "model": ErrorResponseSchema,
            "description": "Card declined; try another card or contact your bank"
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Inactive account or insufficient permissions"
        },
        404: {
            "model": ErrorResponseSchema,
            "description": "Resource not found or belongs to another user"
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "Order/payment cannot be processed in its current state"
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Provider, database or email queue unavailable. "
                           "Retry safely."
        }
    }
)


@router.post(
    "/checkout/",
    response_model=PaymentCheckoutResponseSchema,
    summary="Pay for your order with Stripe",
    description="Send order_id of your pending order. "
                "Prices and total are checked on the server. "
                "Returns a Stripe URL for card payment "
                "(card must be enabled in Stripe). Repeated requests "
                "reuse the same session. Currency is configured on the server "
                "(USD/EUR). Nonzero totals must be 0.50–999999.99. "
                "Checkout expires after one hour. "
                "Card declines are displayed by Stripe with an option to try "
                "another card. A verified webhook confirms the purchase. "
                "Retrying checkout also "
                "reconciles completed/expired sessions directly "
                "with Stripe if a webhook was missed."
)
async def create_checkout(
        data: PaymentCreateRequestSchema,
        user: UserModel = Depends(get_current_user),
        service: PaymentService = Depends(get_payment_service)
) -> PaymentCheckoutResponseSchema:
    return await service.create_checkout(user.id, data.order_id)


@router.post(
    "/checkout/{order_id}/cancel/",
    response_model=MessageResponseSchema,
    summary="Cancel an unpaid checkout",
    description="Expires the Stripe session before canceling your order. "
                "Cart movies are preserved. "
                "Cannot cancel a payment already processing or completed; "
                "use refund instead. No body required."
)
async def cancel_checkout(
        order_id: int = Path(gt=0, le=2**31 - 1),
        user: UserModel = Depends(get_current_user),
        service: PaymentService = Depends(get_payment_service)
) -> MessageResponseSchema:
    await service.cancel_checkout(user.id, order_id)

    return MessageResponseSchema(message="Checkout canceled")


@router.get(
    "/",
    response_model=PaymentListResponseSchema,
    summary="View your payment history",
    description="Your payments, newest first: dates, totals, items and "
                "successful/canceled/refunded status. "
                "Open checkouts are not completed payments. "
                "page starts at 1; per_page is 1–100."
)
async def list_payments(
        query: Annotated[PaymentListQuerySchema, Query()],
        user: UserModel = Depends(get_current_user),
        service: PaymentService = Depends(get_payment_service)
) -> PaymentListResponseSchema:
    return await service.list_payments(query, user.id)


@router.get(
    "/admin/",
    response_model=PaymentListResponseSchema,
    dependencies=[Depends(get_current_admin)],
    summary="Filter all payments as an administrator",
    description="ADMIN only. Filter by user_id, status, date_from/date_to "
                "(YYYY-MM-DD, inclusive UTC). Filters combine with AND. "
                "Supports page and per_page; newest first."
)
async def admin_payments(
        query: Annotated[AdminPaymentListQuerySchema, Query()],
        service: PaymentService = Depends(get_payment_service)
) -> PaymentListResponseSchema:
    return await service.list_payments(query)


@router.get(
    "/purchased/",
    response_model=PurchasedMovieListResponseSchema,
    summary="List your purchased movies",
    description="Paginated movies from successful payments only. "
                "Fully refunded purchases no longer grant access."
)
async def purchased(
        query: Annotated[PaymentListQuerySchema, Query()],
        user: UserModel = Depends(get_current_user),
        service: PaymentService = Depends(get_payment_service)
) -> PurchasedMovieListResponseSchema:
    return await service.purchased_movies(user.id, query)


@router.post(
    "/refund/",
    response_model=PaymentRefundResponseSchema,
    summary="Request a full refund",
    description="Send payment_id of your successful payment. "
                "Returns the entire amount to the original card. "
                "Repeating the request does not create another refund. "
                "Pending provider refunds remain successful locally until confirmed; "
                "a confirmed refund cancels the order and revokes Purchased access. "
                "Partial refunds are not supported."
)
async def refund(
        data: PaymentRefundRequestSchema,
        user: UserModel = Depends(get_current_user),
        service: PaymentService = Depends(get_payment_service)
) -> PaymentRefundResponseSchema:
    return await service.refund(user.id, data.payment_id)


@router.post(
    "/webhook/",
    response_model=MessageResponseSchema,
    summary="Receive signed Stripe events",
    description="Stripe only, no JWT. Raw JSON body and "
                "Stripe-Signature header are required. Subscribe to "
                "checkout.session.completed, checkout.session.expired, "
                "checkout.session.async_payment_succeeded, "
                "refund.created, refund.updated, refund.failed. "
                "Duplicate events are safe; retry non-2xx responses."
)
async def webhook(
        request: Request,
        signature: str = Header(default="", alias="Stripe-Signature"),
        gateway: StripeGateway = Depends(get_stripe_gateway),
        service: PaymentService = Depends(get_payment_service)
) -> MessageResponseSchema:
    payload = bytearray()

    async for chunk in request.stream():
        payload.extend(chunk)

        if len(payload) > 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Webhook too large"
            )

    event = gateway.verify_event(bytes(payload), signature)
    await service.handle_event(event)

    return MessageResponseSchema(message="Event received")


@router.get(
    "/return/",
    response_class=HTMLResponse,
    summary="Show checkout result",
    description="Stripe browser redirect. Shows confirmation only after "
                "the webhook has saved the payment. "
                "This page never changes payment status and "
                "exposes no personal or order details."
)
async def payment_return(
        session_id: str | None = Query(default=None, max_length=255),
        service: PaymentService = Depends(get_payment_service)
) -> HTMLResponse:
    message = await service.return_message(session_id)

    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><title>Online Cinema</title></head>"
        f"<body><h1>Online Cinema</h1><p>{message}</p></body></html>",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )


@router.get(
    "/{payment_id}/",
    response_model=PaymentResponseSchema,
    summary="View your payment",
    description="Returns only your own payment, "
                "including purchased items and their historical prices."
)
async def get_payment(
        payment_id: int = Path(gt=0, le=2**31 - 1),
        user: UserModel = Depends(get_current_user),
        service: PaymentService = Depends(get_payment_service)
) -> PaymentResponseSchema:
    return await service.get_payment(user.id, payment_id)

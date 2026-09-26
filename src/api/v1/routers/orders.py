from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.api.dependencies import get_order_service
from src.database.models import UserModel
from src.schemas.common import ErrorResponseSchema
from src.schemas.orders import (
    AdminOrderListQuerySchema,
    OrderListQuerySchema,
    OrderListResponseSchema,
    OrderResponseSchema
)
from src.security.dependencies import get_current_admin, get_current_user
from src.services.orders import OrderService


router = APIRouter(
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Missing or invalid access token"
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Inactive account or insufficient permissions"
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Database temporarily unavailable"
        }
    }
)


@router.get(
    "/",
    response_model=OrderListResponseSchema,
    summary="List your orders",
    description=(
            "Requires an active account. Returns only your orders, "
            "newest first, including pending, paid and canceled. "
            "Use page (from 1) and per_page (1–100). Each order "
            "includes its creation time, status, movies, "
            "stored item prices and total. "
            "Create an order through POST /api/v1/cart/checkout/."
    )
)
async def list_orders(
        query: Annotated[OrderListQuerySchema, Query()],
        current_user: UserModel = Depends(get_current_user),
        service: OrderService = Depends(get_order_service)
) -> OrderListResponseSchema:
    return await service.list_orders(query, user_id=current_user.id)


@router.get(
    "/admin/",
    response_model=OrderListResponseSchema,
    dependencies=[Depends(get_current_admin)],
    summary="List all orders as an administrator",
    description=(
            "ADMIN only. Optional filters: user_id, "
            "status (pending, paid, canceled), date_from and date_to "
            "(YYYY-MM-DD, both dates inclusive in UTC). "
            "Filters combine with AND. Supports page and per_page; "
            "newest orders first. "
            "A range with date_to earlier than date_from is rejected."
    )
)
async def list_all_orders(
        query: Annotated[AdminOrderListQuerySchema, Query()],
        service: OrderService = Depends(get_order_service)
) -> OrderListResponseSchema:
    return await service.list_orders(query)


@router.get(
    "/{order_id}/",
    response_model=OrderResponseSchema,
    summary="View your order",
    description=(
            "Returns your order with all items and stored prices, "
            "including movies removed from the catalog. "
            "Unknown orders and orders belonging to another user both return 404, "
            "including for administrators."
    ),
    responses={
        404: {
            "model": ErrorResponseSchema,
            "description": "Order not found or not owned by you"
        }
    }
)
async def get_order(
        order_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: OrderService = Depends(get_order_service)
) -> OrderResponseSchema:
    return await service.get_order(current_user.id, order_id)


@router.patch(
    "/{order_id}/cancel/",
    response_model=OrderResponseSchema,
    summary="Cancel your pending order",
    description=(
            "No body required. Cancels only your pending, unpaid order. "
            "Preserves items, prices and cart contents. "
            "An already canceled order returns 409. A paid order or an order "
            "with a successful/refunded payment "
            "cannot be canceled here; payment refunds belong to the Payments flow."
    ),
    responses={
        404: {
            "model": ErrorResponseSchema,
            "description": "Order not found or not owned by you"
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "Order already canceled or payment has completed"
        }
    }
)
async def cancel_order(
        order_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: OrderService = Depends(get_order_service)
) -> OrderResponseSchema:
    return await service.cancel_order(current_user.id, order_id)

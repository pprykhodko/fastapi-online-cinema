from fastapi import APIRouter, Depends, Path, Response, status

from src.api.dependencies import get_cart_service, get_order_service
from src.database.models import UserModel
from src.schemas.cart import CartItemCreateRequestSchema, CartItemResponseSchema, CartResponseSchema
from src.schemas.common import ErrorResponseSchema
from src.schemas.orders import OrderCreateResponseSchema
from src.security.dependencies import get_current_admin, get_current_user
from src.services.cart import CartService
from src.services.orders import OrderService


router = APIRouter(
    responses={
        401: {
            "model": ErrorResponseSchema,
            "description": "Register, activate your account and log in first"
        },
        403: {
            "model": ErrorResponseSchema,
            "description": "Inactive account or insufficient permissions"
        },
        404: {
            "model": ErrorResponseSchema,
            "description": "Cart, movie or cart item not found"
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Database temporarily unavailable"
        }
    }
)


@router.get(
    "/",
    response_model=CartResponseSchema,
    summary="View your cart",
    description=(
            "Returns your cart with movie names, current prices, genres and release years. Requires an active account."
    )
)
async def get_cart(
        current_user: UserModel = Depends(get_current_user),
        service: CartService = Depends(get_cart_service)
) -> CartResponseSchema:
    return await service.get_cart(current_user.id)


@router.post(
    "/items/",
    response_model=CartItemResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Add a movie to your cart",
    description=(
            "Accepts movie_id in JSON. The cart owner is taken from the access token. "
            "Rejects duplicate items, purchased movies, deleted movies and movies without a price. A zero price is allowed."
    ),
    responses={
        409: {"model": ErrorResponseSchema, "description": "Duplicate, purchased or unavailable movie."}
    }
)
async def add_item(
        data: CartItemCreateRequestSchema,
        current_user: UserModel = Depends(get_current_user),
        service: CartService = Depends(get_cart_service)
) -> CartItemResponseSchema:
    return await service.add_item(current_user.id, data.movie_id)


@router.delete(
    "/items/{movie_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a movie from your cart",
    description="movie_id is a movie ID, not a cart item ID. Removes only your item, including unavailable movies."
)
async def remove_item(
        movie_id: int = Path(gt=0, le=2**31 - 1),
        current_user: UserModel = Depends(get_current_user),
        service: CartService = Depends(get_cart_service)
) -> Response:
    await service.remove_item(current_user.id, movie_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear your cart",
    description="Removes all your cart items, preserving the cart itself. An already empty cart also returns 204."
)
async def clear_cart(
        current_user: UserModel = Depends(get_current_user),
        service: CartService = Depends(get_cart_service)
) -> Response:
    await service.clear_cart(current_user.id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/users/{user_id}/",
    response_model=CartResponseSchema,
    dependencies=[Depends(get_current_admin)],
    summary="View a user's cart as an administrator",
    description="ADMIN only. Returns the cart of the specified user for troubleshooting, including inactive users."
)
async def get_user_cart(
        user_id: int = Path(gt=0, le=2**31 - 1),
        service: CartService = Depends(get_cart_service)
) -> CartResponseSchema:
    return await service.get_cart(user_id)


@router.post(
    "/checkout/",
    response_model=OrderCreateResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create an order from your cart",
    description=(
            "No body required. Rechecks availability and purchases, removes excluded items from the cart and reports "
            "their movie IDs and reasons. Creates one pending order with a snapshot of current prices. "
            "Valid items remain in the cart until payment. Returns 200 with order=null if all items were excluded; "
            "400 for an empty cart; 409 if eligible movies already belong to your pending order. "
            "This endpoint does not take payment or mark movies as purchased."
    ),
    responses={
        200: {"model": OrderCreateResponseSchema, "description": "All cart items were excluded; no order created."},
        400: {"model": ErrorResponseSchema, "description": "Empty cart."},
        409: {"model": ErrorResponseSchema, "description": "Pending order overlap, excessive total or data conflict."},
    }
)
async def checkout(
        response: Response,
        current_user: UserModel = Depends(get_current_user),
        service: OrderService = Depends(get_order_service)
) -> OrderCreateResponseSchema:
    result = await service.checkout(current_user.id)

    if result.order is None:
        response.status_code = status.HTTP_200_OK

    return result

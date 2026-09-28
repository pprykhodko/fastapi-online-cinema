from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.database.models import OrderModel


def build_checkout_data(
        order: OrderModel,
        currency: str,
        return_url: str,
        key: str,
        expires_at: int
) -> dict:
    """
    Build card checkout parameters from saved order prices, grouping more than 100
    items.

    Args:
        order (OrderModel): Order with its loaded items and saved prices.
        currency (str): Payment currency code, such as usd or eur.
        return_url (str): Public browser URL used after checkout.
        key (str): Stable checkout/refund idempotency key.
        expires_at (int): Checkout expiration as a Unix timestamp in seconds.

    Returns:
        dict: Stripe session parameters with metadata, line items and return URLs.
    """
    line_items = [
        {
            "quantity": 1,
            "price_data": {
                "currency": currency,
                "unit_amount": int(item.price_at_order * 100),
                "product_data": {"name": item.movie.name}
            }
        } for item in order.items
    ]

    if len(line_items) > 100:
        line_items = [
            {
                "quantity": 1,
                "price_data": {
                    "currency": currency,
                    "unit_amount": sum(
                        int(item.price_at_order * 100) for item in order.items
                    ),
                    "product_data": {
                        "name": f"Online Cinema order #{order.id} "
                                f"({len(order.items)} movies)"
                    }
                }
            }
        ]
    parts = urlsplit(return_url)
    query = dict(parse_qsl(parts.query))
    query["session_id"] = "{CHECKOUT_SESSION_ID}"
    success_url = urlunsplit(parts._replace(query=urlencode(query)))
    success_url = success_url.replace(
        "%7BCHECKOUT_SESSION_ID%7D",
        "{CHECKOUT_SESSION_ID}"
    )

    return {
        "mode": "payment",
        "payment_method_types": ["card"],
        "client_reference_id": str(order.id),
        "metadata": {
            "order_id": str(order.id),
            "request_key": key
        },
        "line_items": line_items,
        "success_url": success_url,
        "cancel_url": return_url,
        "expires_at": expires_at
    }


def checkout_amount(data: dict) -> int:
    """
    Sum Stripe checkout line items in the smallest currency unit.

    Args:
        data (dict): Stripe checkout request parameters with line items and prices in
            cents.

    Returns:
        int: Total amount in the smallest currency unit (cents).
    """
    return sum(
        item["quantity"] * item["price_data"]["unit_amount"]
        for item in data["line_items"]
    )

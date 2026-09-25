from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from src.payments.checkout import build_checkout_data, checkout_amount


@pytest.mark.parametrize("count", [1, 100, 101])
def test_checkout_lines_preserve_amounts_and_provider_limit(count):
    order = SimpleNamespace(id=7, items=[SimpleNamespace(price_at_order=Decimal("12.34"),
                                                        movie=SimpleNamespace(name=f"Movie {i}")) for i in range(count)])
    result = build_checkout_data(order, "eur", "https://example.com/return/?lang=en#result", "key", 123456)
    assert checkout_amount(result) == 1234 * count
    assert len(result["line_items"]) == (count if count <= 100 else 1)
    assert result["line_items"][0]["price_data"]["currency"] == "eur"
    assert result["metadata"] == {"order_id": "7", "request_key": "key"}
    assert result["expires_at"] == 123456
    assert result["cancel_url"] == "https://example.com/return/?lang=en#result"
    assert "{CHECKOUT_SESSION_ID}" in result["success_url"]
    assert parse_qs(urlsplit(result["success_url"]).query) == {"lang": ["en"], "session_id": ["{CHECKOUT_SESSION_ID}"]}


def test_checkout_amount_respects_quantities():
    assert checkout_amount({"line_items": [{"quantity": 2, "price_data": {"unit_amount": 99}}]}) == 198

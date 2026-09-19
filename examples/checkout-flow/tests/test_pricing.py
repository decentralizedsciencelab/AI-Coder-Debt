"""Unit tests for cart pricing."""

from checkout_flow.checkout.pricing import cart_total, line_total


def test_line_total_multiplies_price_by_quantity():
    """One line is priced as unit price times quantity."""
    assert line_total({"unit_price": 4.50, "quantity": 2}) == 9.0


def test_cart_total_applies_tax():
    """The cart total includes tax."""
    assert cart_total([{"unit_price": 10.00, "quantity": 1}]) == 10.80


def test_cart_total_of_empty_cart_is_zero():
    """An empty cart costs nothing."""
    assert not cart_total([])

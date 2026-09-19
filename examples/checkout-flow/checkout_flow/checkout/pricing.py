"""Cart pricing."""

TAX_RATE = 0.08


def line_total(item):
    """Return the price of one cart line."""
    return item["unit_price"] * item["quantity"]


def cart_total(items):
    """Return the tax-inclusive total for a list of cart lines."""
    subtotal = sum(line_total(i) for i in items)
    return round(subtotal * (1 + TAX_RATE), 2)

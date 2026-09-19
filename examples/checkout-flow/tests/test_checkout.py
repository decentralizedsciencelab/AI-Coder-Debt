"""Unit tests for the checkout handler.

The payments boundary is mocked. That is why this suite passes while the
deployed system does not: the stub answers 200 to whatever URL the handler
posts to, so the route name is never compared against the payments service.
"""

from unittest.mock import patch

from checkout_flow.checkout.app import app


class StubResponse:
    """Minimal stand-in for a requests Response."""

    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        """Return the decoded body."""
        return self._payload

    def raise_for_status(self):
        """Match the requests API; the stub never raises."""
        return None


def test_quote_returns_taxed_total():
    """Quoting a cart needs no payments call."""
    resp = app.test_client().post(
        "/checkout/quote", json={"items": [{"unit_price": 10.0, "quantity": 1}]}
    )
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 10.80


@patch(
    "checkout_flow.checkout.app.requests.post",
    return_value=StubResponse(200, {"authorized": True}),
)
def test_checkout_succeeds_when_payment_authorizes(mock_post):
    """A 200 from payments completes the order."""
    resp = app.test_client().post(
        "/checkout", json={"items": [{"unit_price": 10.0, "quantity": 1}]}
    )
    assert resp.status_code == 201
    assert resp.get_json() == {"order_total": 10.80, "paid": True}
    assert mock_post.called


@patch(
    "checkout_flow.checkout.app.requests.post",
    return_value=StubResponse(502),
)
def test_checkout_reports_failure_when_payment_declines(mock_post):
    """A non-200 from payments surfaces as a gateway error."""
    resp = app.test_client().post(
        "/checkout", json={"items": [{"unit_price": 10.0, "quantity": 1}]}
    )
    assert resp.status_code == 502
    assert mock_post.called


def test_health_is_green():
    """The health endpoint reports liveness."""
    assert app.test_client().get("/health").status_code == 200

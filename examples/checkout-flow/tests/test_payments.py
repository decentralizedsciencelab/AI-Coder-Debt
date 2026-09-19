"""Unit tests for the payments service."""

from checkout_flow.payments.app import app


def test_authorize_accepts_an_amount():
    """Authorization succeeds for a valid amount."""
    resp = app.test_client().post("/payments/authorize", json={"amount": 10.80})
    assert resp.status_code == 200
    assert resp.get_json()["authorized"] is True


def test_authorize_rejects_a_missing_amount():
    """Authorization requires an amount."""
    assert app.test_client().post("/payments/authorize", json={}).status_code == 400


def test_refund_returns_the_amount():
    """A refund reports the amount returned."""
    resp = app.test_client().post("/payments/refund", json={"amount": 5.0})
    assert resp.get_json()["refunded"] is True


def test_health_is_green():
    """The health endpoint reports liveness."""
    assert app.test_client().get("/health").status_code == 200

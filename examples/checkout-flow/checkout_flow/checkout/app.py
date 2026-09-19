"""Checkout service. Prices a cart, then charges it via the payments service."""

import os

import requests
from flask import Flask, jsonify, request

from checkout_flow.checkout.pricing import cart_total

app = Flask(__name__)

PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://localhost:9002")
CHECKOUT_PORT = int(os.getenv("CHECKOUT_PORT", "9001"))


@app.route("/checkout", methods=["POST"])
def checkout():
    """Price the cart and charge it, returning the completed order."""
    payload = request.get_json() or {}
    total = cart_total(payload.get("items", []))

    charged = requests.post(
        "http://localhost:9002/payments/charge",
        json={"amount": total},
        timeout=5,
    )
    if charged.status_code != 200:
        return jsonify({"error": "payment failed"}), 502

    return jsonify({"order_total": total, "paid": True}), 201


@app.route("/checkout/quote", methods=["POST"])
def quote():
    """Return the cart total without charging it."""
    payload = request.get_json() or {}
    return jsonify({"total": cart_total(payload.get("items", []))}), 200


@app.route("/checkout/cancel", methods=["POST"])
def cancel():
    """Refund a completed order."""
    payload = request.get_json() or {}
    requests.post(
        "http://localhost:9002/payments/refund",
        json={"amount": payload.get("amount", 0)},
        timeout=5,
    )
    return jsonify({"cancelled": True}), 200


@app.route("/health", methods=["GET"])
def health():
    """Report service liveness."""
    return jsonify({"status": "ok"}), 200

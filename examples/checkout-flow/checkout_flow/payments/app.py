"""Payments service. Owns authorization and refunds."""

import os

from flask import Flask, jsonify, request

app = Flask(__name__)

LEDGER_URL = os.getenv("LEDGER_URL")
PAYMENTS_PORT = int(os.getenv("PAYMENTS_PORT", "9002"))


@app.route("/payments/authorize", methods=["POST"])
def authorize():
    """Authorize a charge for the supplied amount."""
    payload = request.get_json() or {}
    if not payload.get("amount"):
        return jsonify({"error": "amount required"}), 400
    return jsonify({"authorized": True, "amount": payload["amount"]}), 200


@app.route("/payments/refund", methods=["POST"])
def refund():
    """Refund the supplied amount."""
    payload = request.get_json() or {}
    return jsonify({"refunded": True, "amount": payload.get("amount", 0)}), 200


@app.route("/health", methods=["GET"])
def health():
    """Report service liveness."""
    return jsonify({"status": "ok"}), 200

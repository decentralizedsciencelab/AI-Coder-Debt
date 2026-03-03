"""Main application for mixed project."""

import os

from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/api/data")
def get_data():
    """Get data endpoint."""
    db_url = os.environ.get("DATABASE_URL")
    return jsonify({"data": [], "connected": bool(db_url)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

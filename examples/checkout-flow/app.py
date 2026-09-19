"""Entry point. Runs whichever service the SERVICE variable names."""

import os
import sys

from checkout_flow.checkout.app import CHECKOUT_PORT
from checkout_flow.checkout.app import app as checkout_app
from checkout_flow.payments.app import PAYMENTS_PORT
from checkout_flow.payments.app import app as payments_app

SERVICE = os.getenv("SERVICE", "checkout")


def main():
    """Start the service named by SERVICE."""
    if SERVICE == "checkout":
        checkout_app.run(host="0.0.0.0", port=CHECKOUT_PORT)
    elif SERVICE == "payments":
        payments_app.run(host="0.0.0.0", port=PAYMENTS_PORT)
    else:
        sys.exit(f"unknown SERVICE {SERVICE!r}")


if __name__ == "__main__":
    main()

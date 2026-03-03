"""Main application module."""

import os

from utils import helper


def main() -> dict:
    """Main entry point."""
    api_key = os.environ.get("API_KEY")
    result = helper.process_data()
    return {"api_key": bool(api_key), "result": result}


if __name__ == "__main__":
    print(main())

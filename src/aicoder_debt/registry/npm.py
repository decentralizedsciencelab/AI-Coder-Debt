"""npm registry checker for package existence verification."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import quote

import requests

from ..constants import REGISTRY_CACHE_TTL, REGISTRY_TIMEOUT


class NpmRegistry:
    """Check package existence on npm registry."""

    BASE_URL = "https://registry.npmjs.org"

    def __init__(self, timeout: int = REGISTRY_TIMEOUT) -> None:
        """Initialize the npm registry checker.

        Args:
            timeout: Request timeout in seconds.
        """
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "aicoder-debt/0.1.0",
        })

    def package_exists(self, package_name: str) -> bool:
        """Check if a package exists on npm.

        Args:
            package_name: Name of the package to check.

        Returns:
            True if the package exists.
        """
        return self._cached_check(package_name)

    @lru_cache(maxsize=1000)
    def _cached_check(self, package_name: str) -> bool:
        """Cached package existence check.

        Args:
            package_name: Name of the package to check.

        Returns:
            True if the package exists.
        """
        # Handle scoped packages (e.g., @scope/package)
        encoded_name = quote(package_name, safe="@")

        try:
            url = f"{self.BASE_URL}/{encoded_name}"
            response = self._session.head(url, timeout=self.timeout)
            return response.status_code == 200
        except requests.RequestException:
            # On network error, assume package exists to avoid false positives
            return True

    def get_package_info(self, package_name: str) -> dict[str, Any] | None:
        """Get package information from npm.

        Args:
            package_name: Name of the package.

        Returns:
            Package info dict or None if not found.
        """
        encoded_name = quote(package_name, safe="@")

        try:
            url = f"{self.BASE_URL}/{encoded_name}"
            response = self._session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException:
            return None

    def clear_cache(self) -> None:
        """Clear the package existence cache."""
        self._cached_check.cache_clear()

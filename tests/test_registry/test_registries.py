"""Tests for registry checkers."""

from unittest.mock import MagicMock, patch

import pytest

from aicoder_debt.registry.npm import NpmRegistry
from aicoder_debt.registry.pypi import PyPIRegistry


class TestPyPIRegistry:
    """Tests for PyPI registry checker."""

    def test_normalize_name(self) -> None:
        """Test package name normalization."""
        registry = PyPIRegistry()

        assert registry._normalize_name("My-Package") == "my-package"
        assert registry._normalize_name("my_package") == "my-package"
        assert registry._normalize_name("MyPackage") == "mypackage"

    @patch("aicoder_debt.registry.pypi.requests.Session.head")
    def test_package_exists_true(self, mock_head: MagicMock) -> None:
        """Test package existence check returns True."""
        mock_head.return_value.status_code = 200

        registry = PyPIRegistry()
        registry.clear_cache()
        result = registry.package_exists("requests")

        assert result is True
        mock_head.assert_called_once()

    @patch("aicoder_debt.registry.pypi.requests.Session.head")
    def test_package_exists_false(self, mock_head: MagicMock) -> None:
        """Test package existence check returns False."""
        mock_head.return_value.status_code = 404

        registry = PyPIRegistry()
        registry.clear_cache()
        result = registry.package_exists("nonexistent-package-xyz-123")

        assert result is False

    @patch("aicoder_debt.registry.pypi.requests.Session.head")
    def test_cache_works(self, mock_head: MagicMock) -> None:
        """Test that caching prevents repeated requests."""
        mock_head.return_value.status_code = 200

        registry = PyPIRegistry()
        registry.clear_cache()

        # First call
        registry.package_exists("cached-package")
        # Second call should use cache
        registry.package_exists("cached-package")

        assert mock_head.call_count == 1

    @patch("aicoder_debt.registry.pypi.requests.Session.head")
    def test_network_error_returns_true(self, mock_head: MagicMock) -> None:
        """Test that network errors return True to avoid false positives."""
        import requests

        mock_head.side_effect = requests.RequestException("Network error")

        registry = PyPIRegistry()
        registry.clear_cache()
        result = registry.package_exists("error-package")

        # Should return True on error to avoid false positives
        assert result is True


class TestNpmRegistry:
    """Tests for npm registry checker."""

    @patch("aicoder_debt.registry.npm.requests.Session.head")
    def test_package_exists_true(self, mock_head: MagicMock) -> None:
        """Test package existence check returns True."""
        mock_head.return_value.status_code = 200

        registry = NpmRegistry()
        registry.clear_cache()
        result = registry.package_exists("express")

        assert result is True

    @patch("aicoder_debt.registry.npm.requests.Session.head")
    def test_scoped_package(self, mock_head: MagicMock) -> None:
        """Test scoped package URL encoding."""
        mock_head.return_value.status_code = 200

        registry = NpmRegistry()
        registry.clear_cache()
        registry.package_exists("@angular/core")

        # Should encode @ symbol properly
        call_url = mock_head.call_args[0][0]
        assert "@angular" in call_url or "%40angular" in call_url

    @patch("aicoder_debt.registry.npm.requests.Session.head")
    def test_package_exists_false(self, mock_head: MagicMock) -> None:
        """Test package existence check returns False."""
        mock_head.return_value.status_code = 404

        registry = NpmRegistry()
        registry.clear_cache()
        result = registry.package_exists("nonexistent-pkg-xyz-abc-123")

        assert result is False

    @patch("aicoder_debt.registry.npm.requests.Session.head")
    def test_network_error_returns_true(self, mock_head: MagicMock) -> None:
        """Test that network errors return True to avoid false positives."""
        import requests

        mock_head.side_effect = requests.RequestException("Network error")

        registry = NpmRegistry()
        registry.clear_cache()
        result = registry.package_exists("error-package")

        assert result is True

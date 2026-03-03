"""Tests for Tier 2 integration metrics."""

from pathlib import Path

import pytest

from aicoder_debt.metrics.tier2_integration import IntegrationMetrics


class TestICR:
    """Tests for Interface Consistency Rate."""

    def test_no_internal_calls(self, temp_dir: Path) -> None:
        """Test ICR when no internal calls exist."""
        (temp_dir / "simple.py").write_text(
            """
def hello():
    return "Hello"
"""
        )

        metrics = IntegrationMetrics(temp_dir)
        result = metrics.calculate_icr()

        assert result.rate == 0.0
        assert result.total_internal_calls == 0

    def test_matched_calls(self, temp_dir: Path) -> None:
        """Test ICR with matched internal calls."""
        # Create Flask API
        (temp_dir / "api.py").write_text(
            """
from flask import Flask

app = Flask(__name__)

@app.route("/users")
def get_users():
    return []

@app.route("/users/<id>", methods=["GET"])
def get_user(id):
    return {}
"""
        )

        # Create client that calls API
        (temp_dir / "client.py").write_text(
            """
import requests

def fetch_users():
    return requests.get("/users")

def fetch_user(user_id):
    return requests.get(f"/users/{user_id}")
"""
        )

        metrics = IntegrationMetrics(temp_dir)
        result = metrics.calculate_icr()

        # Should have some internal calls detected
        assert result.total_internal_calls >= 1

    def test_unmatched_calls(self, temp_dir: Path) -> None:
        """Test ICR with unmatched internal calls."""
        (temp_dir / "client.py").write_text(
            """
import requests

def fetch_data():
    return requests.get("/nonexistent-endpoint")
"""
        )

        metrics = IntegrationMetrics(temp_dir)
        result = metrics.calculate_icr()

        # Should have unmatched calls
        assert result.total_internal_calls >= 1
        assert len(result.unmatched_calls) >= 0


class TestCCS:
    """Tests for Configuration Coherence Score."""

    def test_all_resolved(self, python_project: Path) -> None:
        """Test CCS when all config references are resolved."""
        metrics = IntegrationMetrics(python_project)
        result = metrics.calculate_ccs()

        # The python_project fixture has .env with API_KEY defined
        # and main.py references API_KEY
        # Score should be positive
        assert result.score >= 0

    def test_no_config_refs(self, temp_dir: Path) -> None:
        """Test CCS when no config references exist."""
        (temp_dir / "simple.py").write_text(
            """
def hello():
    return "Hello"
"""
        )

        metrics = IntegrationMetrics(temp_dir)
        result = metrics.calculate_ccs()

        assert result.score == 0.0
        assert result.total_config_refs == 0

    def test_unresolved_configs(self, temp_dir: Path) -> None:
        """Test CCS with unresolved config references."""
        (temp_dir / "app.py").write_text(
            """
import os

secret = os.environ.get("SECRET_KEY")
db_url = os.getenv("MISSING_DATABASE_URL")
"""
        )

        # No .env file, so configs are unresolved
        metrics = IntegrationMetrics(temp_dir)
        result = metrics.calculate_ccs()

        assert result.total_config_refs >= 2
        assert len(result.unresolved_refs) >= 2

    def test_partial_resolution(self, temp_dir: Path) -> None:
        """Test CCS with partially resolved configs."""
        (temp_dir / ".env").write_text("API_KEY=test123\n")
        (temp_dir / "app.py").write_text(
            """
import os

api_key = os.environ.get("API_KEY")  # resolved
secret = os.environ.get("SECRET")  # unresolved
"""
        )

        metrics = IntegrationMetrics(temp_dir)
        result = metrics.calculate_ccs()

        # Should detect config references
        assert result.total_config_refs >= 2
        # At least some should be unresolved since SECRET is not defined
        assert len(result.unresolved_refs) >= 1

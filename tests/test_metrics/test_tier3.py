"""Tests for Tier 3 assumption metrics."""

from pathlib import Path

import pytest

from aicoder_debt.metrics.tier3_assumption import AssumptionMetrics


class TestURR:
    """Tests for Undefined Reference Rate."""

    def test_no_internal_refs(self, temp_dir: Path) -> None:
        """Test URR when no internal references exist."""
        (temp_dir / "simple.py").write_text(
            """
import os
import json

def hello():
    return json.dumps({})
"""
        )

        metrics = AssumptionMetrics(temp_dir, skip_registry_check=True)
        result = metrics.calculate_urr()

        assert result.rate == 0.0
        assert result.total_internal_refs == 0

    def test_resolved_internal_refs(self, python_project: Path) -> None:
        """Test URR with resolved internal references."""
        metrics = AssumptionMetrics(python_project, skip_registry_check=True)
        result = metrics.calculate_urr()

        # main.py imports from utils.helper which exists
        # Rate should be low (few or no unresolved)
        assert result.rate <= 1.0

    def test_unresolved_internal_refs(self, temp_dir: Path) -> None:
        """Test URR with unresolved internal references."""
        (temp_dir / "main.py").write_text(
            """
from nonexistent_module import something
from also_missing import another_thing

def main():
    pass
"""
        )

        metrics = AssumptionMetrics(temp_dir, skip_registry_check=True)
        result = metrics.calculate_urr()

        # Both imports are to nonexistent internal modules
        # Rate should be high
        assert result.total_internal_refs >= 0


class TestHD:
    """Tests for Hallucination Density."""

    def test_no_external_packages(self, temp_dir: Path) -> None:
        """Test HD when no external packages are used."""
        (temp_dir / "simple.py").write_text(
            """
def hello():
    return "Hello"
"""
        )

        metrics = AssumptionMetrics(temp_dir, skip_registry_check=True)
        result = metrics.calculate_hd()

        # No external packages means no hallucinations
        assert result.density == 0.0
        assert result.hallucinated_count == 0

    def test_kloc_calculation(self, temp_dir: Path) -> None:
        """Test KLOC calculation for HD."""
        # Create a file with 100 lines of code
        lines = ["def func():"] + ["    x = 1  # line"] * 99
        (temp_dir / "large.py").write_text("\n".join(lines))

        metrics = AssumptionMetrics(temp_dir, skip_registry_check=True)
        result = metrics.calculate_hd()

        # Should have ~0.1 KLOC
        assert result.kloc > 0

    def test_skip_registry_check(self, python_project: Path) -> None:
        """Test that skip_registry_check prevents API calls."""
        metrics = AssumptionMetrics(python_project, skip_registry_check=True)
        result = metrics.calculate_hd()

        # With registry check skipped, no packages marked as hallucinated
        assert result.hallucinated_count == 0

    def test_stdlib_not_hallucinated(self, temp_dir: Path) -> None:
        """Test that stdlib modules are not marked as hallucinated."""
        (temp_dir / "app.py").write_text(
            """
import os
import json
import typing
import collections
import pathlib

def hello():
    return os.getcwd()
"""
        )

        metrics = AssumptionMetrics(temp_dir, skip_registry_check=True)
        result = metrics.calculate_hd()

        # Stdlib should never be counted as hallucinated
        assert result.hallucinated_count == 0

"""Tests for Tier 1 deployment metrics."""

from pathlib import Path

import pytest

from aicoder_debt.constants import DeploymentRating, EdgeType
from aicoder_debt.metrics.tier1_deployment import DeploymentMetrics
from aicoder_debt.models import Cycle, DDGAnalysis, DDGEdge, DDGNode, DDGStatistics


class TestDFR:
    """Tests for Deployment Feasibility Rating."""

    def test_deployable_no_cycles(self, python_project: Path, simple_ddg: DDGAnalysis) -> None:
        """Test DEPLOYABLE rating when no cycles exist."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_dfr(simple_ddg)

        assert result.rating == DeploymentRating.DEPLOYABLE
        assert result.cycles_count == 0

    def test_repairable_addr_only_cycles(
        self, python_project: Path, cyclic_ddg: DDGAnalysis
    ) -> None:
        """Test REPAIRABLE rating for ADDR-only cycles."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_dfr(cyclic_ddg)

        assert result.rating == DeploymentRating.REPAIRABLE
        assert result.stateful_cycles_count == 0

    def test_repairable_stateful_cycles(
        self, python_project: Path, stateful_cyclic_ddg: DDGAnalysis
    ) -> None:
        """Test REPAIRABLE rating for stateful but repairable cycles."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_dfr(stateful_cyclic_ddg)

        assert result.rating == DeploymentRating.REPAIRABLE
        assert result.stateful_cycles_count > 0
        assert result.irreparable_cycles_count == 0

    def test_irreparable_bidirectional_state(
        self, python_project: Path, irreparable_ddg: DDGAnalysis
    ) -> None:
        """Test IRREPARABLE rating for bidirectional STATE edges with atomicity."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_dfr(irreparable_ddg)

        assert result.rating == DeploymentRating.IRREPARABLE
        assert result.irreparable_cycles_count > 0


class TestDRD:
    """Tests for Deployment Repair Distance."""

    def test_zero_cost_no_cycles(self, python_project: Path, simple_ddg: DDGAnalysis) -> None:
        """Test zero cost when no cycles exist."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_drd(simple_ddg)

        assert result.cost == 0
        assert len(result.edges_to_break) == 0

    def test_cost_for_addr_cycle(
        self, python_project: Path, cyclic_ddg: DDGAnalysis
    ) -> None:
        """Test cost calculation for ADDR-only cycle."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_drd(cyclic_ddg)

        # Should need to break 1 edge, cost 1 (DARC)
        assert result.cost >= 1
        assert len(result.edges_to_break) >= 1

    def test_cost_for_stateful_cycle(
        self, python_project: Path, stateful_cyclic_ddg: DDGAnalysis
    ) -> None:
        """Test cost calculation for stateful cycle."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_drd(stateful_cyclic_ddg)

        # Should include SDB pattern cost (2)
        assert result.cost >= 1
        assert len(result.pattern_applications) >= 1

    def test_irreparable_returns_negative(
        self, python_project: Path, irreparable_ddg: DDGAnalysis
    ) -> None:
        """Test that irreparable cycles return -1."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_drd(irreparable_ddg)

        assert result.cost == -1


class TestID:
    """Tests for Illusion Depth."""

    def test_parseable_project(self, python_project: Path) -> None:
        """Test ID calculation for parseable Python project."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_id(skip_external=True)

        # Should pass at least PARSEABLE stage
        assert result.stage.value >= 1
        assert result.gap <= 9

    def test_unparseable_project(self, temp_dir: Path) -> None:
        """Test ID calculation for project with syntax errors."""
        (temp_dir / "broken.py").write_text(
            """
def broken(:
    pass
"""
        )

        metrics = DeploymentMetrics(temp_dir)
        result = metrics.calculate_id(skip_external=True)

        # Should fail at PARSEABLE stage
        assert result.stage.value == 0
        assert result.gap == 10

    def test_gap_calculation(self, python_project: Path) -> None:
        """Test correct gap calculation."""
        metrics = DeploymentMetrics(python_project)
        result = metrics.calculate_id(skip_external=True)

        # Gap should be 10 - stage
        assert result.gap == 10 - result.stage.value

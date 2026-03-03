"""Tests for main analyzer."""

from pathlib import Path

import pytest

from aicoder_debt.analyzer import AICoderDebtAnalyzer
from aicoder_debt.constants import DeploymentRating


class TestAICoderDebtAnalyzer:
    """Tests for main analyzer class."""

    def test_analyze_python_project(self, python_project: Path) -> None:
        """Test full analysis of Python project."""
        analyzer = AICoderDebtAnalyzer(
            skip_registry_check=True,
            skip_maintainability=False,
        )
        result = analyzer.analyze(python_project)

        # Check all tiers are present
        assert result.tier1 is not None
        assert result.tier2 is not None
        assert result.tier3 is not None
        assert result.tier4 is not None

        # Check basic sanity (handle macOS /private symlink)
        assert str(python_project) in result.project_path or result.project_path in str(python_project)
        assert result.timestamp is not None

    def test_analyze_with_skip_maintainability(self, python_project: Path) -> None:
        """Test analysis with maintainability metrics skipped."""
        analyzer = AICoderDebtAnalyzer(
            skip_registry_check=True,
            skip_maintainability=True,
        )
        result = analyzer.analyze(python_project)

        assert result.tier1 is not None
        assert result.tier2 is not None
        assert result.tier3 is not None
        assert result.tier4 is None

    def test_analyze_docker_project(self, docker_project: Path) -> None:
        """Test analysis of Docker project."""
        analyzer = AICoderDebtAnalyzer(skip_registry_check=True)
        result = analyzer.analyze(docker_project)

        # Should detect Docker services
        assert result.ddg.statistics.total_nodes > 0

    def test_analyze_mixed_project(self, mixed_project: Path) -> None:
        """Test analysis of mixed Python + Docker project."""
        analyzer = AICoderDebtAnalyzer(skip_registry_check=True)
        result = analyzer.analyze(mixed_project)

        # Should have nodes from both Python and Docker
        assert result.ddg.statistics.total_nodes > 0

    def test_nonexistent_path_raises(self) -> None:
        """Test that nonexistent path raises error."""
        analyzer = AICoderDebtAnalyzer()

        with pytest.raises(FileNotFoundError):
            analyzer.analyze("/nonexistent/path")

    def test_file_path_raises(self, python_project: Path) -> None:
        """Test that file path (not directory) raises error."""
        analyzer = AICoderDebtAnalyzer()

        with pytest.raises(NotADirectoryError):
            analyzer.analyze(python_project / "main.py")

    def test_individual_dfr(self, python_project: Path) -> None:
        """Test individual DFR calculation."""
        analyzer = AICoderDebtAnalyzer()
        result = analyzer.calculate_dfr(python_project)

        assert result.rating in [
            DeploymentRating.DEPLOYABLE,
            DeploymentRating.REPAIRABLE,
            DeploymentRating.IRREPARABLE,
        ]

    def test_individual_drd(self, python_project: Path) -> None:
        """Test individual DRD calculation."""
        analyzer = AICoderDebtAnalyzer()
        result = analyzer.calculate_drd(python_project)

        assert result.cost >= -1  # -1 for irreparable

    def test_individual_id(self, python_project: Path) -> None:
        """Test individual ID calculation."""
        analyzer = AICoderDebtAnalyzer()
        result = analyzer.calculate_id(python_project)

        assert 0 <= result.stage.value <= 10
        assert result.gap == 10 - result.stage.value

    def test_individual_icr(self, python_project: Path) -> None:
        """Test individual ICR calculation."""
        analyzer = AICoderDebtAnalyzer()
        result = analyzer.calculate_icr(python_project)

        assert 0.0 <= result.rate <= 1.0

    def test_individual_ccs(self, python_project: Path) -> None:
        """Test individual CCS calculation."""
        analyzer = AICoderDebtAnalyzer()
        result = analyzer.calculate_ccs(python_project)

        assert 0.0 <= result.score <= 1.0

    def test_individual_urr(self, python_project: Path) -> None:
        """Test individual URR calculation."""
        analyzer = AICoderDebtAnalyzer(skip_registry_check=True)
        result = analyzer.calculate_urr(python_project)

        assert 0.0 <= result.rate <= 1.0

    def test_individual_hd(self, python_project: Path) -> None:
        """Test individual HD calculation."""
        analyzer = AICoderDebtAnalyzer(skip_registry_check=True)
        result = analyzer.calculate_hd(python_project)

        assert result.density >= 0.0

    def test_individual_csd(self, python_project: Path) -> None:
        """Test individual CSD calculation."""
        analyzer = AICoderDebtAnalyzer()
        result = analyzer.calculate_csd(python_project)

        assert result.density >= 0.0

    def test_individual_ccx(self, python_project: Path) -> None:
        """Test individual CCX calculation."""
        analyzer = AICoderDebtAnalyzer()
        result = analyzer.calculate_ccx(python_project)

        assert result.average >= 0.0

    def test_get_summary(self, python_project: Path) -> None:
        """Test summary generation."""
        analyzer = AICoderDebtAnalyzer(skip_registry_check=True)
        result = analyzer.analyze(python_project)
        summary = analyzer.get_summary(result)

        assert summary.dfr in ["DEPLOYABLE", "REPAIRABLE", "IRREPARABLE"]
        assert 0.0 <= summary.icr <= 1.0
        assert 0.0 <= summary.ccs <= 1.0
        assert 0.0 <= summary.urr <= 1.0
        assert summary.hd >= 0.0

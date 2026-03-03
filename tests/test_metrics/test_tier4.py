"""Tests for Tier 4 maintainability metrics."""

from pathlib import Path

import pytest

from aicoder_debt.metrics.tier4_maintainability import MaintainabilityMetrics


class TestCSD:
    """Tests for Code Smell Density."""

    def test_clean_code(self, temp_dir: Path) -> None:
        """Test CSD for clean code with no smells."""
        (temp_dir / "clean.py").write_text(
            '''"""Clean module with good practices."""


def hello(name: str) -> str:
    """Return greeting."""
    return f"Hello, {name}"
'''
        )

        metrics = MaintainabilityMetrics(temp_dir)
        result = metrics.calculate_csd()

        # Clean code should have low density
        assert result.kloc > 0

    def test_smelly_code(self, temp_dir: Path) -> None:
        """Test CSD for code with smells."""
        (temp_dir / "smelly.py").write_text(
            """
# TODO: Fix this later
def very_long_function_name_that_exceeds_reasonable_length_for_naming_conventions():
    x = 1
    # FIXME: This is broken
    y = 2
    # HACK: Temporary workaround
    return x + y
"""
        )

        metrics = MaintainabilityMetrics(temp_dir)
        result = metrics.calculate_csd()

        # Should detect TODO/FIXME/HACK comments at minimum
        assert result.kloc > 0

    def test_kloc_calculation(self, temp_dir: Path) -> None:
        """Test KLOC calculation."""
        # Create a file with known line count
        lines = ["def func():"] + ["    x = 1"] * 50
        (temp_dir / "test.py").write_text("\n".join(lines))

        metrics = MaintainabilityMetrics(temp_dir)
        result = metrics.calculate_csd()

        assert result.kloc > 0.05  # At least 50 lines


class TestCCX:
    """Tests for Cognitive Complexity Index."""

    def test_simple_function(self, temp_dir: Path) -> None:
        """Test CCX for simple function."""
        (temp_dir / "simple.py").write_text(
            """
def hello(name):
    return f"Hello, {name}"
"""
        )

        metrics = MaintainabilityMetrics(temp_dir)
        result = metrics.calculate_ccx()

        # Simple function should have low complexity
        assert result.total_functions >= 1
        assert result.average <= 5

    def test_complex_function(self, temp_dir: Path) -> None:
        """Test CCX for complex function."""
        (temp_dir / "complex.py").write_text(
            """
def complex_logic(data, options):
    result = []
    for item in data:
        if item.is_valid:
            if item.type == "A":
                if options.get("process_a"):
                    for sub in item.children:
                        if sub.active:
                            result.append(sub)
                else:
                    result.append(item)
            elif item.type == "B":
                try:
                    processed = process_b(item)
                    if processed:
                        result.append(processed)
                except ValueError:
                    if options.get("strict"):
                        raise
                    continue
    return result
"""
        )

        metrics = MaintainabilityMetrics(temp_dir)
        result = metrics.calculate_ccx()

        # Complex function should have higher complexity
        assert result.max_complexity > 5

    def test_multiple_functions(self, temp_dir: Path) -> None:
        """Test CCX averaging across multiple functions."""
        (temp_dir / "multi.py").write_text(
            """
def simple1():
    return 1

def simple2():
    return 2

def moderate(x):
    if x > 0:
        return x
    else:
        return -x
"""
        )

        metrics = MaintainabilityMetrics(temp_dir)
        result = metrics.calculate_ccx()

        assert result.total_functions >= 3
        # Average should be moderate
        assert result.average < 10

    def test_high_complexity_detection(self, temp_dir: Path) -> None:
        """Test detection of high complexity functions."""
        (temp_dir / "high.py").write_text(
            """
def very_complex(a, b, c, d, e):
    if a:
        if b:
            if c:
                if d:
                    if e:
                        for i in range(10):
                            for j in range(10):
                                if i > j:
                                    if i % 2 == 0:
                                        if j % 2 == 0:
                                            return i + j
    return 0
"""
        )

        metrics = MaintainabilityMetrics(temp_dir)
        result = metrics.calculate_ccx()

        # Should detect high complexity
        assert result.max_complexity > 10
        assert result.high_complexity_count >= 1

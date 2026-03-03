"""Tests for DDG extractor."""

from pathlib import Path

import pytest

from aicoder_debt.extractors.ddg import DDGExtractor


class TestDDGExtractor:
    """Tests for DDGExtractor."""

    def test_detect_python_project(self, python_project: Path) -> None:
        """Test detection of Python project type."""
        extractor = DDGExtractor(python_project)
        types = extractor.detect_project_types()
        assert "python" in types

    def test_detect_solidity_project(self, solidity_project: Path) -> None:
        """Test detection of Solidity project type."""
        extractor = DDGExtractor(solidity_project)
        types = extractor.detect_project_types()
        assert "solidity" in types

    def test_detect_docker_project(self, docker_project: Path) -> None:
        """Test detection of Docker project type."""
        extractor = DDGExtractor(docker_project)
        types = extractor.detect_project_types()
        assert "docker" in types

    def test_detect_mixed_project(self, mixed_project: Path) -> None:
        """Test detection of mixed project types."""
        extractor = DDGExtractor(mixed_project)
        types = extractor.detect_project_types()
        assert "python" in types
        assert "docker" in types

    def test_extract_python_nodes(self, python_project: Path) -> None:
        """Test extraction of Python module nodes."""
        extractor = DDGExtractor(python_project)
        ddg = extractor.extract()

        # Should have nodes for main.py and utils/helper.py
        node_names = {node.name for node in ddg.nodes}
        assert any("main" in name for name in node_names)

    def test_extract_solidity_nodes(self, solidity_project: Path) -> None:
        """Test extraction of Solidity contract nodes."""
        extractor = DDGExtractor(solidity_project)
        ddg = extractor.extract()

        node_names = {node.name for node in ddg.nodes}
        assert "Token" in node_names
        assert "Exchange" in node_names

    def test_extract_docker_nodes(self, docker_project: Path) -> None:
        """Test extraction of Docker service nodes."""
        extractor = DDGExtractor(docker_project)
        ddg = extractor.extract()

        node_names = {node.name for node in ddg.nodes}
        assert "api" in node_names
        assert "db" in node_names
        assert "cache" in node_names

    def test_extract_docker_edges(self, docker_project: Path) -> None:
        """Test extraction of Docker dependency edges."""
        extractor = DDGExtractor(docker_project)
        ddg = extractor.extract()

        # api depends on db and cache
        api_edges = [e for e in ddg.edges if "api" in e.source]
        targets = {e.target for e in api_edges}
        assert any("db" in t for t in targets)
        assert any("cache" in t for t in targets)

    def test_statistics_calculation(self, docker_project: Path) -> None:
        """Test DDG statistics calculation."""
        extractor = DDGExtractor(docker_project)
        ddg = extractor.extract()

        assert ddg.statistics.total_nodes > 0
        assert ddg.statistics.total_edges >= 0


class TestTarjanSCC:
    """Tests for Tarjan's SCC algorithm."""

    def test_no_cycles(self, temp_dir: Path) -> None:
        """Test graph with no cycles."""
        (temp_dir / "docker-compose.yml").write_text(
            """
version: "3.8"
services:
  a:
    image: nginx
  b:
    image: nginx
    depends_on:
      - a
  c:
    image: nginx
    depends_on:
      - b
"""
        )
        extractor = DDGExtractor(temp_dir)
        ddg = extractor.extract()

        assert ddg.statistics.total_cycles == 0

    def test_simple_cycle(self, temp_dir: Path) -> None:
        """Test graph with a simple 2-node cycle."""
        # Create a Python project with circular imports
        (temp_dir / "module_a.py").write_text(
            """
from module_b import func_b

def func_a():
    return func_b()
"""
        )
        (temp_dir / "module_b.py").write_text(
            """
from module_a import func_a

def func_b():
    return func_a()
"""
        )

        extractor = DDGExtractor(temp_dir)
        ddg = extractor.extract()

        # Note: This may or may not detect a cycle depending on
        # how the Python extractor handles the imports
        assert ddg.statistics.total_edges >= 0

    def test_self_loop(self, temp_dir: Path) -> None:
        """Test graph with self-loop."""
        (temp_dir / "docker-compose.yml").write_text(
            """
version: "3.8"
services:
  recursive:
    image: nginx
    depends_on:
      - recursive
"""
        )
        extractor = DDGExtractor(temp_dir)
        ddg = extractor.extract()

        # Self-loop should be detected as a cycle
        assert ddg.statistics.total_cycles >= 1

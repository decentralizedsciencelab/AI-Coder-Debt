"""Tests for Python extractor."""

from pathlib import Path

import pytest

from aicoder_debt.extractors.python_analyzer import PythonExtractor


class TestPythonExtractor:
    """Tests for PythonExtractor."""

    def test_extract_nodes(self, python_project: Path) -> None:
        """Test extraction of Python module nodes."""
        extractor = PythonExtractor(python_project)
        nodes = extractor.extract_nodes()

        assert len(nodes) >= 2  # main.py and utils/helper.py
        node_ids = {node.id for node in nodes}
        assert any("main" in nid for nid in node_ids)

    def test_extract_import_edges(self, python_project: Path) -> None:
        """Test extraction of import edges."""
        extractor = PythonExtractor(python_project)
        nodes = extractor.extract_nodes()
        edges = extractor.extract_edges(nodes)

        # main.py imports from utils
        assert len(edges) >= 1

    def test_module_type_detection(self, temp_dir: Path) -> None:
        """Test module type detection."""
        # Create a Flask app
        (temp_dir / "app.py").write_text(
            """
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello"
"""
        )

        extractor = PythonExtractor(temp_dir)
        nodes = extractor.extract_nodes()

        app_node = next((n for n in nodes if "app" in n.name), None)
        assert app_node is not None
        assert app_node.type == "api"

    def test_database_connection_detection(self, temp_dir: Path) -> None:
        """Test database connection pattern detection."""
        (temp_dir / "db.py").write_text(
            """
from sqlalchemy import create_engine

engine = create_engine("postgresql://localhost/test")
"""
        )

        extractor = PythonExtractor(temp_dir)
        nodes = extractor.extract_nodes()

        db_node = next((n for n in nodes if "db" in n.name), None)
        assert db_node is not None
        assert db_node.type == "database"

    def test_metadata_extraction(self, python_project: Path) -> None:
        """Test metadata extraction from modules."""
        extractor = PythonExtractor(python_project)
        nodes = extractor.extract_nodes()

        main_node = next((n for n in nodes if "main" in n.name), None)
        assert main_node is not None
        assert "functions" in main_node.metadata
        assert "imports" in main_node.metadata

"""Tests for CLI commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from aicoder_debt.cli import main


class TestCLI:
    """Tests for CLI commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_version(self, runner: CliRunner) -> None:
        """Test version command."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_list_metrics(self, runner: CliRunner) -> None:
        """Test list-metrics command."""
        result = runner.invoke(main, ["list-metrics"])
        assert result.exit_code == 0
        assert "DFR" in result.output
        assert "DRD" in result.output
        assert "ICR" in result.output

    def test_analyze_table(self, runner: CliRunner, python_project: Path) -> None:
        """Test analyze command with table output."""
        result = runner.invoke(
            main,
            [
                "analyze",
                str(python_project),
                "--format",
                "table",
                "--skip-registry-check",
            ],
        )
        assert result.exit_code == 0
        assert "DFR" in result.output

    def test_analyze_json(self, runner: CliRunner, python_project: Path) -> None:
        """Test analyze command with JSON output."""
        result = runner.invoke(
            main,
            [
                "analyze",
                str(python_project),
                "--format",
                "json",
                "--skip-registry-check",
            ],
        )
        assert result.exit_code == 0

        # Should be valid JSON
        data = json.loads(result.output)
        assert "tier1" in data
        assert "tier2" in data
        assert "tier3" in data

    def test_analyze_json_output_file(
        self, runner: CliRunner, python_project: Path, temp_dir: Path
    ) -> None:
        """Test analyze command with JSON output to file."""
        output_file = temp_dir / "report.json"
        result = runner.invoke(
            main,
            [
                "analyze",
                str(python_project),
                "--format",
                "json",
                "--output",
                str(output_file),
                "--skip-registry-check",
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

        # Verify file contents
        data = json.loads(output_file.read_text())
        assert "tier1" in data

    def test_analyze_markdown(self, runner: CliRunner, python_project: Path) -> None:
        """Test analyze command with Markdown output."""
        result = runner.invoke(
            main,
            [
                "analyze",
                str(python_project),
                "--format",
                "markdown",
                "--skip-registry-check",
            ],
        )
        assert result.exit_code == 0
        assert "# AI Coder Debt Analysis Report" in result.output

    def test_analyze_html(self, runner: CliRunner, python_project: Path) -> None:
        """Test analyze command with HTML output."""
        result = runner.invoke(
            main,
            [
                "analyze",
                str(python_project),
                "--format",
                "html",
                "--skip-registry-check",
            ],
        )
        assert result.exit_code == 0
        assert "<html" in result.output

    def test_dfr_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test dfr command."""
        result = runner.invoke(main, ["dfr", str(python_project)])
        assert result.exit_code == 0
        assert "DFR" in result.output

    def test_drd_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test drd command."""
        result = runner.invoke(main, ["drd", str(python_project)])
        assert result.exit_code == 0
        assert "DRD" in result.output

    def test_id_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test id command."""
        result = runner.invoke(main, ["id", str(python_project)])
        assert result.exit_code == 0
        assert "ID" in result.output

    def test_icr_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test icr command."""
        result = runner.invoke(main, ["icr", str(python_project)])
        assert result.exit_code == 0
        assert "ICR" in result.output

    def test_ccs_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test ccs command."""
        result = runner.invoke(main, ["ccs", str(python_project)])
        assert result.exit_code == 0
        assert "CCS" in result.output

    def test_urr_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test urr command."""
        result = runner.invoke(main, ["urr", str(python_project)])
        assert result.exit_code == 0
        assert "URR" in result.output

    def test_hd_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test hd command."""
        result = runner.invoke(
            main, ["hd", str(python_project), "--skip-registry-check"]
        )
        assert result.exit_code == 0
        assert "HD" in result.output

    def test_csd_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test csd command."""
        result = runner.invoke(main, ["csd", str(python_project)])
        assert result.exit_code == 0
        assert "CSD" in result.output

    def test_ccx_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test ccx command."""
        result = runner.invoke(main, ["ccx", str(python_project)])
        assert result.exit_code == 0
        assert "CCX" in result.output

    def test_extract_ddg_command(self, runner: CliRunner, python_project: Path) -> None:
        """Test extract-ddg command."""
        result = runner.invoke(main, ["extract-ddg", str(python_project)])
        assert result.exit_code == 0
        assert "Nodes" in result.output

    def test_extract_ddg_json_output(
        self, runner: CliRunner, python_project: Path, temp_dir: Path
    ) -> None:
        """Test extract-ddg command with JSON output."""
        output_file = temp_dir / "ddg.json"
        result = runner.invoke(
            main, ["extract-ddg", str(python_project), "-o", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert "nodes" in data
        assert "edges" in data

    def test_nonexistent_path_error(self, runner: CliRunner) -> None:
        """Test error on nonexistent path."""
        result = runner.invoke(main, ["analyze", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_skip_maintainability_flag(
        self, runner: CliRunner, python_project: Path
    ) -> None:
        """Test --skip-maintainability flag."""
        result = runner.invoke(
            main,
            [
                "analyze",
                str(python_project),
                "--format",
                "json",
                "--skip-registry-check",
                "--skip-maintainability",
            ],
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["tier4"] is None

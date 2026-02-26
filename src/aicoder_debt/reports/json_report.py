"""JSON report generator for AI Coder Debt analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import AnalysisResult


class JSONReportGenerator:
    """Generate JSON reports from analysis results."""

    def __init__(self, indent: int = 2) -> None:
        """Initialize the JSON report generator.

        Args:
            indent: JSON indentation level.
        """
        self.indent = indent

    def generate(self, result: "AnalysisResult") -> str:
        """Generate JSON report string.

        Args:
            result: Analysis result to format.

        Returns:
            JSON string.
        """
        return result.model_dump_json(indent=self.indent)

    def save(self, result: "AnalysisResult", output_path: str | Path) -> None:
        """Save JSON report to file.

        Args:
            result: Analysis result to save.
            output_path: Path to output file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.generate(result), encoding="utf-8")

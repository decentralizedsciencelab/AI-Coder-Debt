"""Markdown report generator for AI Coder Debt analysis."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import AnalysisResult


class MarkdownReportGenerator:
    """Generate Markdown reports from analysis results."""

    def generate(self, result: "AnalysisResult") -> str:
        """Generate Markdown report string.

        Args:
            result: Analysis result to format.

        Returns:
            Markdown string.
        """
        lines: list[str] = []

        # Header
        lines.append("# AI Coder Debt Analysis Report")
        lines.append("")
        lines.append(f"**Project:** `{result.project_path}`")
        lines.append(f"**Timestamp:** {result.timestamp}")
        lines.append("")

        # Summary Table
        lines.append("## Metrics Summary")
        lines.append("")
        lines.append("| Tier | Metric | Value | Description |")
        lines.append("|------|--------|-------|-------------|")

        # Tier 1
        lines.append(
            f"| 1 | DFR | **{result.tier1.dfr.rating.value}** | "
            f"Deployment Feasibility Rating |"
        )
        drd_value = result.tier1.drd.cost
        drd_display = str(drd_value) if drd_value >= 0 else "IRREPARABLE"
        lines.append(
            f"| 1 | DRD | {drd_display} | Deployment Repair Distance |"
        )
        lines.append(
            f"| 1 | ID | {result.tier1.id.stage.value} (gap: {result.tier1.id.gap}) | "
            f"Illusion Depth ({result.tier1.id.stage_name}) |"
        )

        # Tier 2
        lines.append(
            f"| 2 | ICR | {result.tier2.icr.rate:.2f} | Interface Consistency Rate |"
        )
        lines.append(
            f"| 2 | CCS | {result.tier2.ccs.score:.2f} | Configuration Coherence Score |"
        )

        # Tier 3
        lines.append(
            f"| 3 | URR | {result.tier3.urr.rate:.2f} | Undefined Reference Rate |"
        )
        lines.append(
            f"| 3 | HD | {result.tier3.hd.density:.2f} | "
            f"Hallucination Density (per KLOC) |"
        )

        # Tier 4 (optional)
        if result.tier4:
            lines.append(
                f"| 4 | CSD | {result.tier4.csd.density:.2f} | "
                f"Code Smell Density (per KLOC) |"
            )
            lines.append(
                f"| 4 | CCX | {result.tier4.ccx.average:.2f} | "
                f"Cognitive Complexity Index |"
            )

        lines.append("")

        # DDG Statistics
        lines.append("## Deployment Dependency Graph")
        lines.append("")
        stats = result.ddg.statistics
        lines.append(f"- **Total Nodes:** {stats.total_nodes}")
        lines.append(f"- **Total Edges:** {stats.total_edges}")
        lines.append(f"  - ADDR edges: {stats.addr_edges}")
        lines.append(f"  - STATE edges: {stats.state_edges}")
        lines.append(f"  - RUNTIME edges: {stats.runtime_edges}")
        lines.append(f"- **Cycles:** {stats.total_cycles}")
        lines.append(f"  - Stateful cycles: {stats.stateful_cycles}")
        lines.append(f"  - Irreparable cycles: {stats.irreparable_cycles}")
        lines.append("")

        # DFR Details
        lines.append("## Tier 1: Deployment Metrics")
        lines.append("")
        lines.append("### DFR - Deployment Feasibility Rating")
        lines.append("")
        lines.append(f"**Rating:** {result.tier1.dfr.rating.value}")
        lines.append(f"**Reason:** {result.tier1.dfr.reason}")
        lines.append("")

        # DRD Details
        lines.append("### DRD - Deployment Repair Distance")
        lines.append("")
        if result.tier1.drd.cost >= 0:
            lines.append(f"**Cost:** {result.tier1.drd.cost}")
            if result.tier1.drd.pattern_applications:
                lines.append("")
                lines.append("**Repair Patterns:**")
                for pattern in result.tier1.drd.pattern_applications:
                    lines.append(f"- {pattern}")
        else:
            lines.append("**Status:** IRREPARABLE")
        lines.append("")

        # ID Details
        lines.append("### ID - Illusion Depth")
        lines.append("")
        lines.append(f"**Highest Stage Passed:** {result.tier1.id.stage_name} ({result.tier1.id.stage.value})")
        lines.append(f"**Gap from Deployment:** {result.tier1.id.gap}")
        lines.append("")

        # Tier 2 Details
        lines.append("## Tier 2: Integration Metrics")
        lines.append("")

        # ICR Details
        lines.append("### ICR - Interface Consistency Rate")
        lines.append("")
        lines.append(f"**Rate:** {result.tier2.icr.rate:.2%}")
        lines.append(f"**Matched Calls:** {result.tier2.icr.matched_calls} / {result.tier2.icr.total_internal_calls}")
        if result.tier2.icr.unmatched_calls:
            lines.append("")
            lines.append("**Unmatched Calls:**")
            for call in result.tier2.icr.unmatched_calls[:10]:  # Limit to 10
                lines.append(f"- `{call.method} {call.endpoint}` at {call.file_path}:{call.line_number}")
            if len(result.tier2.icr.unmatched_calls) > 10:
                lines.append(f"- ... and {len(result.tier2.icr.unmatched_calls) - 10} more")
        lines.append("")

        # CCS Details
        lines.append("### CCS - Configuration Coherence Score")
        lines.append("")
        lines.append(f"**Score:** {result.tier2.ccs.score:.2%}")
        lines.append(f"**Resolved:** {result.tier2.ccs.resolved_configs} / {result.tier2.ccs.total_config_refs}")
        if result.tier2.ccs.unresolved_refs:
            lines.append("")
            lines.append("**Unresolved Config References:**")
            for ref in result.tier2.ccs.unresolved_refs[:10]:
                lines.append(f"- `{ref.key}` at {ref.file_path}:{ref.line_number}")
            if len(result.tier2.ccs.unresolved_refs) > 10:
                lines.append(f"- ... and {len(result.tier2.ccs.unresolved_refs) - 10} more")
        lines.append("")

        # Tier 3 Details
        lines.append("## Tier 3: Assumption Metrics")
        lines.append("")

        # URR Details
        lines.append("### URR - Undefined Reference Rate")
        lines.append("")
        lines.append(f"**Rate:** {result.tier3.urr.rate:.2%}")
        lines.append(f"**Unresolved:** {result.tier3.urr.unresolved_refs} / {result.tier3.urr.total_internal_refs}")
        if result.tier3.urr.unresolved_list:
            lines.append("")
            lines.append("**Unresolved References:**")
            for ref in result.tier3.urr.unresolved_list[:10]:
                lines.append(f"- `{ref.module}` at {ref.file_path}:{ref.line_number}")
            if len(result.tier3.urr.unresolved_list) > 10:
                lines.append(f"- ... and {len(result.tier3.urr.unresolved_list) - 10} more")
        lines.append("")

        # HD Details
        lines.append("### HD - Hallucination Density")
        lines.append("")
        lines.append(f"**Density:** {result.tier3.hd.density:.2f} per KLOC")
        lines.append(f"**Hallucinated Packages:** {result.tier3.hd.hallucinated_count} / {result.tier3.hd.total_packages}")
        lines.append(f"**KLOC:** {result.tier3.hd.kloc:.2f}")
        if result.tier3.hd.hallucinated_packages:
            lines.append("")
            lines.append("**Hallucinated Packages:**")
            for pkg in result.tier3.hd.hallucinated_packages[:10]:
                lines.append(f"- `{pkg.package_name}` ({pkg.ecosystem}) at {pkg.file_path}:{pkg.line_number}")
            if len(result.tier3.hd.hallucinated_packages) > 10:
                lines.append(f"- ... and {len(result.tier3.hd.hallucinated_packages) - 10} more")
        lines.append("")

        # Tier 4 Details (if present)
        if result.tier4:
            lines.append("## Tier 4: Maintainability Metrics")
            lines.append("")

            # CSD Details
            lines.append("### CSD - Code Smell Density")
            lines.append("")
            lines.append(f"**Density:** {result.tier4.csd.density:.2f} per KLOC")
            lines.append(f"**Total Issues:** {result.tier4.csd.total_issues}")
            lines.append(f"**KLOC:** {result.tier4.csd.kloc:.2f}")
            if result.tier4.csd.by_severity:
                lines.append("")
                lines.append("**Issues by Severity:**")
                for severity, count in sorted(result.tier4.csd.by_severity.items()):
                    lines.append(f"- {severity}: {count}")
            lines.append("")

            # CCX Details
            lines.append("### CCX - Cognitive Complexity Index")
            lines.append("")
            lines.append(f"**Average:** {result.tier4.ccx.average:.2f}")
            lines.append(f"**Max Complexity:** {result.tier4.ccx.max_complexity}")
            lines.append(f"**Total Functions:** {result.tier4.ccx.total_functions}")
            lines.append(f"**High Complexity (>10):** {result.tier4.ccx.high_complexity_count}")
            if result.tier4.ccx.functions:
                high_complexity = [f for f in result.tier4.ccx.functions if f.complexity > 10]
                if high_complexity:
                    lines.append("")
                    lines.append("**High Complexity Functions:**")
                    for func in sorted(high_complexity, key=lambda x: -x.complexity)[:10]:
                        lines.append(
                            f"- `{func.function_name}` (complexity: {func.complexity}) "
                            f"at {func.file_path}:{func.line_number}"
                        )
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("*Generated by aicoder-debt*")

        return "\n".join(lines)

    def save(self, result: "AnalysisResult", output_path: str | Path) -> None:
        """Save Markdown report to file.

        Args:
            result: Analysis result to save.
            output_path: Path to output file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.generate(result), encoding="utf-8")

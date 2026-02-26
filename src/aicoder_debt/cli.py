"""CLI interface for AI Coder Debt analysis."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .analyzer import AICoderDebtAnalyzer
from .models import AnalysisResult
from .reports.html_report import HTMLReportGenerator
from .reports.json_report import JSONReportGenerator
from .reports.markdown_report import MarkdownReportGenerator

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="aicoder-debt")
def main() -> None:
    """AI Coder Debt - Metrics for LLM-generated multi-component systems."""
    pass


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json", "markdown", "html"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path",
)
@click.option(
    "--skip-registry-check",
    is_flag=True,
    help="Skip npm/PyPI package verification",
)
@click.option(
    "--skip-maintainability",
    is_flag=True,
    help="Skip Tier 4 maintainability metrics",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed progress",
)
def analyze(
    project_path: str,
    output_format: str,
    output: Optional[str],
    skip_registry_check: bool,
    skip_maintainability: bool,
    verbose: bool,
) -> None:
    """Run full analysis on a project."""
    try:
        analyzer = AICoderDebtAnalyzer(
            skip_registry_check=skip_registry_check,
            skip_maintainability=skip_maintainability,
        )

        if verbose:
            console.print(f"[bold]Analyzing:[/bold] {project_path}")

        with console.status("[bold green]Analyzing project...") as status:
            if verbose:
                status.update("[bold green]Extracting DDG...")
            result = analyzer.analyze(project_path)

        # Output results
        if output_format == "table":
            _print_table(result)
        elif output_format == "json":
            report = JSONReportGenerator().generate(result)
            if output:
                Path(output).write_text(report, encoding="utf-8")
                console.print(f"[green]Report saved to {output}[/green]")
            else:
                console.print(report)
        elif output_format == "markdown":
            report = MarkdownReportGenerator().generate(result)
            if output:
                Path(output).write_text(report, encoding="utf-8")
                console.print(f"[green]Report saved to {output}[/green]")
            else:
                console.print(report)
        elif output_format == "html":
            report = HTMLReportGenerator().generate(result)
            if output:
                Path(output).write_text(report, encoding="utf-8")
                console.print(f"[green]Report saved to {output}[/green]")
            else:
                console.print(report)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (JSON)",
)
def extract_ddg(project_path: str, output: Optional[str]) -> None:
    """Extract Deployment Dependency Graph only."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Extracting DDG..."):
            ddg = analyzer.extract_ddg(project_path)

        if output:
            import json

            Path(output).write_text(
                json.dumps(ddg.model_dump(), indent=2), encoding="utf-8"
            )
            console.print(f"[green]DDG saved to {output}[/green]")
        else:
            console.print(f"Nodes: {ddg.statistics.total_nodes}")
            console.print(f"Edges: {ddg.statistics.total_edges}")
            console.print(f"Cycles: {ddg.statistics.total_cycles}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def dfr(project_path: str) -> None:
    """Calculate Deployment Feasibility Rating (DFR)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating DFR..."):
            result = analyzer.calculate_dfr(project_path)

        color = {
            "DEPLOYABLE": "green",
            "REPAIRABLE": "yellow",
            "IRREPARABLE": "red",
        }.get(result.rating.value, "white")

        console.print(f"[bold]DFR:[/bold] [{color}]{result.rating.value}[/{color}]")
        console.print(f"[dim]Reason: {result.reason}[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def drd(project_path: str) -> None:
    """Calculate Deployment Repair Distance (DRD)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating DRD..."):
            result = analyzer.calculate_drd(project_path)

        if result.cost >= 0:
            console.print(f"[bold]DRD:[/bold] {result.cost}")
            if result.pattern_applications:
                console.print("[bold]Repair patterns:[/bold]")
                for pattern in result.pattern_applications:
                    console.print(f"  - {pattern}")
        else:
            console.print("[bold]DRD:[/bold] [red]IRREPARABLE[/red]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command("id")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def illusion_depth(project_path: str) -> None:
    """Calculate Illusion Depth (ID)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating ID..."):
            result = analyzer.calculate_id(project_path)

        console.print(
            f"[bold]ID:[/bold] Stage {result.stage.value} ({result.stage_name})"
        )
        console.print(f"[bold]Gap:[/bold] {result.gap}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def icr(project_path: str) -> None:
    """Calculate Interface Consistency Rate (ICR)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating ICR..."):
            result = analyzer.calculate_icr(project_path)

        console.print(f"[bold]ICR:[/bold] {result.rate:.2%}")
        console.print(
            f"[dim]Matched: {result.matched_calls}/{result.total_internal_calls}[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def ccs(project_path: str) -> None:
    """Calculate Configuration Coherence Score (CCS)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating CCS..."):
            result = analyzer.calculate_ccs(project_path)

        console.print(f"[bold]CCS:[/bold] {result.score:.2%}")
        console.print(
            f"[dim]Resolved: {result.resolved_configs}/{result.total_config_refs}[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def urr(project_path: str) -> None:
    """Calculate Undefined Reference Rate (URR)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating URR..."):
            result = analyzer.calculate_urr(project_path)

        console.print(f"[bold]URR:[/bold] {result.rate:.2%}")
        console.print(
            f"[dim]Unresolved: {result.unresolved_refs}/{result.total_internal_refs}[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--skip-registry-check",
    is_flag=True,
    help="Skip npm/PyPI package verification",
)
def hd(project_path: str, skip_registry_check: bool) -> None:
    """Calculate Hallucination Density (HD)."""
    try:
        analyzer = AICoderDebtAnalyzer(skip_registry_check=skip_registry_check)

        with console.status("[bold green]Calculating HD..."):
            result = analyzer.calculate_hd(project_path)

        console.print(f"[bold]HD:[/bold] {result.density:.2f} per KLOC")
        console.print(
            f"[dim]Hallucinated: {result.hallucinated_count}/{result.total_packages} packages[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def csd(project_path: str) -> None:
    """Calculate Code Smell Density (CSD)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating CSD..."):
            result = analyzer.calculate_csd(project_path)

        console.print(f"[bold]CSD:[/bold] {result.density:.2f} per KLOC")
        console.print(f"[dim]Total issues: {result.total_issues}[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def ccx(project_path: str) -> None:
    """Calculate Cognitive Complexity Index (CCX)."""
    try:
        analyzer = AICoderDebtAnalyzer()

        with console.status("[bold green]Calculating CCX..."):
            result = analyzer.calculate_ccx(project_path)

        console.print(f"[bold]CCX:[/bold] {result.average:.2f}")
        console.print(
            f"[dim]Max: {result.max_complexity}, High complexity: {result.high_complexity_count}[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
def list_metrics() -> None:
    """List all available metrics."""
    table = Table(title="AI Coder Debt Metrics")
    table.add_column("Tier", style="cyan")
    table.add_column("Metric", style="green")
    table.add_column("Description")
    table.add_column("Output")

    metrics = [
        ("1", "DFR", "Deployment Feasibility Rating", "DEPLOYABLE/REPAIRABLE/IRREPARABLE"),
        ("1", "DRD", "Deployment Repair Distance", "Cost (0+, or -1 if irreparable)"),
        ("1", "ID", "Illusion Depth", "Stage 0-10, gap from deployment"),
        ("2", "ICR", "Interface Consistency Rate", "0.0-1.0"),
        ("2", "CCS", "Configuration Coherence Score", "0.0-1.0"),
        ("3", "URR", "Undefined Reference Rate", "0.0-1.0"),
        ("3", "HD", "Hallucination Density", "count/KLOC"),
        ("4", "CSD", "Code Smell Density", "issues/KLOC"),
        ("4", "CCX", "Cognitive Complexity Index", "avg complexity"),
    ]

    for tier, metric, desc, output in metrics:
        table.add_row(tier, metric, desc, output)

    console.print(table)


def _print_table(result: AnalysisResult) -> None:
    """Print results as a Rich table.

    Args:
        result: Analysis result to display.
    """
    table = Table(title="AI Coder Debt Analysis Results")
    table.add_column("Tier", style="cyan")
    table.add_column("Metric", style="green")
    table.add_column("Value", style="bold")
    table.add_column("Details")

    # DFR
    dfr_color = {
        "DEPLOYABLE": "green",
        "REPAIRABLE": "yellow",
        "IRREPARABLE": "red",
    }.get(result.tier1.dfr.rating.value, "white")
    table.add_row(
        "1",
        "DFR",
        f"[{dfr_color}]{result.tier1.dfr.rating.value}[/{dfr_color}]",
        result.tier1.dfr.reason[:50] + "..."
        if len(result.tier1.dfr.reason) > 50
        else result.tier1.dfr.reason,
    )

    # DRD
    drd_value = result.tier1.drd.cost
    drd_display = str(drd_value) if drd_value >= 0 else "[red]IRREPARABLE[/red]"
    table.add_row("1", "DRD", drd_display, f"{len(result.tier1.drd.edges_to_break)} edges to break")

    # ID
    table.add_row(
        "1",
        "ID",
        f"{result.tier1.id.stage.value}",
        f"{result.tier1.id.stage_name} (gap: {result.tier1.id.gap})",
    )

    # ICR
    icr_color = "green" if result.tier2.icr.rate >= 0.8 else "yellow" if result.tier2.icr.rate >= 0.5 else "red"
    table.add_row(
        "2",
        "ICR",
        f"[{icr_color}]{result.tier2.icr.rate:.2f}[/{icr_color}]",
        f"{result.tier2.icr.matched_calls}/{result.tier2.icr.total_internal_calls} matched",
    )

    # CCS
    ccs_color = "green" if result.tier2.ccs.score >= 0.8 else "yellow" if result.tier2.ccs.score >= 0.5 else "red"
    table.add_row(
        "2",
        "CCS",
        f"[{ccs_color}]{result.tier2.ccs.score:.2f}[/{ccs_color}]",
        f"{result.tier2.ccs.resolved_configs}/{result.tier2.ccs.total_config_refs} resolved",
    )

    # URR
    urr_color = "green" if result.tier3.urr.rate <= 0.1 else "yellow" if result.tier3.urr.rate <= 0.3 else "red"
    table.add_row(
        "3",
        "URR",
        f"[{urr_color}]{result.tier3.urr.rate:.2f}[/{urr_color}]",
        f"{result.tier3.urr.unresolved_refs}/{result.tier3.urr.total_internal_refs} unresolved",
    )

    # HD
    hd_color = "green" if result.tier3.hd.density <= 1.0 else "yellow" if result.tier3.hd.density <= 5.0 else "red"
    table.add_row(
        "3",
        "HD",
        f"[{hd_color}]{result.tier3.hd.density:.2f}[/{hd_color}]",
        f"{result.tier3.hd.hallucinated_count} hallucinated, {result.tier3.hd.kloc:.1f} KLOC",
    )

    # Tier 4 (if present)
    if result.tier4:
        # CSD
        csd_color = "green" if result.tier4.csd.density <= 10 else "yellow" if result.tier4.csd.density <= 50 else "red"
        table.add_row(
            "4",
            "CSD",
            f"[{csd_color}]{result.tier4.csd.density:.2f}[/{csd_color}]",
            f"{result.tier4.csd.total_issues} issues, {result.tier4.csd.kloc:.1f} KLOC",
        )

        # CCX
        ccx_color = "green" if result.tier4.ccx.average <= 5 else "yellow" if result.tier4.ccx.average <= 10 else "red"
        table.add_row(
            "4",
            "CCX",
            f"[{ccx_color}]{result.tier4.ccx.average:.2f}[/{ccx_color}]",
            f"max: {result.tier4.ccx.max_complexity}, {result.tier4.ccx.high_complexity_count} high",
        )

    # Tier 5 (if present)
    if result.tier5 and result.tier5.drs:
        drs = result.tier5.drs
        drs_color = "green" if drs.score >= 0.8 else "yellow" if drs.score >= 0.5 else "red"
        table.add_row(
            "5",
            "DRS",
            f"[{drs_color}]{drs.score:.2f}[/{drs_color}]",
            f"{drs.passing_checks}/{drs.total_applicable} checks pass",
        )

    console.print(table)

    # DDG Summary
    stats = result.ddg.statistics
    console.print(f"\n[bold]DDG Summary:[/bold] {stats.total_nodes} nodes, {stats.total_edges} edges, {stats.total_cycles} cycles")

    # ACDS Composite Score
    from .analyzer import AICoderDebtAnalyzer
    acds = AICoderDebtAnalyzer.compute_acds(result)
    if acds is not None:
        acds_color = "green" if acds <= 0.3 else "yellow" if acds <= 0.6 else "red"
        console.print(f"\n[bold]AI Coder Debt Score (ACDS):[/bold] [{acds_color}]{acds:.1%}[/{acds_color}]")


if __name__ == "__main__":
    main()

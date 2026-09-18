"""CLI interface for AI Coder Debt analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .analyzer import AICoderDebtAnalyzer
from .levels import LevelScores, score_analysis
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
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Write the report to a file instead of stdout",
)
@click.option(
    "--judge/--no-judge",
    default=False,
    help="Run LLM-as-Judge for L4 (needs an API key; costs tokens)",
)
@click.option(
    "--sdd",
    type=float,
    default=None,
    help="Security debt density per KLOC, an optional L3 input",
)
@click.option(
    "--skip-maintainability",
    is_flag=True,
    help="Skip Tier 4 (radon/pylint); leaves L3 unmeasured",
)
def score(
    project_path: str,
    output_format: str,
    output: Optional[str],
    judge: bool,
    sdd: Optional[float],
    skip_maintainability: bool,
) -> None:
    """Score one system: per-level debt (L1-L4) and composite ACDS.

    Runs the tier metrics on PROJECT_PATH and folds them into the four
    level scores and the composite.  Levels whose inputs are unavailable
    are reported as unmeasured and excluded from ACDS.
    """
    try:
        analyzer = AICoderDebtAnalyzer(
            skip_maintainability=skip_maintainability,
        )
        with console.status("[bold green]Analyzing project..."):
            result = analyzer.analyze(project_path)

        judge_scores = None
        if judge:
            with console.status("[bold green]Running LLM-as-Judge..."):
                judge_scores = _run_judge(project_path)

        scores = score_analysis(result, judge=judge_scores, sdd=sdd)

        if output_format == "json":
            report = json.dumps(scores.to_dict(), indent=2)
        else:
            report = None
            _print_levels(scores)

        if output:
            if report is None:
                report = json.dumps(scores.to_dict(), indent=2)
            Path(output).write_text(report, encoding="utf-8")
            console.print(f"[green]Report saved to {output}[/green]")
        elif report is not None:
            click.echo(report)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def _run_judge(project_path: str) -> dict[str, float]:
    """Run all five LLM-as-Judge metrics, returning native-unit scores."""
    from .levels import NATIVE_MARKER
    from .metrics.llm_judge import LLMJudge

    judge = LLMJudge()
    report = judge.judge_all(project_path)
    scores: dict[str, float] = {NATIVE_MARKER: True}  # type: ignore[dict-item]
    for metric in (
        "defect_density", "vulnerability_density", "deployment_risk",
        "ownership_void", "specification_alignment",
    ):
        res = getattr(report, metric, None)
        if res is not None:
            scores[metric] = res.native_score
    return scores


_LEVEL_LABELS = [
    ("l1_debt", "L1", "System Existence", "1 - DRS"),
    ("l2_debt", "L2", "System Coherence", "mean(1-ICR, 1-CCS, URR)"),
    ("l3_debt", "L3", "Component Quality", "mean(CCX, CSD, SDD) capped"),
    ("l4_debt", "L4", "Traceability", "mean of 5 LLM-as-Judge metrics"),
]


def _print_levels(scores: LevelScores) -> None:
    """Render per-level debt as a table."""
    table = Table(title=f"AI Coder Debt — {scores.project_path}")
    table.add_column("Level", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Debt", justify="right")
    table.add_column("Formula", style="dim")

    for attr, tag, name, formula in _LEVEL_LABELS:
        value = getattr(scores, attr)
        if value is None:
            shown, style = "unmeasured", "yellow"
        else:
            shown = f"{value:.3f}"
            style = "red" if value >= 0.5 else "green"
        table.add_row(tag, name, f"[{style}]{shown}[/{style}]", formula)

    acds = scores.acds
    acds_shown = "unmeasured" if acds is None else f"{acds:.3f}"
    table.add_row(
        "ACDS", "Composite", f"[bold]{acds_shown}[/bold]",
        f"1 - prod(1 - L) over {scores.levels_measured} level(s)",
    )
    console.print(table)

    inputs = ", ".join(
        f"{k}={v:.3f}" for k, v in scores.inputs.items() if v is not None
    )
    if inputs:
        console.print(f"[dim]Inputs: {inputs}[/dim]")
    if scores.unavailable:
        console.print(
            f"[yellow]Unmeasured: {', '.join(scores.unavailable)}[/yellow] "
            "[dim](excluded from ACDS, not counted as zero debt)[/dim]"
        )


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


@main.command("ownership-signals")
@click.argument("project_path", type=click.Path(exists=True))
@click.option(
    "--children",
    is_flag=True,
    help="Treat each immediate subdirectory as a separate project.",
)
@click.option("--format", "output_format", type=click.Choice(["table", "json"]),
              default="table")
def ownership_signals(project_path: str, children: bool, output_format: str) -> None:
    """Report whether projects carry ownership metadata.

    The Ownership Void Index is defined over repository signals
    (CODEOWNERS entries, substantive edits by a distinct human author).
    This reports whether those signals exist; it does not estimate the
    index. A project without them is unmeasured by that definition, not
    maximally unowned.
    """
    from .ownership import survey_ownership_signals

    root = Path(project_path)
    if children:
        targets = sorted(d for d in root.iterdir() if d.is_dir())
    else:
        targets = [root]

    summary = survey_ownership_signals(targets)

    if output_format == "json":
        click.echo(json.dumps({
            "total": summary.total,
            "measurable": summary.measurable,
            "unmeasurable": summary.unmeasurable,
            "measurable_fraction": summary.measurable_fraction,
            "projects": [
                {
                    "path": s.path,
                    "has_git": s.has_git,
                    "commit_count": s.commit_count,
                    "distinct_authors": s.distinct_authors,
                    "has_codeowners": s.has_codeowners,
                    "measurable": s.measurable,
                    "reason": s.reason,
                }
                for s in summary.signals
            ],
        }, indent=2))
        return

    table = Table(title=f"Ownership signals - {root}")
    table.add_column("Project", style="cyan")
    table.add_column("Commits", justify="right")
    table.add_column("Authors", justify="right")
    table.add_column("CODEOWNERS", justify="center")
    table.add_column("Measurable", justify="center")
    table.add_column("Reason")

    for sig in summary.signals:
        table.add_row(
            Path(sig.path).name,
            str(sig.commit_count),
            str(sig.distinct_authors),
            "yes" if sig.has_codeowners else "-",
            "[green]yes[/green]" if sig.measurable else "[red]no[/red]",
            sig.reason,
        )

    console.print(table)
    frac = summary.measurable_fraction
    pct = "n/a" if frac is None else f"{frac:.1%}"
    console.print(
        f"Repository-based Ownership Void Index is computable for "
        f"{summary.measurable} of {summary.total} projects ({pct}). "
        f"The rest are unmeasured by that definition."
    )


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

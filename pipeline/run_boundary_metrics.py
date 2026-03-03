#!/usr/bin/env python3
"""
Batch runner: Tier 5 boundary checks + THI on the full corpus.

Runs all discovered systems through:
  1. The 12 boundary checks → DRS per system
  2. THI computation per (source) cohort
  3. Comparison table: existing tier metrics vs DRS
  4. CSV + markdown output

Usage:
    python pipeline/run_boundary_metrics.py [--data-root DATA] [--results-dir RESULTS]
"""

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aicoder_debt.metrics.tier5_boundary import (  # noqa: E402
    BoundaryMetrics,
    PythonBoundaryMetrics,
    compute_thi,
)

# ── Default corpus locations ──────────────────────────────────────────

DEFAULT_DATA_ROOT = Path("/Users/viraaji/2025_IdeaProj")
MA_PATH = DEFAULT_DATA_ROOT / "multi_agent_system" / "storage" / "projects"
BENCHMARK_PATH = DEFAULT_DATA_ROOT / "benchmark_projects" / "storage" / "projects"
BALANCED_PATH = DEFAULT_DATA_ROOT / "balanced_dataset" / "storage" / "projects"
HUMAN_PATH = DEFAULT_DATA_ROOT / "human_baseline" / "projects"
HUMAN_LOCAL_PATH = ROOT / "data" / "human_baseline"
AI_PYTHON_PATH = ROOT / "data" / "ai_python_baseline"
BENCHMARK_LOCAL_PATH = ROOT / "benchmark" / "outputs"


# ── Corpus discovery ──────────────────────────────────────────────────


def _discover(root: Path, label: str) -> list[tuple[Path, str]]:
    """Return (path, label) pairs for all project dirs under *root*."""
    if not root.exists():
        return []
    seen: set[Path] = set()
    results: list[tuple[Path, str]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.is_symlink():
            continue
        real = d.resolve()
        if real in seen:
            continue
        seen.add(real)
        results.append((d, label))
    return results


def _discover_benchmark(root: Path, label: str) -> list[tuple[Path, str]]:
    """Discover benchmark projects, preferring extracted/ subdir if present."""
    if not root.exists():
        return []
    results: list[tuple[Path, str]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.is_symlink():
            continue
        # Benchmark projects may have extracted/ subdir with the real code
        proj_path = d / "extracted" if (d / "extracted").is_dir() else d
        results.append((proj_path, label))
    return results


def discover_all(data_root: Path | None = None) -> list[tuple[Path, str]]:
    """Discover all projects across corpora."""
    if data_root:
        ma = data_root / "multi_agent_system" / "storage" / "projects"
        bench_ext = data_root / "benchmark_projects" / "storage" / "projects"
        bal = data_root / "balanced_dataset" / "storage" / "projects"
        human = data_root / "human_baseline" / "projects"
        human_local = data_root / "human_baseline"
        ai_py = data_root / "ai_python_baseline"
        bench_local = ROOT / "benchmark" / "outputs"
    else:
        ma, bench_ext, bal, human = MA_PATH, BENCHMARK_PATH, BALANCED_PATH, HUMAN_PATH
        human_local = HUMAN_LOCAL_PATH
        ai_py = AI_PYTHON_PATH
        bench_local = BENCHMARK_LOCAL_PATH

    projects: list[tuple[Path, str]] = []
    projects.extend(_discover(ma, "multi_agent"))
    # Try external benchmark path first, fall back to local benchmark/outputs
    bench_found = _discover_benchmark(bench_ext, "benchmark")
    if not bench_found:
        bench_found = _discover_benchmark(bench_local, "benchmark")
    projects.extend(bench_found)
    projects.extend(_discover(bal, "balanced"))
    # Try external human path first, fall back to local data/human_baseline
    human_found = _discover(human, "human")
    if not human_found:
        human_found = _discover(human_local, "human")
    projects.extend(human_found)
    projects.extend(_discover(ai_py, "ai_python"))

    # ── New corpora (local data/ dirs) ──
    projects.extend(_discover(ROOT / "data" / "vibe_coded", "vibe_coded"))
    projects.extend(_discover(ROOT / "data" / "gpt_engineer_apps", "gpt_engineer"))
    projects.extend(_discover(ROOT / "data" / "v0dev_apps", "v0dev"))
    projects.extend(_discover(ROOT / "data" / "vibe_platforms", "vibe_platforms"))
    projects.extend(_discover(ROOT / "data" / "vibe_solidity", "vibe_solidity"))
    projects.extend(_discover(ROOT / "data" / "ai_detection_tools", "ai_detection"))

    return projects


# ── Project type detection ────────────────────────────────────────────


def _detect_checker(proj_path: Path) -> str:
    """Detect whether a project should use DApp or Python boundary checks.

    Heuristic:
      - Has contracts/ dir or *.sol files → "dapp"
      - Has *.py files and no contracts/ → "python"
      - Otherwise → "dapp" (fallback for JS-only projects)
    """
    has_contracts = (proj_path / "contracts").is_dir()
    if has_contracts:
        return "dapp"

    # Check for Python indicators (root files or .py anywhere in tree)
    has_py = (
        (proj_path / "pyproject.toml").exists()
        or (proj_path / "setup.py").exists()
        or (proj_path / "requirements.txt").exists()
        or any(proj_path.glob("*.py"))
        or any(proj_path.rglob("*.py"))
    )
    if has_py:
        return "python"

    return "dapp"


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tier 5 boundary metrics on corpus")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Root directory containing corpus subdirectories")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results",
                        help="Output directory for CSV and markdown")
    args = parser.parse_args()

    results_dir: Path = args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    projects = discover_all(args.data_root)
    print(f"Discovered {len(projects)} projects")

    if not projects:
        print("No projects found. Check --data-root.")
        sys.exit(1)

    # ── Run boundary checks ───────────────────────────────────────────
    rows: list[dict] = []
    t0 = time.time()

    for i, (proj_path, source) in enumerate(projects):
        if (i + 1) % 20 == 0 or i == 0:
            print(f"[{i+1}/{len(projects)}] {source}: {proj_path.name[:16]}...")
        try:
            checker_type = _detect_checker(proj_path)
            if checker_type == "python":
                bm = PythonBoundaryMetrics(proj_path)
            else:
                bm = BoundaryMetrics(proj_path)
            drs = bm.calculate_drs()
            row: dict = {
                "project_id": proj_path.name,
                "source": source,
                "checker": checker_type,
                "drs": drs.score,
                "passing": drs.passing_checks,
                "applicable": drs.total_applicable,
            }
            for check in drs.checks:
                row[f"check_{check.name}"] = (
                    "PASS" if check.passed else ("N/A" if not check.applicable else "FAIL")
                )
            rows.append(row)
        except Exception as e:
            print(f"  ERROR on {proj_path.name}: {e}")
            rows.append({
                "project_id": proj_path.name,
                "source": source,
                "drs": -1,
                "error": str(e),
            })

    elapsed = time.time() - t0
    print(f"\nCompleted {len(rows)} audits in {elapsed:.1f}s "
          f"({elapsed / max(len(rows), 1):.3f}s/system)")

    # ── Save CSV ──────────────────────────────────────────────────────
    csv_path = results_dir / "boundary_metrics_data.csv"
    if rows:
        all_keys: list[str] = []
        seen_keys: set[str] = set()
        for r in rows:
            for k in r:
                if k not in seen_keys:
                    all_keys.append(k)
                    seen_keys.add(k)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {len(rows)} rows to {csv_path}")

    # ── THI per cohort ────────────────────────────────────────────────
    cohorts: dict[str, list[Path]] = {}
    for proj_path, source in projects:
        cohorts.setdefault(source, []).append(proj_path)

    thi_results: dict[str, float] = {}
    for label, cohort_projects in cohorts.items():
        print(f"Computing THI for {label} ({len(cohort_projects)} projects)...")
        # For large cohorts, sample to keep runtime reasonable
        sample = cohort_projects[:50]
        thi = compute_thi(sample)
        thi_results[label] = thi.thi
        print(f"  THI({label}) = {thi.thi:.3f} (sampled {thi.cohort_size}, {thi.pairs_compared} pairs)")

    # ── Generate report ───────────────────────────────────────────────
    valid_rows = [r for r in rows if r.get("drs", -1) >= 0]
    report_lines: list[str] = [
        "# Tier 5: Boundary Metrics Report",
        "",
        f"Analysed **{len(valid_rows)}** systems.",
        "",
    ]

    # Summary by source
    report_lines += ["## DRS by Source", "", "| Source | N | Mean DRS | Median DRS | DRS=1.0 (fully ready) |", "|--------|---|----------|------------|----------------------|"]
    for source_label in sorted(cohorts):
        source_rows = [r for r in valid_rows if r["source"] == source_label]
        if not source_rows:
            continue
        scores = [r["drs"] for r in source_rows]
        n = len(scores)
        mean_drs = sum(scores) / n
        sorted_scores = sorted(scores)
        median_drs = sorted_scores[n // 2]
        perfect = sum(1 for s in scores if s >= 1.0)
        report_lines.append(
            f"| {source_label} | {n} | {mean_drs:.3f} | {median_drs:.3f} | {perfect} ({perfect/n*100:.1f}%) |"
        )
    report_lines.append("")

    # THI
    report_lines += ["## Template Homogeneity Index (THI)", "", "| Cohort | THI |", "|--------|-----|"]
    for label, thi_val in sorted(thi_results.items()):
        report_lines.append(f"| {label} | {thi_val:.3f} |")
    report_lines.append("")

    # Per-check failure rates
    check_cols = [k for k in (valid_rows[0] if valid_rows else {}) if k.startswith("check_")]
    if check_cols:
        report_lines += ["## Per-Check Failure Rates (across all sources)", "", "| Check | FAIL | N/A | PASS |", "|-------|------|-----|------|"]
        for col in check_cols:
            fail = sum(1 for r in valid_rows if r.get(col) == "FAIL")
            na = sum(1 for r in valid_rows if r.get(col) == "N/A")
            pas = sum(1 for r in valid_rows if r.get(col) == "PASS")
            name = col.replace("check_", "")
            report_lines.append(f"| {name} | {fail} | {na} | {pas} |")
        report_lines.append("")

    # Comparison table
    report_lines += [
        "## Comparison: Tier Metrics vs DRS",
        "",
        "| Perspective | Tier 1-4 Metrics | Tier 5 (DRS) |",
        "|-------------|-----------------|--------------|",
        "| Deployment feasibility | DFR=DEPLOYABLE (cycle-free) | DRS shows actual boundary integrity |",
        "| Config completeness | CCS (resolved/total, 0/0→1.0) | Check 6: all process.env refs defined |",
        "| Reference integrity | URR (0/0→0.0) | Check 11: require() paths resolve |",
        "| ABI integrity | Not measured | Checks 1-3: ABI exists, matches, no stubs |",
        "| Port conflicts | Not measured | Check 8: no port conflicts |",
        "| Dead code | Not measured | Check 5: no dead backend routes |",
        "",
    ]

    report_path = results_dir / "boundary_metrics_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Saved report to {report_path}")
    print("Done.")


if __name__ == "__main__":
    main()

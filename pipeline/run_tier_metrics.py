#!/usr/bin/env python3
"""
Batch runner: compute all Tier 1-4 metrics on the full corpus.

Discovers three AI sources (benchmark, multi-agent, balanced_dataset)
and 100 human baselines, runs all tier metrics on each.

Outputs:
    results/tier_metrics_data.csv   — per-system flat CSV
    results/tier_metrics_summary.md — group-level summary tables

Usage:
    python pipeline/run_tier_metrics.py [--data-root DATA] [--results-dir RESULTS]
"""

import argparse
import json
import signal
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aicoder_debt import AICoderDebtAnalyzer  # noqa: E402

# ── Timeout helper ───────────────────────────────────────────────────
TIMEOUT_SECS = 120  # 2 min per system


class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("Timed out")


# ── Corpus discovery ─────────────────────────────────────────────────


def discover_corpus(data_root: Path) -> list[dict]:
    """Return list of dicts: id, path, group, domain, strategy, source."""
    systems: list[dict] = []

    project_root = data_root.parent  # aicoder-debt/

    # ── 1. Benchmark outputs (120 systems, GPT-4-turbo, 4 domains) ──
    bench = project_root / "benchmark" / "outputs"
    if bench.exists():
        for sys_dir in sorted(bench.iterdir()):
            if not sys_dir.is_dir():
                continue
            # Use extracted/ subdir if present, otherwise the dir itself
            proj_path = sys_dir / "extracted"
            if not proj_path.is_dir():
                proj_path = sys_dir

            # Parse name: e.g. "ms-002_gpt-4-turbo_structured"
            parts = sys_dir.name.split("_")
            domain_tag = parts[0].split("-")[0] if parts else "unknown"
            domain_map = {"ms": "microservice", "web": "webapp",
                          "defi": "defi", "worker": "worker"}
            domain = domain_map.get(domain_tag, domain_tag)
            strategy = parts[-1] if len(parts) >= 3 else ""

            systems.append({
                "system_id": f"bench/{sys_dir.name}",
                "path": str(proj_path),
                "group": "AI-Benchmark",
                "domain": domain,
                "strategy": strategy,
                "source": "benchmark",
            })

    # ── 2. Multi-agent DApp projects (366 unique, DeFi) ──
    ma_path = Path("/Users/viraaji/2025_IdeaProj/multi_agent_system/storage/projects")
    if ma_path.exists():
        for proj_dir in sorted(ma_path.iterdir()):
            if not proj_dir.is_dir():
                continue
            # Skip symlinks / duplicates
            if proj_dir.is_symlink():
                continue
            systems.append({
                "system_id": f"multi-agent/{proj_dir.name[:12]}",
                "path": str(proj_dir),
                "group": "AI-MultiAgent",
                "domain": "defi",
                "strategy": "multi-agent",
                "source": "multi_agent",
            })

    # ── 3. Human baselines (100 repos) ──
    hb = data_root / "human_baseline"
    if hb.exists():
        for proj_dir in sorted(hb.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"human/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "Human",
                "domain": "human_baseline",
                "strategy": "",
                "source": "human_baseline",
            })

    # ── 4. AI Python baseline (9 repos, self-declared AI-generated) ──
    ai_py = data_root / "ai_python_baseline"
    if ai_py.exists():
        for proj_dir in sorted(ai_py.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"ai-python/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "AI-Python",
                "domain": "python",
                "strategy": "ai-generated",
                "source": "ai_python",
            })

    # ── 5. Vibe-coded repos (multi-language AI-generated) ──
    vibe = data_root / "vibe_coded"
    if vibe.exists():
        for proj_dir in sorted(vibe.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"vibe/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "AI-Vibe",
                "domain": "vibe_coded",
                "strategy": "vibe-coded",
                "source": "vibe_coded",
            })

    # ── 6. GPT-Engineer / Lovable / Bolt.new apps ──
    gpt_eng = data_root / "gpt_engineer_apps"
    if gpt_eng.exists():
        for proj_dir in sorted(gpt_eng.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"gpt-eng/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "AI-GPTEng",
                "domain": "web_app",
                "strategy": "gpt-engineer",
                "source": "gpt_engineer",
            })

    # ── 7. v0.dev generated apps ──
    v0 = data_root / "v0dev_apps"
    if v0.exists():
        for proj_dir in sorted(v0.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"v0dev/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "AI-v0dev",
                "domain": "web_app",
                "strategy": "v0dev",
                "source": "v0dev",
            })

    # ── 8. Vibe-coded platforms / tools ──
    vp = data_root / "vibe_platforms"
    if vp.exists():
        for proj_dir in sorted(vp.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"platform/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "AI-Platform",
                "domain": "platform",
                "strategy": "vibe-coded",
                "source": "vibe_platforms",
            })

    # ── 9. AI-generated Solidity projects ──
    sol = data_root / "vibe_solidity"
    if sol.exists():
        for proj_dir in sorted(sol.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"solidity/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "AI-Solidity",
                "domain": "solidity",
                "strategy": "vibe-coded",
                "source": "vibe_solidity",
            })

    # ── 10. AI code detection tools (meta-analysis) ──
    det = data_root / "ai_detection_tools"
    if det.exists():
        for proj_dir in sorted(det.iterdir()):
            if not proj_dir.is_dir():
                continue
            systems.append({
                "system_id": f"detect/{proj_dir.name}",
                "path": str(proj_dir),
                "group": "AI-Detection",
                "domain": "detection_tools",
                "strategy": "ai-tool",
                "source": "ai_detection",
            })

    return systems


# ── Analyze one system ───────────────────────────────────────────────


def analyze_one(
    analyzer: AICoderDebtAnalyzer, system: dict
) -> dict:
    """Run all tier metrics on one system, return flat row dict."""
    row = {
        "system_id": system["system_id"],
        "group": system["group"],
        "domain": system["domain"],
        "strategy": system["strategy"],
        "source": system.get("source", ""),
    }

    proj = Path(system["path"])

    try:
        # Set alarm timeout (Unix only)
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT_SECS)

        # ── DDG extraction ──
        ddg = analyzer.extract_ddg(proj)
        row["ddg_nodes"] = len(ddg.nodes)
        row["ddg_edges"] = len(ddg.edges)
        row["ddg_cycles"] = len(ddg.cycles)

        # ── Tier 1: Deployment ──
        try:
            tier1 = analyzer.calculate_tier1(proj, ddg)
            row["dfr_rating"] = tier1.dfr.rating.value
            row["dfr_cycles"] = tier1.dfr.cycles_count
            row["dfr_stateful_cycles"] = tier1.dfr.stateful_cycles_count
            row["dfr_irreparable_cycles"] = tier1.dfr.irreparable_cycles_count
            row["drd_cost"] = tier1.drd.cost
            row["id_stage"] = tier1.id.stage.value
            row["id_gap"] = tier1.id.gap
        except Exception as e:
            row["tier1_error"] = str(e)[:200]

        # ── Tier 2: Integration ──
        try:
            tier2 = analyzer.calculate_tier2(proj)
            row["icr_rate"] = tier2.icr.rate
            row["icr_matched"] = tier2.icr.matched_calls
            row["icr_total_calls"] = tier2.icr.total_internal_calls
            row["icr_endpoints"] = len(tier2.icr.endpoints)
            row["ccs_score"] = tier2.ccs.score
            row["ccs_resolved"] = tier2.ccs.resolved_configs
            row["ccs_total_refs"] = tier2.ccs.total_config_refs
        except Exception as e:
            row["tier2_error"] = str(e)[:200]

        # ── Tier 3: Assumption ──
        try:
            tier3 = analyzer.calculate_tier3(proj)
            row["urr_rate"] = tier3.urr.rate
            row["urr_unresolved"] = tier3.urr.unresolved_refs
            row["urr_total_refs"] = tier3.urr.total_internal_refs
            row["hd_density"] = tier3.hd.density
            row["hd_hallucinated"] = tier3.hd.hallucinated_count
            row["hd_total_packages"] = tier3.hd.total_packages
            row["hd_kloc"] = round(tier3.hd.kloc, 3)
        except Exception as e:
            row["tier3_error"] = str(e)[:200]

        # ── Tier 4: Maintainability ──
        try:
            tier4 = analyzer.calculate_tier4(proj)
            row["csd_density"] = round(tier4.csd.density, 3)
            row["csd_total_issues"] = tier4.csd.total_issues
            row["csd_kloc"] = round(tier4.csd.kloc, 3)
            row["ccx_average"] = round(tier4.ccx.average, 3)
            row["ccx_max"] = tier4.ccx.max_complexity
            row["ccx_total_functions"] = tier4.ccx.total_functions
            row["ccx_high_complexity"] = tier4.ccx.high_complexity_count
        except Exception as e:
            row["tier4_error"] = str(e)[:200]

        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

    except TimeoutError:
        row["error"] = f"TIMEOUT ({TIMEOUT_SECS}s)"
        signal.alarm(0)
    except Exception as e:
        row["error"] = str(e)[:200]
        signal.alarm(0)

    return row


# ── Summary statistics ───────────────────────────────────────────────


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    """Return column as Series, or zeros if missing."""
    if col in df.columns:
        return df[col]
    return pd.Series([0] * len(df), index=df.index)


def generate_summary(df: pd.DataFrame, out_path: Path) -> None:
    """Generate markdown summary tables from tier metrics dataframe."""
    lines: list[str] = []
    groups = [g for g in [
        "AI-Benchmark", "AI-MultiAgent", "AI-Python", "AI-Vibe",
        "AI-GPTEng", "AI-v0dev", "AI-Platform", "AI-Solidity",
        "AI-Detection", "Human",
    ] if g in df["group"].values]

    lines.append("# Tier 1–4 Metrics: Summary by Group\n")
    lines.append(
        f"Generated from {len(df)} systems "
        f"({', '.join(f'{n} {g}' for g, n in df['group'].value_counts().items())}).\n"
    )

    # ── Table 1: DDG overview ──
    lines.append("### DDG Overview\n")
    lines.append("| Group | N | Mean Nodes | Mean Edges | Mean Cycles | % with Cycles |")
    lines.append("|-------|---|-----------|-----------|------------|---------------|")
    for grp in groups:
        sub = df[df["group"] == grp]
        n = len(sub)
        mn = _safe_col(sub, "ddg_nodes").mean()
        me = _safe_col(sub, "ddg_edges").mean()
        mc = _safe_col(sub, "ddg_cycles").mean()
        pct_cyc = (_safe_col(sub, "ddg_cycles") > 0).mean() * 100
        lines.append(f"| {grp} | {n} | {mn:.1f} | {me:.1f} | {mc:.1f} | {pct_cyc:.1f}% |")

    # ── Table 2: Tier 1 ──
    lines.append("\n### Tier 1: Deployment Metrics\n")
    lines.append(
        "| Group | N | % Deployable | % Repairable | % Irreparable "
        "| Mean DRD Cost | Mean ID Stage | Mean ID Gap |"
    )
    lines.append("|-------|---|-------------|-------------|--------------|"
                 "--------------|--------------|-------------|")
    for grp in groups:
        sub = df[df["group"] == grp]
        n = len(sub)
        if "dfr_rating" in sub.columns:
            dep = (sub["dfr_rating"] == "DEPLOYABLE").mean() * 100
            rep = (sub["dfr_rating"] == "REPAIRABLE").mean() * 100
            irr = (sub["dfr_rating"] == "IRREPARABLE").mean() * 100
        else:
            dep = rep = irr = 0
        drd = _safe_col(sub, "drd_cost").mean()
        ids = _safe_col(sub, "id_stage").mean()
        idg = _safe_col(sub, "id_gap").mean()
        lines.append(
            f"| {grp} | {n} | {dep:.1f}% | {rep:.1f}% | {irr:.1f}% "
            f"| {drd:.2f} | {ids:.1f} | {idg:.1f} |"
        )

    # ── Table 3: Tier 2 ──
    lines.append("\n### Tier 2: Integration Metrics\n")
    lines.append(
        "| Group | N | Mean ICR | Median ICR | Mean CCS | Median CCS "
        "| Mean Internal Calls | Mean Config Refs |"
    )
    lines.append("|-------|---|---------|-----------|---------|----------"
                 "|--------------------|--------------------|")
    for grp in groups:
        sub = df[df["group"] == grp]
        n = len(sub)
        lines.append(
            f"| {grp} | {n} "
            f"| {_safe_col(sub,'icr_rate').mean():.3f} | {_safe_col(sub,'icr_rate').median():.3f} "
            f"| {_safe_col(sub,'ccs_score').mean():.3f} | {_safe_col(sub,'ccs_score').median():.3f} "
            f"| {_safe_col(sub,'icr_total_calls').mean():.1f} "
            f"| {_safe_col(sub,'ccs_total_refs').mean():.1f} |"
        )

    # ── Table 4: Tier 3 ──
    lines.append("\n### Tier 3: Assumption Metrics\n")
    lines.append(
        "| Group | N | Mean URR | Median URR | Mean HD | Median HD "
        "| Mean KLOC | Mean Internal Refs |"
    )
    lines.append("|-------|---|---------|-----------|--------|----------"
                 "|---------|--------------------|")
    for grp in groups:
        sub = df[df["group"] == grp]
        n = len(sub)
        lines.append(
            f"| {grp} | {n} "
            f"| {_safe_col(sub,'urr_rate').mean():.3f} | {_safe_col(sub,'urr_rate').median():.3f} "
            f"| {_safe_col(sub,'hd_density').mean():.3f} | {_safe_col(sub,'hd_density').median():.3f} "
            f"| {_safe_col(sub,'hd_kloc').mean():.1f} "
            f"| {_safe_col(sub,'urr_total_refs').mean():.1f} |"
        )

    # ── Table 5: Tier 4 ──
    lines.append("\n### Tier 4: Maintainability Metrics\n")
    lines.append(
        "| Group | N | Mean CSD | Median CSD | Mean CCX | Median CCX "
        "| Mean Functions | Mean High-Complexity |"
    )
    lines.append("|-------|---|---------|-----------|---------|----------"
                 "|---------------|-----------------------|")
    for grp in groups:
        sub = df[df["group"] == grp]
        n = len(sub)
        lines.append(
            f"| {grp} | {n} "
            f"| {_safe_col(sub,'csd_density').mean():.3f} | {_safe_col(sub,'csd_density').median():.3f} "
            f"| {_safe_col(sub,'ccx_average').mean():.3f} | {_safe_col(sub,'ccx_average').median():.3f} "
            f"| {_safe_col(sub,'ccx_total_functions').mean():.1f} "
            f"| {_safe_col(sub,'ccx_high_complexity').mean():.1f} |"
        )

    # ── Domain breakdown ──
    lines.append("\n### By Domain\n")
    lines.append("| Domain | Group | N | Mean DDG Nodes | Mean Cycles | Mean ICR | Mean CCS | Mean URR |")
    lines.append("|--------|-------|---|---------------|-------------|---------|---------|---------|")
    for domain in sorted(df["domain"].unique()):
        for grp in groups:
            sub = df[(df["domain"] == domain) & (df["group"] == grp)]
            if sub.empty:
                continue
            lines.append(
                f"| {domain} | {grp} | {len(sub)} "
                f"| {_safe_col(sub,'ddg_nodes').mean():.1f} "
                f"| {_safe_col(sub,'ddg_cycles').mean():.1f} "
                f"| {_safe_col(sub,'icr_rate').mean():.3f} "
                f"| {_safe_col(sub,'ccs_score').mean():.3f} "
                f"| {_safe_col(sub,'urr_rate').mean():.3f} |"
            )

    # ── Statistical tests ──
    lines.append("\n### Statistical Tests (Mann-Whitney U: AI pooled vs Human)\n")
    from scipy.stats import mannwhitneyu

    test_cols = [
        ("DDG Nodes", "ddg_nodes"),
        ("DDG Cycles", "ddg_cycles"),
        ("DRD Cost", "drd_cost"),
        ("ID Gap", "id_gap"),
        ("ICR", "icr_rate"),
        ("CCS", "ccs_score"),
        ("URR", "urr_rate"),
        ("HD", "hd_density"),
        ("CSD", "csd_density"),
        ("CCX", "ccx_average"),
    ]
    lines.append("| Metric | N(AI) | N(Human) | U | p-value | Rank-Biserial r | Effect |")
    lines.append("|--------|-------|----------|---|---------|-----------------|--------|")
    ai = df[df["group"] != "Human"]
    human = df[df["group"] == "Human"]
    for label, col in test_cols:
        if col not in df.columns:
            continue
        x = ai[col].dropna()
        y = human[col].dropna()
        if len(x) < 2 or len(y) < 2:
            continue
        try:
            u, p = mannwhitneyu(x, y, alternative="two-sided")
            n1, n2 = len(x), len(y)
            r = 1.0 - (2.0 * u) / (n1 * n2)
            eff = "large" if abs(r) > 0.5 else ("medium" if abs(r) > 0.3 else "small")
            sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))
            lines.append(
                f"| {label} | {n1} | {n2} | {u:.0f} | {p:.2e}{sig} "
                f"| {r:.3f} | {eff} |"
            )
        except Exception:
            pass

    lines.append(
        "\n_Significance: * p<0.05, ** p<0.01, *** p<0.001_\n"
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Run Tier 1-4 metrics on 300-system corpus")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=ROOT / "data",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=ROOT / "results",
    )
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    results_dir = args.results_dir.resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    systems = discover_corpus(data_root)
    print(f"Discovered {len(systems)} systems")

    analyzer = AICoderDebtAnalyzer(
        skip_registry_check=False,  # enable PyPI/NPM lookups for HD
        skip_maintainability=False,  # include Tier 4
    )

    rows: list[dict] = []
    t0 = time.time()

    for i, system in enumerate(systems, 1):
        if i % 10 == 1 or i == len(systems):
            print(f"[{i}/{len(systems)}] Processing {system['system_id']} ({system['group']})...")

        row = analyze_one(analyzer, system)
        rows.append(row)

    elapsed = time.time() - t0

    # Save CSV
    df = pd.DataFrame(rows)
    csv_path = results_dir / "tier_metrics_data.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved {len(df)} rows to {csv_path}")

    # Errors summary
    err_cols = [c for c in df.columns if c.endswith("_error") or c == "error"]
    for c in err_cols:
        n_err = df[c].notna().sum()
        if n_err > 0:
            print(f"  {c}: {n_err} errors")

    # Summary
    summary_path = results_dir / "tier_metrics_summary.md"
    generate_summary(df, summary_path)
    print(f"Saved summary to {summary_path}")
    print(f"Completed in {elapsed:.1f}s ({elapsed / len(systems):.1f}s/system)")


if __name__ == "__main__":
    main()

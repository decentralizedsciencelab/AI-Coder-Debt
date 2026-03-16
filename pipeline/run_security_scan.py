#!/usr/bin/env python3
"""
Security Scan Pipeline: Run SAST scanner across all corpora.

Scans multi_agent, ai_python, human_baseline, benchmark, and vibe_coded
corpora using the SecurityScanner module. Outputs:
  - results/security_scan_data.csv        (per-project summary)
  - results/security_scan_findings.csv    (all individual findings)
  - results/security_scan_report.md       (human-readable summary)
"""

import csv
import sys
import time
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aicoder_debt.metrics.security_scanner import (
    SecurityScanner,
    SecurityScanResult,
    format_findings_report,
)

RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

# ── CORPUS DEFINITIONS ─────────────────────────────────────────────────

CORPORA = {
    "multi_agent": {
        "path": ROOT.parent / "multi_agent_system" / "storage" / "projects",
        "alt_path": ROOT / "multi_agent_system" / "storage" / "projects",
        "source": "multi_agent",
        "max_projects": 20,  # sample for speed (366 total)
    },
    "ai_python": {
        "path": ROOT / "data" / "ai_python_baseline",
        "source": "ai_python",
    },
    "human": {
        "path": ROOT / "data" / "human_baseline",
        "source": "human",
    },
    "vibe_coded": {
        "path": ROOT / "data" / "vibe_coded",
        "source": "vibe_coded",
    },
    "gpt_engineer": {
        "path": ROOT / "data" / "gpt_engineer_apps",
        "source": "gpt_engineer",
    },
    "v0dev": {
        "path": ROOT / "data" / "v0dev_apps",
        "source": "v0dev",
    },
    "vibe_platforms": {
        "path": ROOT / "data" / "vibe_platforms",
        "source": "vibe_platforms",
    },
    "vibe_solidity": {
        "path": ROOT / "data" / "vibe_solidity",
        "source": "vibe_solidity",
    },
    "ai_detection": {
        "path": ROOT / "data" / "ai_detection_tools",
        "source": "ai_detection",
    },
}


def find_corpus_path(corpus_cfg: dict) -> Path | None:
    """Find the first existing path for a corpus."""
    for key in ("path", "alt_path"):
        p = corpus_cfg.get(key)
        if p and Path(p).exists():
            return Path(p)
    return None


def scan_corpus(
    scanner: SecurityScanner,
    corpus_name: str,
    corpus_path: Path,
    source: str,
    max_projects: int | None = None,
) -> list[SecurityScanResult]:
    """Scan all projects in a corpus directory."""
    results = []
    projects = sorted([d for d in corpus_path.iterdir() if d.is_dir()])

    if max_projects and len(projects) > max_projects:
        # Deterministic sampling: every Nth project
        step = len(projects) // max_projects
        projects = projects[::step][:max_projects]

    total = len(projects)
    print(f"\n  Scanning {corpus_name}: {total} projects from {corpus_path}")
    sys.stdout.flush()

    for i, project_dir in enumerate(projects):
        if (i + 1) % 5 == 0 or (i + 1) == total or (i + 1) == 1:
            print(f"    [{i+1}/{total}] {project_dir.name}...")
            sys.stdout.flush()

        result = scanner.scan_project(
            project_dir,
            project_id=f"{source}/{project_dir.name}",
            source=source,
        )
        results.append(result)

    return results


def write_summary_csv(results: list[SecurityScanResult], path: Path):
    """Write per-project summary CSV."""
    fieldnames = [
        "project_id", "source", "total_findings", "critical", "high",
        "medium", "low", "kloc", "files_scanned", "security_debt_density",
        "secret_count", "injection_count", "crypto_weakness_count",
        "auth_issue_count", "config_issue_count",
    ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "project_id": r.project_id,
                "source": r.source,
                "total_findings": r.total_findings,
                "critical": r.critical,
                "high": r.high,
                "medium": r.medium,
                "low": r.low,
                "kloc": round(r.kloc, 2),
                "files_scanned": r.total_files_scanned,
                "security_debt_density": round(r.security_debt_density, 2),
                "secret_count": r.secret_count,
                "injection_count": r.injection_count,
                "crypto_weakness_count": r.crypto_weakness_count,
                "auth_issue_count": r.auth_issue_count,
                "config_issue_count": r.config_issue_count,
            })


def write_findings_csv(results: list[SecurityScanResult], path: Path):
    """Write all individual findings to CSV."""
    fieldnames = [
        "project_id", "source", "pattern_id", "cwe", "severity", "owasp",
        "category", "description", "file_path", "line_number", "language",
    ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            for finding in r.findings:
                writer.writerow({
                    "project_id": r.project_id,
                    "source": r.source,
                    "pattern_id": finding.pattern_id,
                    "cwe": finding.cwe,
                    "severity": finding.severity,
                    "owasp": finding.owasp,
                    "category": finding.category,
                    "description": finding.description,
                    "file_path": finding.file_path,
                    "line_number": finding.line_number,
                    "language": finding.language,
                })


def write_report(results: list[SecurityScanResult], path: Path):
    """Write markdown summary report."""
    import numpy as np

    lines = [
        "# Security Scan Results",
        "",
        f"Generated by `run_security_scan.py` | {len(results)} projects scanned",
        "",
    ]

    # Per-corpus summary
    from collections import defaultdict
    by_source: dict[str, list[SecurityScanResult]] = defaultdict(list)
    for r in results:
        by_source[r.source].append(r)

    lines.append("## Summary by Corpus")
    lines.append("")
    lines.append("| Corpus | N | Mean SDD | Median SDD | Mean Findings | CRIT | HIGH | MED | LOW | Secrets | Injections |")
    lines.append("|--------|---|---------|-----------|--------------|------|------|-----|-----|---------|------------|")

    all_sources = ["multi_agent", "ai_python", "vibe_coded", "gpt_engineer",
                    "v0dev", "vibe_platforms", "vibe_solidity", "ai_detection", "human"]
    for source in all_sources:
        group = by_source.get(source, [])
        if not group:
            continue
        n = len(group)
        sdds = [r.security_debt_density for r in group]
        findings = [r.total_findings for r in group]
        crits = sum(r.critical for r in group)
        highs = sum(r.high for r in group)
        meds = sum(r.medium for r in group)
        lows = sum(r.low for r in group)
        secrets = sum(r.secret_count for r in group)
        injections = sum(r.injection_count for r in group)

        lines.append(
            f"| {source} | {n} | {np.mean(sdds):.2f} | {np.median(sdds):.2f} | "
            f"{np.mean(findings):.1f} | {crits} | {highs} | {meds} | {lows} | "
            f"{secrets} | {injections} |"
        )

    lines.append("")

    # Top patterns across all corpora
    lines.append("## Top Vulnerability Patterns")
    lines.append("")

    from collections import Counter
    pattern_counts: Counter = Counter()
    pattern_desc: dict[str, str] = {}
    pattern_sev: dict[str, str] = {}
    for r in results:
        for f in r.findings:
            pattern_counts[f.pattern_id] += 1
            pattern_desc[f.pattern_id] = f.description
            pattern_sev[f.pattern_id] = f.severity

    lines.append("| Pattern | Severity | Count | Description |")
    lines.append("|---------|----------|-------|-------------|")
    for pid, count in pattern_counts.most_common(20):
        lines.append(
            f"| {pid} | {pattern_sev[pid]} | {count} | {pattern_desc[pid]} |"
        )

    lines.append("")

    # Per-corpus OWASP category breakdown
    lines.append("## OWASP Category Distribution by Corpus")
    lines.append("")

    owasp_names = {
        "A01": "Broken Access Control",
        "A02": "Cryptographic Failures",
        "A03": "Injection",
        "A04": "Insecure Design",
        "A05": "Security Misconfiguration",
        "A06": "Vulnerable Components",
        "A07": "Auth Failures",
        "A08": "Data Integrity",
        "A09": "Logging Failures",
        "A10": "SSRF",
    }

    for source in all_sources:
        group = by_source.get(source, [])
        if not group:
            continue
        owasp_counts: Counter = Counter()
        for r in group:
            for f in r.findings:
                owasp_counts[f.owasp] += 1

        lines.append(f"### {source} (N={len(group)})")
        lines.append("")
        if owasp_counts:
            for code in sorted(owasp_counts.keys()):
                name = owasp_names.get(code, code)
                lines.append(f"- **{code}** {name}: {owasp_counts[code]}")
        else:
            lines.append("- No findings")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


def main():
    print("=" * 60)
    print("Security Scan Pipeline")
    print("=" * 60)

    scanner = SecurityScanner()
    all_results: list[SecurityScanResult] = []

    t0 = time.time()

    for corpus_name, cfg in CORPORA.items():
        corpus_path = find_corpus_path(cfg)
        if corpus_path is None:
            print(f"\n  {corpus_name}: path not found, skipping")
            continue

        results = scan_corpus(
            scanner,
            corpus_name,
            corpus_path,
            cfg["source"],
            cfg.get("max_projects"),
        )
        all_results.extend(results)

    elapsed = time.time() - t0

    # Write outputs
    summary_path = RESULTS / "security_scan_data.csv"
    findings_path = RESULTS / "security_scan_findings.csv"
    report_path = RESULTS / "security_scan_report.md"

    write_summary_csv(all_results, summary_path)
    write_findings_csv(all_results, findings_path)
    write_report(all_results, report_path)

    print(f"\n{'=' * 60}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  {len(all_results)} projects scanned")
    print(f"  {sum(r.total_findings for r in all_results)} total findings")
    print(f"\nOutput:")
    print(f"  {summary_path}")
    print(f"  {findings_path}")
    print(f"  {report_path}")


if __name__ == "__main__":
    main()

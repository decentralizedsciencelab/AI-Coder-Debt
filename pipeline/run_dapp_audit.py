#!/usr/bin/env python3
"""
Deployment audit for multi-agent DApp projects.

Scans all 366+ DApps for deployment issues that standard tier metrics miss:
  - Missing / empty ABI files
  - ABI–contract function mismatch
  - Env-var naming inconsistencies
  - Missing deploy scripts & hardhat config
  - Port conflicts
  - Placeholder (zero) addresses
  - Frontend env vars not defined
  - Dead backend API code (frontend bypasses backend)
  - Unimplemented Solidity function stubs

Outputs:
    results/dapp_audit_data.csv   — per-system issue counts
    results/dapp_audit_report.md  — aggregate analysis
"""

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

MA_PATH = Path("/Users/viraaji/2025_IdeaProj/multi_agent_system/storage/projects")

ZERO_ADDR = "0x" + "0" * 40


# ── Helpers ──────────────────────────────────────────────────────────


def _read_text(p: Path) -> str:
    """Read file as text, return '' on failure."""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_json(p: Path):
    """Read JSON file, return None on failure."""
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _find_files(root: Path, extensions: set[str]) -> list[Path]:
    """Walk root and yield files matching extensions."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip node_modules, .git, etc.
        dirnames[:] = [d for d in dirnames if d not in {
            "node_modules", ".git", "__pycache__", "venv", ".next", "build", "dist",
            "artifacts", "cache", "coverage",
        }]
        for fn in filenames:
            if any(fn.endswith(ext) for ext in extensions):
                found.append(Path(dirpath) / fn)
    return found


def _extract_sol_functions(sol_text: str) -> set[str]:
    """Extract function names from Solidity source."""
    fns = set()
    for m in re.finditer(r'\bfunction\s+(\w+)\s*\(', sol_text):
        name = m.group(1)
        # skip constructor and internal helpers starting with _
        if name != "constructor":
            fns.add(name)
    return fns


def _extract_abi_functions(abi: list) -> set[str]:
    """Extract function names from ABI JSON array."""
    fns = set()
    if not isinstance(abi, list):
        return fns
    for entry in abi:
        if isinstance(entry, dict) and entry.get("type") == "function":
            name = entry.get("name", "")
            if name:
                fns.add(name)
    return fns


def _find_env_references(js_files: list[Path]) -> dict[str, list[str]]:
    """Find all process.env.VAR references across JS files.
    Returns {VAR_NAME: [file1, file2, ...]}."""
    refs: dict[str, list[str]] = {}
    for fp in js_files:
        text = _read_text(fp)
        for m in re.finditer(r'process\.env\.(\w+)', text):
            var = m.group(1)
            refs.setdefault(var, []).append(str(fp))
    return refs


def _parse_env_file(env_path: Path) -> set[str]:
    """Parse .env file and return set of defined variable names."""
    defined = set()
    text = _read_text(env_path)
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key:
                defined.add(key)
    return defined


def _get_env_values(env_path: Path) -> dict[str, str]:
    """Parse .env file into key=value dict."""
    vals = {}
    text = _read_text(env_path)
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals


def _check_require_paths(js_files: list[Path], proj_root: Path) -> list[dict]:
    """Check if require('./...') paths resolve to existing files."""
    broken = []
    for fp in js_files:
        text = _read_text(fp)
        for m in re.finditer(r"""require\s*\(\s*['"](\.[^'"]+)['"]\s*\)""", text):
            req_path = m.group(1)
            # Resolve relative to the file's directory
            resolved = (fp.parent / req_path).resolve()
            # Try exact, .js, .json, /index.js
            candidates = [
                resolved,
                resolved.with_suffix(".js"),
                resolved.with_suffix(".json"),
                resolved / "index.js",
            ]
            if not any(c.exists() for c in candidates):
                broken.append({
                    "file": str(fp.relative_to(proj_root)),
                    "require": req_path,
                })
    return broken


def _check_sol_stubs(sol_files: list[Path], proj_root: Path) -> list[dict]:
    """Find Solidity functions with empty or stub bodies."""
    stubs = []
    for fp in sol_files:
        text = _read_text(fp)
        # Match function ... { // comment-only or empty body }
        for m in re.finditer(
            r'function\s+(\w+)\s*\([^)]*\)[^{]*\{([^}]*)\}',
            text, re.DOTALL
        ):
            fname = m.group(1)
            body = m.group(2).strip()
            # Check if body is empty or only comments
            code_lines = [
                l.strip() for l in body.splitlines()
                if l.strip() and not l.strip().startswith("//")
            ]
            if not code_lines and fname != "constructor":
                stubs.append({
                    "file": str(fp.relative_to(proj_root)),
                    "function": fname,
                })
    return stubs


def _check_frontend_backend_disconnect(proj: Path) -> dict:
    """Check if frontend actually calls backend API or goes direct to contract."""
    frontend_src = proj / "frontend" / "src"
    if not frontend_src.exists():
        return {"has_frontend": False}

    fe_files = _find_files(frontend_src, {".js", ".jsx", ".ts", ".tsx"})
    fe_text = "\n".join(_read_text(f) for f in fe_files)

    # Check if frontend makes HTTP calls to backend
    api_patterns = [
        r'fetch\s*\(',
        r'axios\.',
        r'\.get\s*\(["\']/',
        r'\.post\s*\(["\']/',
        r'BACKEND_URL',
        r'API_URL',
        r'api\.',
    ]
    has_backend_calls = any(re.search(p, fe_text) for p in api_patterns)

    # Check if frontend calls contract directly
    direct_patterns = [
        r'ethers\.Contract',
        r'new\s+Contract\s*\(',
        r'contract\[',
        r'contract\.\w+\s*\(',
        r'web3\.eth',
        r'useContract',
    ]
    has_direct_contract = any(re.search(p, fe_text) for p in direct_patterns)

    # Check if backend has API endpoints
    backend_dir = proj / "backend"
    be_files = _find_files(backend_dir, {".js"}) if backend_dir.exists() else []
    be_text = "\n".join(_read_text(f) for f in be_files)
    has_backend_routes = bool(re.search(
        r'(router\.(get|post|put|delete)|app\.(get|post|put|delete))\s*\(',
        be_text
    ))

    return {
        "has_frontend": True,
        "fe_calls_backend_api": has_backend_calls,
        "fe_calls_contract_direct": has_direct_contract,
        "backend_has_routes": has_backend_routes,
        "dead_backend_api": has_backend_routes and not has_backend_calls,
    }


# ── Main audit per project ──────────────────────────────────────────


def audit_project(proj: Path) -> dict:
    """Run full deployment audit on a single DApp project."""
    row = {
        "project_id": proj.name,
        "path": str(proj),
    }

    # ── 1. Structure check ──
    has_backend = (proj / "backend").is_dir()
    has_frontend = (proj / "frontend").is_dir()
    has_contracts = (proj / "contracts").is_dir()
    has_test = (proj / "test").is_dir()

    row["has_backend"] = has_backend
    row["has_frontend"] = has_frontend
    row["has_contracts"] = has_contracts
    row["has_test"] = has_test
    row["component_count"] = sum([has_backend, has_frontend, has_contracts, has_test])

    # ── 2. ABI checks ──
    abi_config = proj / "backend" / "config" / "contractABI.json"
    row["abi_file_exists"] = abi_config.exists()
    abi_data = _read_json(abi_config) if abi_config.exists() else None
    row["abi_is_empty"] = isinstance(abi_data, list) and len(abi_data) == 0
    abi_fns = _extract_abi_functions(abi_data) if abi_data else set()
    row["abi_function_count"] = len(abi_fns)

    # Get Solidity contract functions
    sol_files = _find_files(proj / "contracts", {".sol"}) if has_contracts else []
    all_sol_fns = set()
    for sf in sol_files:
        all_sol_fns |= _extract_sol_functions(_read_text(sf))
    row["sol_function_count"] = len(all_sol_fns)

    # ABI vs contract mismatch
    if abi_fns and all_sol_fns:
        missing_in_abi = all_sol_fns - abi_fns
        extra_in_abi = abi_fns - all_sol_fns
        row["abi_missing_fns"] = len(missing_in_abi)
        row["abi_extra_fns"] = len(extra_in_abi)
        row["abi_match_ratio"] = len(abi_fns & all_sol_fns) / max(len(all_sol_fns), 1)
    else:
        row["abi_missing_fns"] = len(all_sol_fns) if all_sol_fns else 0
        row["abi_extra_fns"] = len(abi_fns) if abi_fns else 0
        row["abi_match_ratio"] = 0.0 if all_sol_fns else 1.0

    # Check for hardcoded placeholder ABIs in JS (getValue/setValue pattern)
    js_files = _find_files(proj, {".js", ".jsx"})
    js_text_all = "\n".join(_read_text(f) for f in js_files[:30])  # limit
    row["has_placeholder_abi"] = bool(re.search(
        r'"name"\s*:\s*"(getValue|setValue)"', js_text_all
    ))

    # ── 3. Env var checks ──
    env_refs = _find_env_references(js_files)
    row["env_vars_referenced"] = len(env_refs)

    # Collect all env definitions from .env files
    env_defined = set()
    for env_file in [proj / ".env", proj / ".env.example",
                     proj / "backend" / ".env", proj / "backend" / ".env.example"]:
        if env_file.exists():
            env_defined |= _parse_env_file(env_file)
    row["env_vars_defined"] = len(env_defined)

    # Missing env vars (referenced but not defined anywhere)
    missing_env = set(env_refs.keys()) - env_defined
    # Exclude NODE_ENV and common React defaults that CRA injects
    builtin = {"NODE_ENV", "PUBLIC_URL", "FAST_REFRESH"}
    missing_env -= builtin
    row["env_vars_missing"] = len(missing_env)
    row["env_vars_missing_list"] = ";".join(sorted(missing_env))

    # Check for CONTRACT_ADDRESS vs PROJECT_NAME_ADDRESS inconsistency
    has_generic_contract_addr = "CONTRACT_ADDRESS" in env_refs
    project_specific_addrs = [k for k in env_refs if k.endswith("_ADDRESS") and k != "CONTRACT_ADDRESS"]
    row["env_addr_inconsistency"] = has_generic_contract_addr and len(project_specific_addrs) > 0

    # ── 4. Placeholder addresses ──
    env_vals = {}
    for env_file in [proj / ".env", proj / "backend" / ".env"]:
        if env_file.exists():
            env_vals.update(_get_env_values(env_file))

    zero_addrs = [k for k, v in env_vals.items() if ZERO_ADDR in v.lower()]
    row["zero_address_count"] = len(zero_addrs)
    row["zero_address_vars"] = ";".join(zero_addrs)

    # ── 5. Missing infrastructure ──
    row["has_hardhat_config"] = (proj / "hardhat.config.js").exists() or (proj / "hardhat.config.ts").exists()
    row["has_deploy_script"] = (proj / "scripts" / "deploy.js").exists() or (proj / "scripts" / "deploy.ts").exists()
    row["has_docker_compose"] = (proj / "docker-compose.yml").exists() or (proj / "docker-compose.yaml").exists()
    row["has_dockerfile"] = any(_find_files(proj, {"Dockerfile"}))

    # Check if package.json references deploy but script is missing
    pkg = _read_json(proj / "package.json")
    if pkg and isinstance(pkg.get("scripts"), dict):
        deploy_cmd = pkg["scripts"].get("deploy", "")
        row["pkg_references_deploy"] = bool(deploy_cmd)
        row["deploy_script_broken"] = bool(deploy_cmd) and not row["has_deploy_script"]
    else:
        row["pkg_references_deploy"] = False
        row["deploy_script_broken"] = False

    # ── 6. Port conflicts ──
    backend_app = proj / "backend" / "app.js"
    if backend_app.exists():
        app_text = _read_text(backend_app)
        port_match = re.search(r'(?:PORT|port)\s*(?:\|\||\?\?)\s*(\d+)', app_text)
        row["backend_default_port"] = int(port_match.group(1)) if port_match else -1
    else:
        row["backend_default_port"] = -1

    fe_pkg = _read_json(proj / "frontend" / "package.json")
    fe_port = 3000  # React default
    if fe_pkg and isinstance(fe_pkg.get("scripts"), dict):
        start_cmd = fe_pkg["scripts"].get("start", "")
        pm = re.search(r'PORT=(\d+)', start_cmd)
        if pm:
            fe_port = int(pm.group(1))
    row["frontend_default_port"] = fe_port

    row["port_conflict"] = (
        row["backend_default_port"] == row["frontend_default_port"]
        and row["backend_default_port"] > 0
    )

    # Check if .env defines different port but backend doesn't read it
    env_port = env_vals.get("BACKEND_PORT", env_vals.get("PORT", ""))
    if env_port and row["backend_default_port"] > 0:
        try:
            row["env_port_mismatch"] = int(env_port) != row["backend_default_port"]
        except ValueError:
            row["env_port_mismatch"] = False
    else:
        row["env_port_mismatch"] = False

    # ── 7. Broken require paths ──
    broken_reqs = _check_require_paths(js_files[:30], proj)
    row["broken_requires"] = len(broken_reqs)
    row["broken_require_paths"] = ";".join(
        f"{b['file']}:{b['require']}" for b in broken_reqs[:5]
    )

    # ── 8. Solidity stubs ──
    sol_stubs = _check_sol_stubs(sol_files, proj)
    row["sol_stub_count"] = len(sol_stubs)
    row["sol_stub_functions"] = ";".join(s["function"] for s in sol_stubs)

    # ── 9. Frontend–backend disconnect ──
    disconnect = _check_frontend_backend_disconnect(proj)
    row["fe_calls_backend"] = disconnect.get("fe_calls_backend_api", False)
    row["fe_calls_contract_direct"] = disconnect.get("fe_calls_contract_direct", False)
    row["backend_has_routes"] = disconnect.get("backend_has_routes", False)
    row["dead_backend_api"] = disconnect.get("dead_backend_api", False)

    # ── 10. Composite deployment score ──
    issues = 0
    if row["abi_is_empty"]:
        issues += 1
    if row["has_placeholder_abi"]:
        issues += 1
    if row["abi_match_ratio"] < 0.5:
        issues += 1
    if row["env_vars_missing"] > 0:
        issues += 1
    if row["env_addr_inconsistency"]:
        issues += 1
    if row["zero_address_count"] > 0:
        issues += 1
    if not row["has_hardhat_config"]:
        issues += 1
    if row["deploy_script_broken"]:
        issues += 1
    if row["port_conflict"]:
        issues += 1
    if row["broken_requires"] > 0:
        issues += 1
    if row["sol_stub_count"] > 0:
        issues += 1
    if row["dead_backend_api"]:
        issues += 1
    row["total_issue_categories"] = issues
    row["deployment_viable"] = issues == 0

    return row


# ── Corpus discovery ─────────────────────────────────────────────────


def discover_dapps() -> list[Path]:
    """Return sorted list of unique DApp project directories."""
    if not MA_PATH.exists():
        print(f"ERROR: {MA_PATH} not found")
        sys.exit(1)

    projects = []
    seen = set()
    for d in sorted(MA_PATH.iterdir()):
        if not d.is_dir() or d.is_symlink():
            continue
        real = d.resolve()
        if real in seen:
            continue
        seen.add(real)
        projects.append(d)
    return projects


# ── Report generation ────────────────────────────────────────────────


def generate_report(rows: list[dict], out_path: Path):
    """Generate markdown report from audit results."""
    n = len(rows)
    lines = [
        f"# DApp Deployment Audit Report",
        f"",
        f"Audited **{n}** multi-agent DApp projects.",
        f"",
    ]

    # ── Summary ──
    def pct(count):
        return f"{count/n*100:.1f}%"

    def mean_val(key):
        vals = [r[key] for r in rows if isinstance(r[key], (int, float))]
        return sum(vals) / len(vals) if vals else 0

    viable = sum(1 for r in rows if r["deployment_viable"])
    lines += [
        f"## Executive Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Systems audited | {n} |",
        f"| **Deployment viable** | **{viable} ({pct(viable)})** |",
        f"| **Not viable** | **{n - viable} ({pct(n - viable)})** |",
        f"| Mean issue categories per system | {mean_val('total_issue_categories'):.1f} / 12 |",
        f"",
    ]

    # ── Issue breakdown ──
    checks = [
        ("abi_is_empty", "Empty ABI config file"),
        ("has_placeholder_abi", "Placeholder ABI (getValue/setValue)"),
        ("env_addr_inconsistency", "Env-var address naming mismatch"),
        ("port_conflict", "Backend/frontend port conflict"),
        ("dead_backend_api", "Dead backend API (frontend bypasses)"),
        ("deploy_script_broken", "Deploy script referenced but missing"),
    ]
    bool_checks_data = []
    for key, label in checks:
        count = sum(1 for r in rows if r.get(key))
        bool_checks_data.append((label, count, pct(count)))

    # Numeric checks
    num_checks = [
        ("zero_address_count", "> 0", "Placeholder zero addresses in .env"),
        ("env_vars_missing", "> 0", "Missing env vars (referenced but undefined)"),
        ("broken_requires", "> 0", "Broken require() paths"),
        ("sol_stub_count", "> 0", "Unimplemented Solidity function stubs"),
    ]
    for key, cond, label in num_checks:
        count = sum(1 for r in rows if r.get(key, 0) > 0)
        bool_checks_data.append((label, count, pct(count)))

    infra_checks = [
        ("has_hardhat_config", False, "Missing hardhat.config.js"),
        ("has_deploy_script", False, "Missing deploy script"),
        ("has_docker_compose", False, "No Docker Compose"),
    ]
    for key, target, label in infra_checks:
        count = sum(1 for r in rows if r.get(key) == target)
        bool_checks_data.append((label, count, pct(count)))

    lines += [
        f"## Issue Breakdown",
        f"",
        f"| Issue | Affected | % |",
        f"|-------|----------|---|",
    ]
    for label, count, p in sorted(bool_checks_data, key=lambda x: -x[1]):
        lines.append(f"| {label} | {count} | {p} |")
    lines.append("")

    # ── ABI analysis ──
    lines += [
        f"## ABI Analysis",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| ABI config file exists | {sum(1 for r in rows if r['abi_file_exists'])} ({pct(sum(1 for r in rows if r['abi_file_exists']))}) |",
        f"| ABI config is empty | {sum(1 for r in rows if r['abi_is_empty'])} ({pct(sum(1 for r in rows if r['abi_is_empty']))}) |",
        f"| Has placeholder ABI in JS | {sum(1 for r in rows if r['has_placeholder_abi'])} ({pct(sum(1 for r in rows if r['has_placeholder_abi']))}) |",
        f"| Mean Solidity functions | {mean_val('sol_function_count'):.1f} |",
        f"| Mean ABI functions | {mean_val('abi_function_count'):.1f} |",
        f"| Mean ABI match ratio | {mean_val('abi_match_ratio'):.3f} |",
        f"",
    ]

    # ── Env var analysis ──
    lines += [
        f"## Environment Variable Analysis",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean env vars referenced | {mean_val('env_vars_referenced'):.1f} |",
        f"| Mean env vars defined | {mean_val('env_vars_defined'):.1f} |",
        f"| Mean env vars MISSING | {mean_val('env_vars_missing'):.1f} |",
        f"| Address naming inconsistency | {sum(1 for r in rows if r['env_addr_inconsistency'])} ({pct(sum(1 for r in rows if r['env_addr_inconsistency']))}) |",
        f"| Zero addresses in .env | {sum(1 for r in rows if r['zero_address_count'] > 0)} ({pct(sum(1 for r in rows if r['zero_address_count'] > 0))}) |",
        f"",
    ]

    # Most commonly missing env vars
    from collections import Counter
    missing_counter = Counter()
    for r in rows:
        if r["env_vars_missing_list"]:
            for v in r["env_vars_missing_list"].split(";"):
                if v:
                    missing_counter[v] += 1
    if missing_counter:
        lines += [
            f"### Most Commonly Missing Env Vars",
            f"",
            f"| Variable | Missing In | % |",
            f"|----------|-----------|---|",
        ]
        for var, cnt in missing_counter.most_common(15):
            lines.append(f"| `{var}` | {cnt} | {pct(cnt)} |")
        lines.append("")

    # ── Infrastructure ──
    lines += [
        f"## Infrastructure Gaps",
        f"",
        f"| Check | Present | Missing |",
        f"|-------|---------|---------|",
        f"| hardhat.config.js | {sum(1 for r in rows if r['has_hardhat_config'])} | {sum(1 for r in rows if not r['has_hardhat_config'])} |",
        f"| scripts/deploy.js | {sum(1 for r in rows if r['has_deploy_script'])} | {sum(1 for r in rows if not r['has_deploy_script'])} |",
        f"| docker-compose.yml | {sum(1 for r in rows if r['has_docker_compose'])} | {sum(1 for r in rows if not r['has_docker_compose'])} |",
        f"| Dockerfile | {sum(1 for r in rows if r['has_dockerfile'])} | {sum(1 for r in rows if not r['has_dockerfile'])} |",
        f"",
    ]

    # ── Frontend–Backend architecture ──
    has_fe = [r for r in rows if r.get("has_frontend")]
    lines += [
        f"## Frontend–Backend Architecture ({len(has_fe)} projects with frontend)",
        f"",
        f"| Pattern | Count | % |",
        f"|---------|-------|---|",
        f"| Frontend calls backend API | {sum(1 for r in has_fe if r['fe_calls_backend'])} | {sum(1 for r in has_fe if r['fe_calls_backend'])/max(len(has_fe),1)*100:.1f}% |",
        f"| Frontend calls contract directly | {sum(1 for r in has_fe if r['fe_calls_contract_direct'])} | {sum(1 for r in has_fe if r['fe_calls_contract_direct'])/max(len(has_fe),1)*100:.1f}% |",
        f"| Backend has API routes | {sum(1 for r in has_fe if r['backend_has_routes'])} | {sum(1 for r in has_fe if r['backend_has_routes'])/max(len(has_fe),1)*100:.1f}% |",
        f"| **Dead backend API** | {sum(1 for r in has_fe if r['dead_backend_api'])} | {sum(1 for r in has_fe if r['dead_backend_api'])/max(len(has_fe),1)*100:.1f}% |",
        f"",
    ]

    # ── Solidity stubs ──
    stub_systems = sum(1 for r in rows if r["sol_stub_count"] > 0)
    lines += [
        f"## Solidity Function Stubs",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Systems with stub functions | {stub_systems} ({pct(stub_systems)}) |",
        f"| Mean stubs per system (if any) | {sum(r['sol_stub_count'] for r in rows if r['sol_stub_count']>0)/max(stub_systems,1):.1f} |",
        f"",
    ]

    # Most common stub function names
    stub_counter = Counter()
    for r in rows:
        if r["sol_stub_functions"]:
            for fn in r["sol_stub_functions"].split(";"):
                if fn:
                    stub_counter[fn] += 1
    if stub_counter:
        lines += [
            f"### Most Common Stub Functions",
            f"",
            f"| Function | Occurrences |",
            f"|----------|-------------|",
        ]
        for fn, cnt in stub_counter.most_common(10):
            lines.append(f"| `{fn}()` | {cnt} |")
        lines.append("")

    # ── Broken requires ──
    broken_systems = sum(1 for r in rows if r["broken_requires"] > 0)
    lines += [
        f"## Broken Import Paths",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Systems with broken requires | {broken_systems} ({pct(broken_systems)}) |",
        f"| Mean broken requires per system | {mean_val('broken_requires'):.1f} |",
        f"",
    ]

    # ── Issue distribution ──
    from collections import Counter as Ctr
    dist = Ctr(r["total_issue_categories"] for r in rows)
    lines += [
        f"## Issue Count Distribution",
        f"",
        f"| Issue Categories | Systems | % |",
        f"|-----------------|---------|---|",
    ]
    for k in sorted(dist.keys()):
        lines.append(f"| {k} | {dist[k]} | {pct(dist[k])} |")
    lines.append("")

    # ── Comparison with tier metrics ──
    lines += [
        f"## Comparison: Tier Metrics vs Deployment Audit",
        f"",
        f"| Perspective | Tier Metrics | Deployment Audit |",
        f"|-------------|-------------|------------------|",
        f"| Deployable | 100% (DFR=DEPLOYABLE) | {pct(viable)} viable |",
        f"| Config completeness | CCS=0.867 (2 unresolved) | {mean_val('env_vars_missing'):.1f} missing env vars |",
        f"| Reference integrity | URR=0.091 (2 unresolved) | {mean_val('broken_requires'):.1f} broken requires |",
        f"| ABI integrity | Not measured | {pct(sum(1 for r in rows if r['abi_is_empty']))} empty ABI |",
        f"| Port conflicts | Not measured | {pct(sum(1 for r in rows if r['port_conflict']))} conflicts |",
        f"| Dead code | Not measured | {pct(sum(1 for r in rows if r['dead_backend_api']))} dead backend |",
        f"| Infrastructure | Not measured | {pct(sum(1 for r in rows if not r['has_hardhat_config']))} no hardhat |",
        f"",
        f"**Key insight**: Tier metrics report 100% deployment feasibility based on",
        f"cycle-free dependency graphs. The deployment audit reveals that **{pct(n - viable)}**",
        f"of systems would fail to deploy due to missing configs, broken ABIs,",
        f"unresolved env vars, and missing infrastructure.",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved report to {out_path}")


# ── Main ─────────────────────────────────────────────────────────────


def main():
    projects = discover_dapps()
    print(f"Discovered {len(projects)} unique DApp projects")

    rows = []
    t0 = time.time()
    for i, proj in enumerate(projects):
        if (i + 1) % 20 == 0 or i == 0:
            print(f"[{i+1}/{len(projects)}] Auditing {proj.name[:12]}...")
        try:
            row = audit_project(proj)
            rows.append(row)
        except Exception as e:
            print(f"  ERROR on {proj.name}: {e}")
            rows.append({"project_id": proj.name, "error": str(e)})

    elapsed = time.time() - t0
    print(f"\nCompleted {len(rows)} audits in {elapsed:.1f}s ({elapsed/len(rows):.2f}s/system)")

    # Save CSV
    csv_path = RESULTS / "dapp_audit_data.csv"
    if rows:
        keys = rows[0].keys()
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {len(rows)} rows to {csv_path}")

    # Generate report
    report_path = RESULTS / "dapp_audit_report.md"
    generate_report(rows, report_path)

    print(f"Done.")


if __name__ == "__main__":
    main()

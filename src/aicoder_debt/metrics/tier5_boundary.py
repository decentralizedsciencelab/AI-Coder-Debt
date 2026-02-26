"""Tier 5 Boundary Metrics: DRS (Deployment Readiness Score), THI (Template Homogeneity Index).

Two domain-specific checkers:

  **BoundaryMetrics**        — 12 checks for DApp (Solidity + JS) projects
  **PythonBoundaryMetrics**  — 12 checks for Python projects

Each check asks: "Is this inter-component boundary intact?"
The Deployment Readiness Score is simply:

    DRS = passing_checks / total_applicable_checks

THI measures cross-project template homogeneity via pairwise Jaccard
similarity of normalised file-tree fingerprints.
"""

from __future__ import annotations

import ast
import json
import os
import re
from itertools import combinations
from pathlib import Path

from ..models import BoundaryCheck, DRSResult, THIResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _find_files(root: Path, extensions: set[str]) -> list[Path]:
    """Walk *root* collecting files whose names end with any of *extensions*."""
    found: list[Path] = []
    if not root.exists():
        return found
    skip = {"node_modules", ".git", "__pycache__", "venv", ".next", "build",
            "dist", "artifacts", "cache", "coverage"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if any(fn.endswith(ext) for ext in extensions):
                found.append(Path(dirpath) / fn)
    return found


def _extract_sol_functions(sol_text: str) -> set[str]:
    fns: set[str] = set()
    for m in re.finditer(r"\bfunction\s+(\w+)\s*\(", sol_text):
        name = m.group(1)
        if name != "constructor":
            fns.add(name)
    return fns


def _extract_abi_functions(abi: list) -> set[str]:
    fns: set[str] = set()
    if not isinstance(abi, list):
        return fns
    for entry in abi:
        if isinstance(entry, dict) and entry.get("type") == "function":
            name = entry.get("name", "")
            if name:
                fns.add(name)
    return fns


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _parse_env_file(env_path: Path) -> set[str]:
    defined: set[str] = set()
    for line in _read_text(env_path).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key:
                defined.add(key)
    return defined


def _get_env_values(env_path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    for line in _read_text(env_path).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals


# ---------------------------------------------------------------------------
# The 12 Boundary Checks
# ---------------------------------------------------------------------------

class BoundaryMetrics:
    """Calculate Tier 5 boundary metrics: DRS and THI."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path).resolve()

    # -- individual checks --------------------------------------------------

    def _check_abi_exists(self) -> BoundaryCheck:
        """Check 1: ABI file exists and is non-empty."""
        abi_path = self.project_path / "backend" / "config" / "contractABI.json"
        if not abi_path.exists():
            # Also try common alternative locations
            for alt in [
                self.project_path / "abi" / "contractABI.json",
                self.project_path / "artifacts",
            ]:
                if alt.exists():
                    abi_path = alt
                    break

        if not abi_path.exists():
            has_contracts = (self.project_path / "contracts").is_dir()
            return BoundaryCheck(
                name="abi_exists",
                passed=False,
                applicable=has_contracts,
                detail="No ABI file found",
            )

        data = _read_json(abi_path) if abi_path.is_file() else None
        non_empty = isinstance(data, list) and len(data) > 0
        return BoundaryCheck(
            name="abi_exists",
            passed=non_empty,
            applicable=True,
            detail=f"ABI has {len(data) if isinstance(data, list) else 0} entries",
        )

    def _check_abi_matches_contract(self) -> BoundaryCheck:
        """Check 2: ABI functions match contract functions (Jaccard > 0.5)."""
        has_contracts = (self.project_path / "contracts").is_dir()
        if not has_contracts:
            return BoundaryCheck(
                name="abi_matches_contract",
                passed=True,
                applicable=False,
                detail="No contracts directory",
            )

        sol_files = _find_files(self.project_path / "contracts", {".sol"})
        sol_fns: set[str] = set()
        for sf in sol_files:
            sol_fns |= _extract_sol_functions(_read_text(sf))

        abi_path = self.project_path / "backend" / "config" / "contractABI.json"
        abi_data = _read_json(abi_path) if abi_path.exists() else None
        abi_fns = _extract_abi_functions(abi_data) if abi_data else set()

        if not sol_fns:
            return BoundaryCheck(
                name="abi_matches_contract",
                passed=True,
                applicable=False,
                detail="No Solidity functions found",
            )

        j = _jaccard(abi_fns, sol_fns)
        return BoundaryCheck(
            name="abi_matches_contract",
            passed=j > 0.5,
            applicable=True,
            detail=f"Jaccard={j:.3f} (ABI:{len(abi_fns)}, Sol:{len(sol_fns)})",
        )

    def _check_no_placeholder_abi(self) -> BoundaryCheck:
        """Check 3: No placeholder ABI (getValue/setValue template stubs)."""
        js_files = _find_files(self.project_path, {".js", ".jsx"})[:30]
        all_text = "\n".join(_read_text(f) for f in js_files)
        has_placeholder = bool(
            re.search(r'"name"\s*:\s*"(getValue|setValue)"', all_text)
        )
        return BoundaryCheck(
            name="no_placeholder_abi",
            passed=not has_placeholder,
            applicable=True,
            detail="Placeholder ABI detected" if has_placeholder else "OK",
        )

    def _check_frontend_calls_backend(self) -> BoundaryCheck:
        """Check 4: Frontend calls backend (if backend exists)."""
        has_backend = (self.project_path / "backend").is_dir()
        frontend_src = self.project_path / "frontend" / "src"
        if not has_backend or not frontend_src.exists():
            return BoundaryCheck(
                name="frontend_calls_backend",
                passed=True,
                applicable=False,
                detail="No frontend+backend pair",
            )

        fe_files = _find_files(frontend_src, {".js", ".jsx", ".ts", ".tsx"})
        fe_text = "\n".join(_read_text(f) for f in fe_files[:30])
        api_patterns = [
            r"fetch\s*\(",
            r"axios\.",
            r"\.get\s*\([\"']/",
            r"\.post\s*\([\"']/",
            r"BACKEND_URL",
            r"API_URL",
        ]
        has_calls = any(re.search(p, fe_text) for p in api_patterns)
        return BoundaryCheck(
            name="frontend_calls_backend",
            passed=has_calls,
            applicable=True,
            detail="Frontend calls backend API" if has_calls else "Frontend does NOT call backend",
        )

    def _check_no_dead_backend_routes(self) -> BoundaryCheck:
        """Check 5: No dead backend routes (generated but unused)."""
        backend_dir = self.project_path / "backend"
        frontend_src = self.project_path / "frontend" / "src"
        if not backend_dir.is_dir() or not frontend_src.exists():
            return BoundaryCheck(
                name="no_dead_backend_routes",
                passed=True,
                applicable=False,
                detail="No frontend+backend pair",
            )

        be_files = _find_files(backend_dir, {".js"})
        be_text = "\n".join(_read_text(f) for f in be_files[:30])
        has_routes = bool(
            re.search(
                r"(router\.(get|post|put|delete)|app\.(get|post|put|delete))\s*\(",
                be_text,
            )
        )
        if not has_routes:
            return BoundaryCheck(
                name="no_dead_backend_routes",
                passed=True,
                applicable=False,
                detail="Backend has no routes",
            )

        fe_files = _find_files(frontend_src, {".js", ".jsx", ".ts", ".tsx"})
        fe_text = "\n".join(_read_text(f) for f in fe_files[:30])
        api_patterns = [r"fetch\s*\(", r"axios\.", r"BACKEND_URL", r"API_URL"]
        fe_calls_backend = any(re.search(p, fe_text) for p in api_patterns)

        return BoundaryCheck(
            name="no_dead_backend_routes",
            passed=fe_calls_backend,
            applicable=True,
            detail="OK" if fe_calls_backend else "Backend routes exist but frontend never calls them",
        )

    def _check_env_vars_defined(self) -> BoundaryCheck:
        """Check 6: All process.env refs are defined."""
        js_files = _find_files(self.project_path, {".js", ".jsx", ".ts", ".tsx"})[:50]
        refs: set[str] = set()
        for fp in js_files:
            for m in re.finditer(r"process\.env\.(\w+)", _read_text(fp)):
                refs.add(m.group(1))

        if not refs:
            return BoundaryCheck(
                name="env_vars_defined",
                passed=True,
                applicable=False,
                detail="No process.env references",
            )

        # Collect definitions from .env files
        env_defined: set[str] = set()
        for env_file in [
            self.project_path / ".env",
            self.project_path / ".env.example",
            self.project_path / "backend" / ".env",
            self.project_path / "backend" / ".env.example",
            self.project_path / "frontend" / ".env",
        ]:
            if env_file.exists():
                env_defined |= _parse_env_file(env_file)

        # Exclude well-known builtins
        builtins = {"NODE_ENV", "PUBLIC_URL", "FAST_REFRESH"}
        missing = refs - env_defined - builtins
        return BoundaryCheck(
            name="env_vars_defined",
            passed=len(missing) == 0,
            applicable=True,
            detail=f"{len(missing)} undefined: {', '.join(sorted(missing)[:5])}" if missing else "OK",
        )

    def _check_no_placeholder_addresses(self) -> BoundaryCheck:
        """Check 7: No zero/placeholder addresses in env files."""
        zero_addr = "0x" + "0" * 40
        env_vals: dict[str, str] = {}
        for env_file in [self.project_path / ".env", self.project_path / "backend" / ".env"]:
            if env_file.exists():
                env_vals.update(_get_env_values(env_file))

        if not env_vals:
            return BoundaryCheck(
                name="no_placeholder_addresses",
                passed=True,
                applicable=False,
                detail="No .env files",
            )

        placeholders = [k for k, v in env_vals.items() if zero_addr in v.lower()]
        return BoundaryCheck(
            name="no_placeholder_addresses",
            passed=len(placeholders) == 0,
            applicable=True,
            detail=f"{len(placeholders)} placeholder addresses: {', '.join(placeholders[:3])}"
            if placeholders else "OK",
        )

    def _check_no_port_conflicts(self) -> BoundaryCheck:
        """Check 8: No port conflicts between frontend and backend."""
        backend_app = self.project_path / "backend" / "app.js"
        if not backend_app.exists():
            return BoundaryCheck(
                name="no_port_conflicts",
                passed=True,
                applicable=False,
                detail="No backend app.js",
            )

        app_text = _read_text(backend_app)
        port_match = re.search(r"(?:PORT|port)\s*(?:\|\||\?\?)\s*(\d+)", app_text)
        be_port = int(port_match.group(1)) if port_match else -1

        fe_port = 3000  # React default
        fe_pkg = _read_json(self.project_path / "frontend" / "package.json")
        if fe_pkg and isinstance(fe_pkg.get("scripts"), dict):
            start_cmd = fe_pkg["scripts"].get("start", "")
            pm = re.search(r"PORT=(\d+)", start_cmd)
            if pm:
                fe_port = int(pm.group(1))

        conflict = be_port == fe_port and be_port > 0
        return BoundaryCheck(
            name="no_port_conflicts",
            passed=not conflict,
            applicable=be_port > 0,
            detail=f"Port conflict: both use {be_port}" if conflict else "OK",
        )

    def _check_build_config_exists(self) -> BoundaryCheck:
        """Check 9: Build tool config exists (hardhat, truffle, etc.)."""
        configs = [
            self.project_path / "hardhat.config.js",
            self.project_path / "hardhat.config.ts",
            self.project_path / "truffle-config.js",
            self.project_path / "foundry.toml",
        ]
        has_contracts = (self.project_path / "contracts").is_dir()
        found = any(c.exists() for c in configs)
        return BoundaryCheck(
            name="build_config_exists",
            passed=found,
            applicable=has_contracts,
            detail="Build config found" if found else "No build config (hardhat/truffle/foundry)",
        )

    def _check_deploy_script_exists(self) -> BoundaryCheck:
        """Check 10: Deploy script exists."""
        scripts = [
            self.project_path / "scripts" / "deploy.js",
            self.project_path / "scripts" / "deploy.ts",
            self.project_path / "deploy" / "deploy.js",
            self.project_path / "migrations" / "1_deploy.js",
        ]
        has_contracts = (self.project_path / "contracts").is_dir()
        found = any(s.exists() for s in scripts)
        return BoundaryCheck(
            name="deploy_script_exists",
            passed=found,
            applicable=has_contracts,
            detail="Deploy script found" if found else "No deploy script",
        )

    def _check_imports_resolve(self) -> BoundaryCheck:
        """Check 11: All internal require('./...') paths resolve."""
        js_files = _find_files(self.project_path, {".js", ".jsx"})[:30]
        broken = 0
        total = 0
        for fp in js_files:
            text = _read_text(fp)
            for m in re.finditer(r"""require\s*\(\s*['"](\.[^'"]+)['"]\s*\)""", text):
                total += 1
                req_path = m.group(1)
                resolved = (fp.parent / req_path).resolve()
                candidates = [
                    resolved,
                    resolved.with_suffix(".js"),
                    resolved.with_suffix(".json"),
                    resolved / "index.js",
                ]
                if not any(c.exists() for c in candidates):
                    broken += 1

        if total == 0:
            return BoundaryCheck(
                name="imports_resolve",
                passed=True,
                applicable=False,
                detail="No internal require() calls",
            )

        return BoundaryCheck(
            name="imports_resolve",
            passed=broken == 0,
            applicable=True,
            detail=f"{broken}/{total} broken require() paths" if broken else "OK",
        )

    def _check_tests_match_contract(self) -> BoundaryCheck:
        """Check 12: Test functions match contract functions."""
        has_contracts = (self.project_path / "contracts").is_dir()
        test_dir = self.project_path / "test"
        if not has_contracts or not test_dir.is_dir():
            return BoundaryCheck(
                name="tests_match_contract",
                passed=True,
                applicable=False,
                detail="No contracts or test directory",
            )

        # Collect Solidity function names
        sol_files = _find_files(self.project_path / "contracts", {".sol"})
        sol_fns: set[str] = set()
        for sf in sol_files:
            sol_fns |= _extract_sol_functions(_read_text(sf))

        if not sol_fns:
            return BoundaryCheck(
                name="tests_match_contract",
                passed=True,
                applicable=False,
                detail="No Solidity functions",
            )

        # Collect function names mentioned in test files
        test_files = _find_files(test_dir, {".js", ".ts"})
        test_text = "\n".join(_read_text(f) for f in test_files[:20])

        # Count how many contract functions appear in tests
        tested = {fn for fn in sol_fns if fn in test_text}
        coverage = len(tested) / len(sol_fns) if sol_fns else 1.0
        return BoundaryCheck(
            name="tests_match_contract",
            passed=coverage > 0.5,
            applicable=True,
            detail=f"Test coverage of contract functions: {coverage:.0%} ({len(tested)}/{len(sol_fns)})",
        )

    # -- DRS (aggregate) ----------------------------------------------------

    def calculate_drs(self) -> DRSResult:
        """Calculate Deployment Readiness Score from the 12 boundary checks."""
        checks = [
            self._check_abi_exists(),
            self._check_abi_matches_contract(),
            self._check_no_placeholder_abi(),
            self._check_frontend_calls_backend(),
            self._check_no_dead_backend_routes(),
            self._check_env_vars_defined(),
            self._check_no_placeholder_addresses(),
            self._check_no_port_conflicts(),
            self._check_build_config_exists(),
            self._check_deploy_script_exists(),
            self._check_imports_resolve(),
            self._check_tests_match_contract(),
        ]

        applicable = [c for c in checks if c.applicable]
        passing = [c for c in applicable if c.passed]

        score = len(passing) / len(applicable) if applicable else 0.0

        return DRSResult(
            score=score,
            passing_checks=len(passing),
            total_applicable=len(applicable),
            checks=checks,
        )


# ---------------------------------------------------------------------------
# Python Boundary Checks (12 checks)
# ---------------------------------------------------------------------------

# Python standard-library module names (top-level only, for filtering)
_PY_STDLIB = {
    "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
    "base64", "binascii", "bisect", "builtins", "bz2", "calendar",
    "cgi", "cmd", "code", "codecs", "collections", "colorsys",
    "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "csv", "ctypes", "curses", "dataclasses",
    "datetime", "dbm", "decimal", "difflib", "dis", "distutils",
    "doctest", "email", "encodings", "enum", "errno", "faulthandler",
    "fcntl", "filecmp", "fileinput", "fnmatch", "fractions", "ftplib",
    "functools", "gc", "getopt", "getpass", "gettext", "glob",
    "graphlib", "grp", "gzip", "hashlib", "heapq", "hmac", "html",
    "http", "idlelib", "imaplib", "importlib", "inspect", "io",
    "ipaddress", "itertools", "json", "keyword", "linecache", "locale",
    "logging", "lzma", "mailbox", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "numbers",
    "operator", "optparse", "os", "pathlib", "pdb", "pickle",
    "pkgutil", "platform", "plistlib", "poplib", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtplib", "socket", "socketserver", "sqlite3", "ssl", "stat",
    "statistics", "string", "struct", "subprocess", "sunau", "symtable",
    "sys", "sysconfig", "syslog", "tabnanny", "tarfile", "tempfile",
    "termios", "test", "textwrap", "threading", "time", "timeit",
    "tkinter", "token", "tokenize", "tomllib", "trace", "traceback",
    "tracemalloc", "tty", "turtle", "types", "typing", "unicodedata",
    "unittest", "urllib", "uuid", "venv", "warnings", "wave",
    "weakref", "webbrowser", "wsgiref", "xml", "xmlrpc", "zipapp",
    "zipfile", "zipimport", "zlib", "zoneinfo",
    # underscore-prefixed internals
    "_thread", "__future__",
}

_PY_SKIP_DIRS = {
    "__pycache__", ".git", ".tox", ".nox", "venv", ".venv",
    "node_modules", ".eggs", "build", "dist", ".mypy_cache",
    ".pytest_cache", "htmlcov", "coverage", "*.egg-info",
}


def _find_py_files(root: Path) -> list[Path]:
    """Collect *.py files under *root*, skipping common junk dirs."""
    found: list[Path] = []
    if not root.exists():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _PY_SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                found.append(Path(dirpath) / fn)
    return found


def _extract_python_imports(source: str) -> list[tuple[str, bool]]:
    """Return list of (top-level module name, is_relative) from *source*.

    Uses AST so it handles ``import foo``, ``from foo import bar``,
    and relative imports (``from . import baz``).
    """
    results: list[tuple[str, bool]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                results.append((top, False))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import — always internal
                mod = node.module or ""
                top = mod.split(".")[0] if mod else ""
                results.append((top, True))
            elif node.module:
                top = node.module.split(".")[0]
                results.append((top, False))
    return results


def _parse_requirements_txt(path: Path) -> set[str]:
    """Extract package names from a requirements.txt file."""
    pkgs: set[str] = set()
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip version specifiers, extras, etc.
        name = re.split(r"[><=!~;\[\s]", line, maxsplit=1)[0].strip()
        if name:
            # Normalise (PEP 503): lowercase, replace - and . with _
            pkgs.add(re.sub(r"[-.]", "_", name).lower())
    return pkgs


def _parse_pyproject_deps(path: Path) -> set[str]:
    """Extract dependency names from pyproject.toml (best-effort regex)."""
    pkgs: set[str] = set()
    text = _read_text(path)
    # Match lines inside [project] dependencies = [...] or
    # [tool.poetry.dependencies]
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"\[.*dependenc", stripped, re.IGNORECASE):
            in_deps = True
            continue
        if stripped.startswith("[") and in_deps:
            in_deps = False
            continue
        if in_deps:
            # "requests>=2.0" or requests = "^2.0"
            m = re.match(r'"?([A-Za-z0-9_.-]+)', stripped)
            if m:
                name = re.sub(r"[-.]", "_", m.group(1)).lower()
                if name not in ("python",):
                    pkgs.add(name)
    return pkgs


def _find_package_names(project_path: Path) -> set[str]:
    """Return all names the project might be imported as.

    Returns a set containing:
      - The distribution name from pyproject.toml / setup.py (normalised)
      - The actual importable directory name(s) (directories with __init__.py)
    """
    names: set[str] = set()

    # Distribution name from pyproject.toml
    pp = project_path / "pyproject.toml"
    if pp.exists():
        for line in _read_text(pp).splitlines():
            m = re.match(r'\s*name\s*=\s*"([^"]+)"', line)
            if m:
                names.add(re.sub(r"[-.]", "_", m.group(1)).lower())
                break

    # Distribution name from setup.py / setup.cfg
    for cfg_file in [project_path / "setup.cfg", project_path / "setup.py"]:
        if cfg_file.exists():
            for line in _read_text(cfg_file).splitlines():
                m = re.match(r"\s*name\s*=\s*['\"]?([A-Za-z0-9_.-]+)", line)
                if m:
                    names.add(re.sub(r"[-.]", "_", m.group(1)).lower())
                    break

    # Actual importable package directories (dirs with __init__.py)
    skip = {"tests", "test", "docs", "scripts", "examples", "benchmarks"}
    for candidate_root in [project_path / "src", project_path]:
        if candidate_root.is_dir():
            for child in sorted(candidate_root.iterdir()):
                if (
                    child.is_dir()
                    and (child / "__init__.py").exists()
                    and child.name not in skip
                ):
                    names.add(child.name)

    return names


def _find_package_name(project_path: Path) -> str | None:
    """Return the primary package name (first importable dir, or dist name)."""
    names = _find_package_names(project_path)
    if not names:
        return None
    # Prefer the actual directory name over the distribution name
    skip = {"tests", "test", "docs", "scripts", "examples", "benchmarks"}
    for candidate_root in [project_path / "src", project_path]:
        if candidate_root.is_dir():
            for child in sorted(candidate_root.iterdir()):
                if (
                    child.is_dir()
                    and (child / "__init__.py").exists()
                    and child.name not in skip
                    and child.name in names
                ):
                    return child.name
    return next(iter(names))


class PythonBoundaryMetrics:
    """Calculate Tier 5 boundary metrics for Python projects (12 checks)."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path).resolve()
        self._py_files: list[Path] | None = None
        self._package_name: str | None = None
        self._package_names: set[str] | None = None

    @property
    def py_files(self) -> list[Path]:
        if self._py_files is None:
            self._py_files = _find_py_files(self.project_path)
        return self._py_files

    @property
    def package_name(self) -> str | None:
        if self._package_name is None:
            self._package_name = _find_package_name(self.project_path)
        return self._package_name

    @property
    def package_names(self) -> set[str]:
        if self._package_names is None:
            self._package_names = _find_package_names(self.project_path)
        return self._package_names

    # -- individual checks --------------------------------------------------

    def _check_internal_imports_resolve(self) -> BoundaryCheck:
        """Check 1: All relative / intra-package imports resolve to files."""
        broken = 0
        total = 0
        for fp in self.py_files:
            source = _read_text(fp)
            for mod, is_relative in _extract_python_imports(source):
                if not is_relative:
                    continue
                total += 1
                if not mod:
                    # bare "from . import x" — valid if in a package
                    if not (fp.parent / "__init__.py").exists():
                        broken += 1
                    continue
                # Try to resolve: look for mod.py or mod/__init__.py
                # relative to the file's directory
                parts = mod.split(".")
                base = fp.parent
                target = base / "/".join(parts)
                if not (
                    target.with_suffix(".py").exists()
                    or (target / "__init__.py").exists()
                ):
                    broken += 1

        if total == 0:
            return BoundaryCheck(
                name="internal_imports_resolve",
                passed=True,
                applicable=False,
                detail="No relative imports found",
            )
        return BoundaryCheck(
            name="internal_imports_resolve",
            passed=broken == 0,
            applicable=True,
            detail=f"{broken}/{total} broken relative imports" if broken else "OK",
        )

    def _check_requirements_exist(self) -> BoundaryCheck:
        """Check 2: Dependency manifest exists (requirements.txt / pyproject.toml / setup.py)."""
        manifests = [
            self.project_path / "requirements.txt",
            self.project_path / "pyproject.toml",
            self.project_path / "setup.py",
            self.project_path / "setup.cfg",
            self.project_path / "Pipfile",
        ]
        found = [m for m in manifests if m.exists()]
        return BoundaryCheck(
            name="requirements_exist",
            passed=len(found) > 0,
            applicable=True,
            detail=", ".join(f.name for f in found) if found else "No dependency manifest",
        )

    def _check_deps_match_imports(self) -> BoundaryCheck:
        """Check 3: Imported third-party packages are listed in requirements."""
        # Gather declared deps
        declared: set[str] = set()
        req_txt = self.project_path / "requirements.txt"
        if req_txt.exists():
            declared |= _parse_requirements_txt(req_txt)
        # Also check requirements/*.txt
        req_dir = self.project_path / "requirements"
        if req_dir.is_dir():
            for f in req_dir.glob("*.txt"):
                declared |= _parse_requirements_txt(f)
        pp = self.project_path / "pyproject.toml"
        if pp.exists():
            declared |= _parse_pyproject_deps(pp)

        if not declared:
            return BoundaryCheck(
                name="deps_match_imports",
                passed=True,
                applicable=False,
                detail="No declared dependencies to compare",
            )

        # Gather all imported third-party top-level module names
        imported: set[str] = set()
        for fp in self.py_files:
            source = _read_text(fp)
            for mod, is_relative in _extract_python_imports(source):
                if is_relative:
                    continue
                normalised = re.sub(r"[-.]", "_", mod).lower()
                if normalised in _PY_STDLIB:
                    continue
                if self.package_name and normalised == self.package_name:
                    continue
                imported.add(normalised)

        if not imported:
            return BoundaryCheck(
                name="deps_match_imports",
                passed=True,
                applicable=False,
                detail="No third-party imports found",
            )

        # Common import-name ≠ package-name mappings
        aliases: dict[str, str] = {
            "cv2": "opencv_python", "PIL": "pillow", "pil": "pillow",
            "sklearn": "scikit_learn", "yaml": "pyyaml", "bs4": "beautifulsoup4",
            "attr": "attrs", "gi": "pygobject", "serial": "pyserial",
            "dotenv": "python_dotenv", "jwt": "pyjwt", "magic": "python_magic",
            "dateutil": "python_dateutil",
        }
        missing: set[str] = set()
        for imp in imported:
            normalised_imp = aliases.get(imp, imp)
            if normalised_imp not in declared:
                missing.add(imp)

        return BoundaryCheck(
            name="deps_match_imports",
            passed=len(missing) == 0,
            applicable=True,
            detail=f"{len(missing)} undeclared: {', '.join(sorted(missing)[:5])}"
            if missing else "OK",
        )

    def _check_env_vars_defined(self) -> BoundaryCheck:
        """Check 4: os.environ / os.getenv references have .env definitions."""
        refs: set[str] = set()
        patterns = [
            re.compile(r"""os\.environ\[['"](\w+)['"]\]"""),
            re.compile(r"""os\.environ\.get\(['"](\w+)['"]"""),
            re.compile(r"""os\.getenv\(['"](\w+)['"]"""),
        ]
        for fp in self.py_files:
            source = _read_text(fp)
            for pat in patterns:
                for m in pat.finditer(source):
                    refs.add(m.group(1))

        if not refs:
            return BoundaryCheck(
                name="env_vars_defined",
                passed=True,
                applicable=False,
                detail="No os.environ/os.getenv references",
            )

        env_defined: set[str] = set()
        for env_file in [
            self.project_path / ".env",
            self.project_path / ".env.example",
            self.project_path / ".env.template",
        ]:
            if env_file.exists():
                env_defined |= _parse_env_file(env_file)

        builtins = {"PATH", "HOME", "USER", "LANG", "SHELL", "TERM",
                     "PYTHONPATH", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV"}
        missing = refs - env_defined - builtins
        return BoundaryCheck(
            name="env_vars_defined",
            passed=len(missing) == 0,
            applicable=True,
            detail=f"{len(missing)} undefined: {', '.join(sorted(missing)[:5])}"
            if missing else "OK",
        )

    def _check_no_placeholder_config(self) -> BoundaryCheck:
        """Check 5: No placeholder / dummy values in config files."""
        placeholder_patterns = [
            re.compile(r"""=\s*['"]?(changeme|CHANGEME|TODO|todo|xxx|XXX|replace.?me|REPLACE.?ME|your.?secret|YOUR.?SECRET)['"]?\s*$"""),
            re.compile(r"""=\s*['"]?sk[-_](test|live)_[x]{10,}['"]?\s*$"""),  # fake API keys
        ]
        env_files = [
            self.project_path / ".env",
            self.project_path / ".env.example",
        ]
        hits: list[str] = []
        for ef in env_files:
            if not ef.exists():
                continue
            for line in _read_text(ef).splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for pat in placeholder_patterns:
                    if pat.search(line):
                        key = line.split("=", 1)[0].strip()
                        hits.append(key)
                        break

        if not any(ef.exists() for ef in env_files):
            return BoundaryCheck(
                name="no_placeholder_config",
                passed=True,
                applicable=False,
                detail="No .env files",
            )
        return BoundaryCheck(
            name="no_placeholder_config",
            passed=len(hits) == 0,
            applicable=True,
            detail=f"{len(hits)} placeholders: {', '.join(hits[:3])}"
            if hits else "OK",
        )

    def _check_entry_point_exists(self) -> BoundaryCheck:
        """Check 6: Project has a clear entry point."""
        candidates = [
            self.project_path / "main.py",
            self.project_path / "app.py",
            self.project_path / "manage.py",
            self.project_path / "wsgi.py",
            self.project_path / "asgi.py",
            self.project_path / "run.py",
            self.project_path / "cli.py",
        ]
        # Also check for __main__.py inside any known package directory
        for pkg_name in self.package_names:
            for root_dir in [self.project_path / "src", self.project_path]:
                pkg = root_dir / pkg_name
                if pkg.is_dir():
                    candidates.append(pkg / "__main__.py")

        # Check pyproject.toml for [project.scripts] or console_scripts
        pp = self.project_path / "pyproject.toml"
        has_console_scripts = False
        if pp.exists():
            text = _read_text(pp)
            if re.search(r"\[project\.scripts\]|\[tool\.poetry\.scripts\]|console_scripts", text):
                has_console_scripts = True

        found = [c for c in candidates if c.exists()]
        passed = len(found) > 0 or has_console_scripts
        if has_console_scripts:
            detail = "console_scripts defined in pyproject.toml"
        elif found:
            detail = ", ".join(f.name for f in found)
        else:
            detail = "No entry point (main.py, app.py, manage.py, __main__.py, console_scripts)"
        return BoundaryCheck(
            name="entry_point_exists",
            passed=passed,
            applicable=True,
            detail=detail,
        )

    def _check_tests_exist(self) -> BoundaryCheck:
        """Check 7: Test directory with actual test files exists."""
        test_dirs = [
            self.project_path / "tests",
            self.project_path / "test",
        ]
        # Also check src layout
        if self.package_name:
            test_dirs.append(self.project_path / "src" / "tests")

        test_files: list[Path] = []
        for td in test_dirs:
            if td.is_dir():
                test_files.extend(
                    f for f in _find_py_files(td) if f.name.startswith("test_")
                )

        # Also check for test files alongside source (test_*.py in project root)
        for f in self.py_files:
            if f.name.startswith("test_") and f.parent == self.project_path:
                test_files.append(f)

        return BoundaryCheck(
            name="tests_exist",
            passed=len(test_files) > 0,
            applicable=True,
            detail=f"{len(test_files)} test files" if test_files else "No test files found",
        )

    def _check_tests_import_project(self) -> BoundaryCheck:
        """Check 8: Test files actually import the project package."""
        names = self.package_names
        if not names:
            return BoundaryCheck(
                name="tests_import_project",
                passed=True,
                applicable=False,
                detail="Cannot determine package name",
            )

        test_dirs = [self.project_path / "tests", self.project_path / "test"]
        test_files: list[Path] = []
        for td in test_dirs:
            if td.is_dir():
                test_files.extend(
                    f for f in _find_py_files(td) if f.name.startswith("test_")
                )

        if not test_files:
            return BoundaryCheck(
                name="tests_import_project",
                passed=True,
                applicable=False,
                detail="No test files to check",
            )

        tests_with_import = 0
        for tf in test_files:
            source = _read_text(tf)
            if any(name in source for name in names):
                tests_with_import += 1

        coverage = tests_with_import / len(test_files) if test_files else 0.0
        return BoundaryCheck(
            name="tests_import_project",
            passed=coverage > 0.3,
            applicable=True,
            detail=f"{tests_with_import}/{len(test_files)} test files import {self.package_name}"
            if test_files else "OK",
        )

    def _check_no_circular_imports(self) -> BoundaryCheck:
        """Check 9: No obvious circular import patterns.

        Builds a simple module-level import graph from relative imports
        and checks for strongly-connected components of size > 1.
        """
        # Build adjacency list: module_path -> set of imported module_paths
        graph: dict[str, set[str]] = {}
        for fp in self.py_files:
            mod_key = str(fp.relative_to(self.project_path))
            graph.setdefault(mod_key, set())
            source = _read_text(fp)
            for mod, is_relative in _extract_python_imports(source):
                if not is_relative or not mod:
                    continue
                parts = mod.split(".")
                target = fp.parent / "/".join(parts)
                for candidate in [target.with_suffix(".py"), target / "__init__.py"]:
                    if candidate.exists():
                        try:
                            target_key = str(candidate.relative_to(self.project_path))
                            graph[mod_key].add(target_key)
                        except ValueError:
                            pass
                        break

        # Simple cycle detection via DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in graph}
        cycles_found = 0

        def dfs(node: str) -> bool:
            nonlocal cycles_found
            color[node] = GRAY
            for neighbour in graph.get(node, set()):
                if neighbour not in color:
                    continue
                if color[neighbour] == GRAY:
                    cycles_found += 1
                    return True
                if color[neighbour] == WHITE:
                    if dfs(neighbour):
                        return True
            color[node] = BLACK
            return False

        for node in list(graph):
            if color.get(node) == WHITE:
                dfs(node)

        return BoundaryCheck(
            name="no_circular_imports",
            passed=cycles_found == 0,
            applicable=len(graph) > 1,
            detail=f"{cycles_found} circular import chain(s) detected"
            if cycles_found else "OK",
        )

    def _check_dockerfile_exists(self) -> BoundaryCheck:
        """Check 10: Dockerfile or docker-compose exists for deployment.

        Only applicable for deployable applications (web frameworks, services).
        Libraries distributed via PyPI don't need Docker.
        """
        # Detect if this is a deployable app (not a library)
        app_signals = [
            self.project_path / "app.py",
            self.project_path / "manage.py",
            self.project_path / "wsgi.py",
            self.project_path / "asgi.py",
            self.project_path / "Procfile",
        ]
        web_frameworks = {"flask", "django", "fastapi", "uvicorn", "gunicorn",
                          "starlette", "tornado", "sanic", "aiohttp"}
        has_app_signal = any(s.exists() for s in app_signals)

        # Check if any web framework is imported
        if not has_app_signal:
            for fp in self.py_files[:30]:
                source = _read_text(fp)
                for fw in web_frameworks:
                    if f"import {fw}" in source or f"from {fw}" in source:
                        has_app_signal = True
                        break
                if has_app_signal:
                    break

        candidates = [
            self.project_path / "Dockerfile",
            self.project_path / "docker-compose.yml",
            self.project_path / "docker-compose.yaml",
            self.project_path / "compose.yml",
            self.project_path / "compose.yaml",
        ]
        found = [c for c in candidates if c.exists()]
        return BoundaryCheck(
            name="dockerfile_exists",
            passed=len(found) > 0,
            applicable=has_app_signal,
            detail=", ".join(f.name for f in found) if found else "No Dockerfile or compose file (deployable app)",
        )

    def _check_ci_config_exists(self) -> BoundaryCheck:
        """Check 11: CI/CD configuration exists."""
        candidates = [
            self.project_path / ".github" / "workflows",
            self.project_path / ".gitlab-ci.yml",
            self.project_path / "Jenkinsfile",
            self.project_path / ".circleci",
            self.project_path / ".travis.yml",
            self.project_path / "tox.ini",
            self.project_path / "Makefile",
        ]
        found = []
        for c in candidates:
            if c.exists():
                # For directories, check they're non-empty
                if c.is_dir():
                    if any(c.iterdir()):
                        found.append(c)
                else:
                    found.append(c)

        return BoundaryCheck(
            name="ci_config_exists",
            passed=len(found) > 0,
            applicable=True,
            detail=", ".join(f.name for f in found) if found else "No CI config found",
        )

    def _check_build_config_valid(self) -> BoundaryCheck:
        """Check 12: Build/package config (pyproject.toml / setup.py) is parseable."""
        pp = self.project_path / "pyproject.toml"
        setup_py = self.project_path / "setup.py"
        setup_cfg = self.project_path / "setup.cfg"

        if not (pp.exists() or setup_py.exists() or setup_cfg.exists()):
            return BoundaryCheck(
                name="build_config_valid",
                passed=False,
                applicable=True,
                detail="No pyproject.toml, setup.py, or setup.cfg",
            )

        issues: list[str] = []

        if pp.exists():
            text = _read_text(pp)
            # Basic check: has [project] or [tool.poetry] section
            has_project = bool(re.search(r"^\[project\]", text, re.MULTILINE))
            has_poetry = bool(re.search(r"^\[tool\.poetry\]", text, re.MULTILINE))
            has_build = bool(re.search(r"^\[build-system\]", text, re.MULTILINE))
            if not (has_project or has_poetry):
                issues.append("pyproject.toml missing [project] or [tool.poetry]")
            if not has_build:
                issues.append("pyproject.toml missing [build-system]")

        if setup_py.exists():
            text = _read_text(setup_py)
            try:
                ast.parse(text)
            except SyntaxError:
                issues.append("setup.py has syntax errors")

        return BoundaryCheck(
            name="build_config_valid",
            passed=len(issues) == 0,
            applicable=True,
            detail="; ".join(issues) if issues else "OK",
        )

    # -- DRS (aggregate) ----------------------------------------------------

    def calculate_drs(self) -> DRSResult:
        """Calculate Deployment Readiness Score from 12 Python boundary checks."""
        checks = [
            self._check_internal_imports_resolve(),
            self._check_requirements_exist(),
            self._check_deps_match_imports(),
            self._check_env_vars_defined(),
            self._check_no_placeholder_config(),
            self._check_entry_point_exists(),
            self._check_tests_exist(),
            self._check_tests_import_project(),
            self._check_no_circular_imports(),
            self._check_dockerfile_exists(),
            self._check_ci_config_exists(),
            self._check_build_config_valid(),
        ]

        applicable = [c for c in checks if c.applicable]
        passing = [c for c in applicable if c.passed]

        score = len(passing) / len(applicable) if applicable else 0.0

        return DRSResult(
            score=score,
            passing_checks=len(passing),
            total_applicable=len(applicable),
            checks=checks,
        )


# ---------------------------------------------------------------------------
# THI — Template Homogeneity Index (cross-project)
# ---------------------------------------------------------------------------

def _file_tree_fingerprint(project_path: Path) -> set[str]:
    """Return a set of normalised relative paths for the project's file tree.

    Normalisation:
      - Strip the project root prefix
      - Replace likely contract-specific names with a placeholder so that
        ``voting/contracts/Voting.sol`` and ``auction/contracts/Auction.sol``
        hash to the same fingerprint entry.
    """
    skip = {"node_modules", ".git", "__pycache__", "venv", ".next",
            "build", "dist", "artifacts", "cache", "coverage",
            "package-lock.json", "yarn.lock"}
    fps: set[str] = set()
    if not project_path.is_dir():
        return fps

    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn in skip:
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), project_path)
            # Normalise: replace the project-specific contract/component name
            # with a placeholder.  This way two template-stamped projects
            # that differ only in the entity name hash identically.
            normalised = re.sub(
                r"[A-Z][a-z]+(?:[A-Z][a-z]+)*",  # PascalCase names
                "<NAME>",
                rel,
            )
            fps.add(normalised)
    return fps


def compute_thi(projects: list[Path]) -> THIResult:
    """Compute Template Homogeneity Index across a cohort of projects.

    THI = mean pairwise Jaccard similarity of normalised file-tree fingerprints.
    Near 1.0 → template-stamped.  Near 0.0 → structurally diverse.
    """
    if len(projects) < 2:
        return THIResult(thi=0.0, cohort_size=len(projects), pairs_compared=0)

    fingerprints = [_file_tree_fingerprint(p) for p in projects]

    total_jaccard = 0.0
    pairs = 0
    for i, j in combinations(range(len(fingerprints)), 2):
        total_jaccard += _jaccard(fingerprints[i], fingerprints[j])
        pairs += 1

    thi = total_jaccard / pairs if pairs else 0.0

    return THIResult(thi=thi, cohort_size=len(projects), pairs_compared=pairs)

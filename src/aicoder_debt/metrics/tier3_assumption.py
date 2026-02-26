"""Tier 3 Assumption Metrics: URR, HD."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..extractors.dependency import DependencyExtractor
from ..extractors.reference import ReferenceExtractor
from ..models import HallucinatedPackage, HDResult, ImportReference, URRResult

if TYPE_CHECKING:
    from ..registry.npm import NpmRegistry
    from ..registry.pypi import PyPIRegistry


class AssumptionMetrics:
    """Calculate Tier 3 assumption metrics: URR, HD."""

    def __init__(
        self,
        project_path: str | Path,
        skip_registry_check: bool = False,
    ) -> None:
        """Initialize the assumption metrics calculator.

        Args:
            project_path: Path to the project directory.
            skip_registry_check: Skip external registry checks.
        """
        self.project_path = Path(project_path).resolve()
        self.skip_registry_check = skip_registry_check
        self._reference_extractor = ReferenceExtractor(project_path)
        self._dependency_extractor = DependencyExtractor(project_path)
        self._pypi_registry: "PyPIRegistry | None" = None
        self._npm_registry: "NpmRegistry | None" = None

    def calculate_urr(self) -> URRResult:
        """Calculate Undefined Reference Rate (URR).

        URR = unresolved_internal_refs / (total_internal_refs + 1)

        Uses additive smoothing (k=1) so zero references yield 0.0 rather
        than a vacuously perfect score.

        Returns:
            URRResult with rate and details.
        """
        # Extract all references
        references = self._reference_extractor.extract_references()

        # Filter to internal references only
        internal_refs = [r for r in references if r.is_internal]

        # Count unresolved
        unresolved = [r for r in internal_refs if not r.resolved]

        rate = len(unresolved) / (len(internal_refs) + 1)

        return URRResult(
            rate=rate,
            unresolved_refs=len(unresolved),
            total_internal_refs=len(internal_refs),
            unresolved_list=unresolved,
        )

    def calculate_hd(self) -> HDResult:
        """Calculate Hallucination Density (HD).

        HD = hallucinated_packages / KLOC

        Measures how many external packages don't exist in registries.

        Returns:
            HDResult with density and details.
        """
        # Count lines of code
        kloc = self._count_kloc()

        if kloc == 0:
            return HDResult(
                density=0.0,
                hallucinated_count=0,
                total_packages=0,
                kloc=0.0,
                hallucinated_packages=[],
            )

        # Get external packages from dependencies
        dependencies = self._dependency_extractor.extract_dependencies()

        # Also get packages from imports
        references = self._reference_extractor.extract_references()
        external_refs = [r for r in references if not r.is_internal]

        # Build unique package set
        packages: dict[tuple[str, str], ImportReference | None] = {}

        # From dependencies
        for dep in dependencies:
            key = (dep.name, dep.ecosystem)
            if key not in packages:
                packages[key] = None

        # From imports
        for ref in external_refs:
            # Determine ecosystem from file type
            if ref.file_path.endswith((".py", ".pyi")):
                ecosystem = "pypi"
                # Get top-level package name
                package = ref.module.split(".")[0]
            elif ref.file_path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
                ecosystem = "npm"
                # Handle scoped packages
                if ref.module.startswith("@"):
                    parts = ref.module.split("/")
                    package = f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else ref.module
                else:
                    package = ref.module.split("/")[0]
            else:
                continue

            key = (package, ecosystem)
            if key not in packages:
                packages[key] = ref

        if not packages:
            return HDResult(
                density=0.0,
                hallucinated_count=0,
                total_packages=0,
                kloc=kloc,
                hallucinated_packages=[],
            )

        # Check packages against registries
        hallucinated: list[HallucinatedPackage] = []

        if not self.skip_registry_check:
            self._init_registries()

            for (package, ecosystem), ref in packages.items():
                exists = self._check_package_exists(package, ecosystem)

                if not exists:
                    file_path = ref.file_path if ref else "dependency manifest"
                    line_number = ref.line_number if ref else 0

                    hallucinated.append(
                        HallucinatedPackage(
                            file_path=file_path,
                            line_number=line_number,
                            package_name=package,
                            ecosystem=ecosystem,
                            exists=False,
                        )
                    )

        density = len(hallucinated) / kloc if kloc > 0 else 0.0

        return HDResult(
            density=density,
            hallucinated_count=len(hallucinated),
            total_packages=len(packages),
            kloc=kloc,
            hallucinated_packages=hallucinated,
        )

    def _count_kloc(self) -> float:
        """Count lines of code in thousands.

        Returns:
            Total KLOC (thousands of lines of code).
        """
        total_lines = 0

        # Count Python lines
        for py_file in self.project_path.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                # Count non-empty, non-comment lines
                lines = [
                    line
                    for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                total_lines += len(lines)
            except Exception:
                continue

        # Count JavaScript lines
        for pattern in ["*.js", "*.jsx", "*.ts", "*.tsx"]:
            for js_file in self.project_path.rglob(pattern):
                if self._should_skip_file(js_file):
                    continue
                try:
                    content = js_file.read_text(encoding="utf-8", errors="ignore")
                    # Count non-empty, non-comment lines
                    lines = [
                        line
                        for line in content.splitlines()
                        if line.strip()
                        and not line.strip().startswith("//")
                        and not line.strip().startswith("/*")
                        and not line.strip().startswith("*")
                    ]
                    total_lines += len(lines)
                except Exception:
                    continue

        # Count Solidity lines
        for sol_file in self.project_path.rglob("*.sol"):
            if self._should_skip_file(sol_file):
                continue
            try:
                content = sol_file.read_text(encoding="utf-8", errors="ignore")
                lines = [
                    line
                    for line in content.splitlines()
                    if line.strip()
                    and not line.strip().startswith("//")
                    and not line.strip().startswith("/*")
                    and not line.strip().startswith("*")
                ]
                total_lines += len(lines)
            except Exception:
                continue

        return total_lines / 1000.0

    def _should_skip_file(self, path: Path) -> bool:
        """Check if a file should be skipped.

        Args:
            path: Path to check.

        Returns:
            True if the file should be skipped.
        """
        skip_patterns = [
            "__pycache__",
            ".git",
            ".tox",
            ".nox",
            "venv",
            ".venv",
            "node_modules",
            ".eggs",
            "build",
            "dist",
            "vendor",
        ]
        return any(p in path.parts for p in skip_patterns)

    def _init_registries(self) -> None:
        """Initialize registry clients."""
        if self._pypi_registry is None:
            from ..registry.pypi import PyPIRegistry

            self._pypi_registry = PyPIRegistry()

        if self._npm_registry is None:
            from ..registry.npm import NpmRegistry

            self._npm_registry = NpmRegistry()

    def _check_package_exists(self, package: str, ecosystem: str) -> bool:
        """Check if a package exists in the registry.

        Args:
            package: Package name.
            ecosystem: Package ecosystem (pypi, npm, etc.)

        Returns:
            True if the package exists.
        """
        # Skip standard library modules
        if ecosystem == "pypi" and self._is_python_stdlib(package):
            return True

        # Skip Node.js built-in modules
        if ecosystem == "npm" and self._is_node_builtin(package):
            return True

        if ecosystem == "pypi" and self._pypi_registry:
            return self._pypi_registry.package_exists(package)
        elif ecosystem == "npm" and self._npm_registry:
            return self._npm_registry.package_exists(package)

        # Unknown ecosystem - assume exists
        return True

    def _is_python_stdlib(self, module: str) -> bool:
        """Check if a module is part of Python standard library.

        Args:
            module: Module name.

        Returns:
            True if it's a stdlib module.
        """
        # Common stdlib modules
        stdlib = {
            "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
            "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
            "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd",
            "code", "codecs", "codeop", "collections", "colorsys", "compileall",
            "concurrent", "configparser", "contextlib", "contextvars", "copy",
            "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
            "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
            "distutils", "doctest", "email", "encodings", "enum", "errno",
            "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
            "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
            "gettext", "glob", "graphlib", "grp", "gzip", "hashlib", "heapq",
            "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp",
            "importlib", "inspect", "io", "ipaddress", "itertools", "json",
            "keyword", "lib2to3", "linecache", "locale", "logging", "lzma",
            "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
            "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
            "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
            "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
            "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
            "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue",
            "quopri", "random", "re", "readline", "reprlib", "resource",
            "rlcompleter", "runpy", "sched", "secrets", "select", "selectors",
            "shelve", "shlex", "shutil", "signal", "site", "smtpd", "smtplib",
            "sndhdr", "socket", "socketserver", "spwd", "sqlite3", "ssl",
            "stat", "statistics", "string", "stringprep", "struct", "subprocess",
            "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
            "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
            "threading", "time", "timeit", "tkinter", "token", "tokenize",
            "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
            "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
            "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
            "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
            "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
        }
        return module in stdlib

    def _is_node_builtin(self, module: str) -> bool:
        """Check if a module is a Node.js built-in.

        Args:
            module: Module name.

        Returns:
            True if it's a Node built-in.
        """
        # Node.js built-in modules
        builtins = {
            "assert", "async_hooks", "buffer", "child_process", "cluster",
            "console", "constants", "crypto", "dgram", "dns", "domain",
            "events", "fs", "http", "http2", "https", "inspector", "module",
            "net", "os", "path", "perf_hooks", "process", "punycode",
            "querystring", "readline", "repl", "stream", "string_decoder",
            "sys", "timers", "tls", "trace_events", "tty", "url", "util",
            "v8", "vm", "wasi", "worker_threads", "zlib",
            # Also handle node: prefix
            "node:assert", "node:buffer", "node:child_process", "node:cluster",
            "node:console", "node:crypto", "node:dgram", "node:dns",
            "node:events", "node:fs", "node:http", "node:http2", "node:https",
            "node:inspector", "node:module", "node:net", "node:os", "node:path",
            "node:perf_hooks", "node:process", "node:querystring", "node:readline",
            "node:repl", "node:stream", "node:string_decoder", "node:timers",
            "node:tls", "node:tty", "node:url", "node:util", "node:v8",
            "node:vm", "node:wasi", "node:worker_threads", "node:zlib",
        }
        return module in builtins

"""Tier 4 Maintainability Metrics: CSD, CCX."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ..models import CCXResult, CodeSmell, CSDResult, FunctionComplexity


class MaintainabilityMetrics:
    """Calculate Tier 4 maintainability metrics: CSD, CCX."""

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the maintainability metrics calculator.

        Args:
            project_path: Path to the project directory.
        """
        self.project_path = Path(project_path).resolve()

    def calculate_csd(self) -> CSDResult:
        """Calculate Code Smell Density (CSD).

        CSD = lint_issues / KLOC

        Uses pylint for Python, ESLint for JavaScript/TypeScript, and Solhint for Solidity.

        Returns:
            CSDResult with density and details.
        """
        kloc = self._count_kloc()

        if kloc == 0:
            return CSDResult(
                density=0.0,
                total_issues=0,
                kloc=0.0,
                issues=[],
                by_severity={},
            )

        # Combine issues from pylint, eslint, and solhint
        issues = []
        issues.extend(self._run_pylint())
        issues.extend(self._run_eslint())
        issues.extend(self._run_solhint())

        # Group by severity
        by_severity: dict[str, int] = {}
        for issue in issues:
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1

        density = len(issues) / kloc if kloc > 0 else 0.0

        # Flag when linting tools returned 0 issues on non-trivial code
        # (likely means tools failed silently / weren't available)
        analysis_failed = len(issues) == 0 and kloc > 0.1

        return CSDResult(
            density=density,
            total_issues=len(issues),
            kloc=kloc,
            issues=issues,
            by_severity=by_severity,
            analysis_failed=analysis_failed,
        )

    def calculate_ccx(self) -> CCXResult:
        """Calculate Cognitive Complexity Index (CCX).

        Uses radon for Python and tree-sitter for JS/TS cognitive complexity.

        Returns:
            CCXResult with average complexity and details.
        """
        # Combine complexity from Python (radon) and JS/TS (tree-sitter)
        functions = []
        functions.extend(self._calculate_complexity())
        functions.extend(self._calculate_js_complexity())

        if not functions:
            # Check if there is actual code — if so, tools failed silently
            kloc = self._count_kloc()
            return CCXResult(
                average=0.0,
                max_complexity=0,
                total_functions=0,
                high_complexity_count=0,
                functions=[],
                analysis_failed=kloc > 0.1,
            )

        total_complexity = sum(f.complexity for f in functions)
        max_complexity = max(f.complexity for f in functions)
        high_complexity = sum(1 for f in functions if f.complexity > 10)
        average = total_complexity / len(functions) if functions else 0.0

        return CCXResult(
            average=average,
            max_complexity=max_complexity,
            total_functions=len(functions),
            high_complexity_count=high_complexity,
            functions=functions,
        )

    def _run_pylint(self) -> list[CodeSmell]:
        """Run pylint and extract issues.

        Returns:
            List of CodeSmell objects.
        """
        issues: list[CodeSmell] = []

        # Find Python files
        py_files = [
            str(f) for f in self.project_path.rglob("*.py")
            if not self._should_skip_file(f)
        ]

        if not py_files:
            return issues

        try:
            # Run pylint with JSON output
            result = subprocess.run(
                [
                    "pylint",
                    "--output-format=json",
                    "--disable=all",
                    "--enable=C,R,W",  # Conventions, Refactoring, Warnings
                    *py_files,
                ],
                capture_output=True,
                timeout=120,
                text=True,
            )

            # Parse JSON output
            import json
            try:
                pylint_output = json.loads(result.stdout)
                for item in pylint_output:
                    # Map pylint type to severity
                    severity_map = {
                        "convention": "low",
                        "refactor": "medium",
                        "warning": "high",
                        "error": "critical",
                        "fatal": "critical",
                    }
                    severity = severity_map.get(item.get("type", ""), "medium")

                    # Ensure code is not None
                    code = item.get("message-id")
                    if code is None:
                        code = ""

                    issues.append(
                        CodeSmell(
                            file_path=item.get("path", ""),
                            line_number=item.get("line", 0),
                            code=str(code),
                            message=item.get("message", ""),
                            severity=severity,
                        )
                    )
            except json.JSONDecodeError:
                # Fallback to basic parsing
                pass

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # pylint not available - use basic checks
            issues = self._basic_smell_detection()

        return issues

    def _run_eslint(self) -> list[CodeSmell]:
        """Run eslint and extract issues.

        Returns:
            List of CodeSmell objects.
        """
        issues: list[CodeSmell] = []

        # Find JS/TS files
        js_ts_files = []
        for pattern in ("*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs"):
            for file in self.project_path.rglob(pattern):
                if not self._should_skip_file(file):
                    # Skip minified files
                    if not file.name.endswith((".min.js", ".bundle.js")):
                        js_ts_files.append(str(file))

        if not js_ts_files:
            return issues

        try:
            # Find eslint config
            config_path = Path(__file__).parent.parent.parent.parent / "configs" / "linter_configs" / "eslint_config.json"
            if not config_path.exists():
                config_path = self.project_path / ".eslintrc.json"

            # ESLint location with npm-global
            eslint_path = Path.home() / ".npm-global" / "bin" / "eslint"
            if not eslint_path.exists():
                # Try system eslint
                eslint_path = "eslint"

            # Prepare environment with npm-global bin in PATH
            env = {
                "PATH": f"{Path.home()}/.npm-global/bin:{Path('/usr/local/bin')}:/usr/bin:/bin"
            }

            # Run eslint with JSON output
            result = subprocess.run(
                [
                    str(eslint_path),
                    "--format=json",
                    "--no-eslintrc",
                    f"--config={str(config_path)}",
                    *js_ts_files,
                ],
                capture_output=True,
                timeout=120,
                text=True,
                env=env,
            )

            # Parse JSON output
            try:
                eslint_output = json.loads(result.stdout)
                for file_result in eslint_output:
                    file_path = file_result.get("filePath", "")
                    rel_path = str(Path(file_path).relative_to(self.project_path)) if file_path else ""

                    for msg in file_result.get("messages", []):
                        # Map ESLint severity: 1=warning, 2=error
                        severity_map = {
                            1: "medium",
                            2: "high",
                        }
                        severity = severity_map.get(msg.get("severity", 1), "medium")

                        # Ensure code is not None
                        code = msg.get("ruleId")
                        if code is None:
                            code = ""

                        issues.append(
                            CodeSmell(
                                file_path=rel_path,
                                line_number=msg.get("line", 0),
                                code=str(code),
                                message=msg.get("message", ""),
                                severity=severity,
                            )
                        )
            except json.JSONDecodeError:
                pass

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # ESLint not available
            pass

        return issues

    def _run_solhint(self) -> list[CodeSmell]:
        """Run solhint and extract issues from Solidity files.

        Returns:
            List of CodeSmell objects.
        """
        issues: list[CodeSmell] = []

        # Find Solidity files
        sol_files = [
            str(f) for f in self.project_path.rglob("*.sol")
            if not self._should_skip_file(f)
        ]

        if not sol_files:
            return issues

        try:
            # Find solhint executable
            solhint_path = None
            possible_paths = [
                Path.home() / ".npm-global" / "bin" / "solhint",
                Path("/usr/local/bin/solhint"),
                Path("/opt/homebrew/bin/solhint"),
            ]
            for path in possible_paths:
                if path.exists():
                    solhint_path = str(path)
                    break

            if not solhint_path:
                # Try to find in PATH
                try:
                    result = subprocess.run(
                        ["which", "solhint"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        solhint_path = result.stdout.strip()
                except Exception:
                    pass

            if not solhint_path:
                # solhint not available
                return issues

            # Find solhint config
            config_path = Path(__file__).parent.parent.parent.parent / "configs" / "linter_configs" / "solhint_config.json"
            if not config_path.exists():
                config_path = self.project_path / ".solhint.json"

            # Run solhint with JSON output
            cmd = [solhint_path, "--formatter", "json"]
            if config_path.exists():
                cmd.extend(["-c", str(config_path)])
            cmd.extend(sol_files)

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,
                text=True,
            )

            # Parse JSON output (filter out non-JSON messages)
            output = ""
            all_output = result.stdout + "\n" + result.stderr
            for line in all_output.split("\n"):
                if line.startswith("["):
                    output = line
                    break

            if not output:
                return issues

            try:
                solhint_output = json.loads(output)
                for item in solhint_output:
                    # Skip conclusion object
                    if "conclusion" in item:
                        continue

                    if not isinstance(item, dict):
                        continue

                    file_path = item.get("filePath", "")
                    if not file_path:
                        continue

                    # Make path relative if possible
                    try:
                        rel_path = str(Path(file_path).relative_to(self.project_path))
                    except ValueError:
                        rel_path = file_path

                    # Map solhint severity: Warning -> medium, Error -> high
                    severity_raw = item.get("severity", "Warning")
                    severity_map = {
                        "warning": "medium",
                        "error": "high",
                        "Warning": "medium",
                        "Error": "high",
                    }
                    severity = severity_map.get(severity_raw, "medium")

                    # Ensure code is not None
                    code = item.get("ruleId")
                    if code is None:
                        code = "unknown"

                    issues.append(
                        CodeSmell(
                            file_path=rel_path,
                            line_number=item.get("line", 0),
                            code=str(code),
                            message=item.get("message", ""),
                            severity=severity,
                        )
                    )
            except json.JSONDecodeError:
                pass

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # solhint not available
            pass

        return issues

    def _basic_smell_detection(self) -> list[CodeSmell]:
        """Basic code smell detection without external tools.

        Returns:
            List of CodeSmell objects.
        """
        issues: list[CodeSmell] = []

        for py_file in self.project_path.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                rel_path = str(py_file.relative_to(self.project_path))

                # Check for long lines
                for line_num, line in enumerate(content.splitlines(), 1):
                    if len(line) > 120:
                        issues.append(
                            CodeSmell(
                                file_path=rel_path,
                                line_number=line_num,
                                code="C0301",
                                message=f"Line too long ({len(line)}/120)",
                                severity="low",
                            )
                        )

                # Check for missing docstrings
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not ast.get_docstring(node):
                                # Only flag public functions
                                if not node.name.startswith("_"):
                                    issues.append(
                                        CodeSmell(
                                            file_path=rel_path,
                                            line_number=node.lineno,
                                            code="C0116",
                                            message=f"Missing docstring in function '{node.name}'",
                                            severity="low",
                                        )
                                    )
                        elif isinstance(node, ast.ClassDef):
                            if not ast.get_docstring(node):
                                issues.append(
                                    CodeSmell(
                                        file_path=rel_path,
                                        line_number=node.lineno,
                                        code="C0115",
                                        message=f"Missing docstring in class '{node.name}'",
                                        severity="low",
                                    )
                                )
                except SyntaxError:
                    pass

                # Check for TODO comments
                for line_num, line in enumerate(content.splitlines(), 1):
                    if re.search(r"#\s*(TODO|FIXME|XXX|HACK)", line, re.IGNORECASE):
                        issues.append(
                            CodeSmell(
                                file_path=rel_path,
                                line_number=line_num,
                                code="W0511",
                                message="Found TODO/FIXME comment",
                                severity="low",
                            )
                        )

            except Exception:
                continue

        return issues

    def _calculate_complexity(self) -> list[FunctionComplexity]:
        """Calculate cognitive complexity for all functions.

        Returns:
            List of FunctionComplexity objects.
        """
        functions: list[FunctionComplexity] = []

        # Try radon first
        try:
            result = subprocess.run(
                [
                    "radon",
                    "cc",
                    str(self.project_path),
                    "-s",
                    "-j",  # JSON output
                ],
                capture_output=True,
                timeout=120,
                text=True,
            )

            import json
            try:
                radon_output = json.loads(result.stdout)
                for file_path, file_functions in radon_output.items():
                    # Skip error entries (dict with "error" key)
                    if isinstance(file_functions, dict) and "error" in file_functions:
                        continue
                    if not isinstance(file_functions, list):
                        continue

                    rel_path = str(Path(file_path).relative_to(self.project_path))
                    for func in file_functions:
                        if not isinstance(func, dict):
                            continue
                        functions.append(
                            FunctionComplexity(
                                file_path=rel_path,
                                function_name=func.get("name", ""),
                                line_number=func.get("lineno", 0),
                                complexity=func.get("complexity", 0),
                            )
                        )
            except json.JSONDecodeError:
                pass

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # radon not available - use basic complexity calculation
            functions = self._basic_complexity_calculation()

        return functions

    def _calculate_js_complexity(self) -> list[FunctionComplexity]:
        """Calculate cognitive complexity for JS/TS files.

        Uses tree-sitter-based complexity analyzer from tools/extractors/js_complexity.py

        Returns:
            List of FunctionComplexity objects.
        """
        functions: list[FunctionComplexity] = []

        try:
            # Try to import the JS complexity analyzer
            import sys

            # Find the project root by looking for "aicoder-debt" directory
            parts = self.project_path.parts
            root = None
            try:
                idx = parts.index("aicoder-debt")
                root = Path(*parts[:idx+1])
            except ValueError:
                # Fallback 1: walk up from project path to find tools directory
                root = self.project_path
                while root != root.parent:
                    if (root / "tools").exists():
                        break
                    root = root.parent

                # Fallback 2: use __file__ location to find the package root
                if not (root / "tools").exists():
                    this_file = Path(__file__).resolve()
                    # From src/aicoder_debt/metrics/tier4_maintainability.py, go up 4 levels
                    root = this_file.parent.parent.parent.parent
                    if not (root / "tools").exists():
                        # Try one more level up
                        root = root.parent

            tools_path = root / "tools" / "extractors"
            if not tools_path.exists():
                return functions

            # Add to sys.path if not already there
            tools_path_str = str(tools_path)
            if tools_path_str not in sys.path:
                sys.path.insert(0, tools_path_str)

            # Import the module
            from js_complexity import extract_js_complexity

        except (ImportError, ModuleNotFoundError, AttributeError, FileNotFoundError, ValueError, Exception):
            # If import fails, return empty list
            return functions

        # Find JS/TS files
        for pattern in ("*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs"):
            for js_file in self.project_path.rglob(pattern):
                if self._should_skip_file(js_file):
                    continue
                if js_file.name.endswith((".min.js", ".bundle.js")):
                    continue

                try:
                    # Extract complexity from this file
                    js_funcs, _, _ = extract_js_complexity(str(js_file))

                    # Convert to FunctionComplexity format
                    rel_path = str(js_file.relative_to(self.project_path))
                    for func in js_funcs:
                        functions.append(
                            FunctionComplexity(
                                file_path=rel_path,
                                function_name=func.function_name,
                                line_number=func.line,
                                complexity=func.complexity,
                            )
                        )
                except Exception:
                    # Skip files that fail to parse
                    continue

        return functions

    def _basic_complexity_calculation(self) -> list[FunctionComplexity]:
        """Basic complexity calculation without radon.

        Uses cyclomatic complexity approximation based on control flow.

        Returns:
            List of FunctionComplexity objects.
        """
        functions: list[FunctionComplexity] = []

        for py_file in self.project_path.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                rel_path = str(py_file.relative_to(self.project_path))

                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        complexity = self._calculate_node_complexity(node)
                        functions.append(
                            FunctionComplexity(
                                file_path=rel_path,
                                function_name=node.name,
                                line_number=node.lineno,
                                complexity=complexity,
                            )
                        )

            except (SyntaxError, Exception):
                continue

        return functions

    def _calculate_node_complexity(self, node: ast.AST) -> int:
        """Calculate complexity for an AST node.

        This is an approximation of cyclomatic complexity.

        Args:
            node: AST node to analyze.

        Returns:
            Complexity score.
        """
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            # Increment for decision points
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                # Count boolean operators (and, or)
                complexity += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
                if child.ifs:
                    complexity += len(child.ifs)
            elif isinstance(child, (ast.Assert, ast.Raise)):
                complexity += 1
            elif isinstance(child, ast.Match):  # Python 3.10+
                complexity += 1
            elif isinstance(child, ast.match_case):  # Python 3.10+
                complexity += 1

        return complexity

    def _count_kloc(self) -> float:
        """Count lines of code in thousands.

        Counts Python (.py), JavaScript/TypeScript (.js, .jsx, .ts, .tsx), and Solidity (.sol) files.

        Returns:
            Total KLOC.
        """
        total_lines = 0

        # Count Python files
        for py_file in self.project_path.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                lines = [
                    line
                    for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                total_lines += len(lines)
            except Exception:
                continue

        # Count JS/TS files
        for pattern in ("*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs"):
            for js_file in self.project_path.rglob(pattern):
                if self._should_skip_file(js_file):
                    continue
                if js_file.name.endswith((".min.js", ".bundle.js")):
                    continue
                try:
                    content = js_file.read_text(encoding="utf-8", errors="ignore")
                    # Exclude single-line comments and blank lines
                    lines = [
                        line
                        for line in content.splitlines()
                        if line.strip() and not line.strip().startswith("//")
                    ]
                    total_lines += len(lines)
                except Exception:
                    continue

        # Count Solidity files
        for sol_file in self.project_path.rglob("*.sol"):
            if self._should_skip_file(sol_file):
                continue
            try:
                content = sol_file.read_text(encoding="utf-8", errors="ignore")
                # Exclude single-line comments and blank lines
                lines = [
                    line
                    for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("//")
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
            "migrations",
            "test",
            "tests",
        ]
        return any(p in path.parts for p in skip_patterns)

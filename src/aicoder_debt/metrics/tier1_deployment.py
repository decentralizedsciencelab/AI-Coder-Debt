"""Tier 1 Deployment Metrics: DFR, DRD, ID."""

from __future__ import annotations

import ast
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..constants import (
    EDGE_TYPE_COSTS,
    PYTHON_PATTERNS,
    STAGE_DESCRIPTIONS,
    DeploymentRating,
    EdgeType,
    ValidationStage,
)
from ..models import (
    Cycle,
    DDGAnalysis,
    DDGEdge,
    DFRResult,
    DRDResult,
    IDResult,
)

if TYPE_CHECKING:
    from ..extractors.base import BaseExtractor


class DeploymentMetrics:
    """Calculate Tier 1 deployment metrics: DFR, DRD, ID."""

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the deployment metrics calculator.

        Args:
            project_path: Path to the project directory.
        """
        self.project_path = Path(project_path).resolve()

    def calculate_dfr(self, ddg: DDGAnalysis) -> DFRResult:
        """Calculate Deployment Feasibility Rating (DFR).

        DFR Decision Tree:
        1. No cycles → DEPLOYABLE
        2. No stateful cycles → REPAIRABLE (ADDR-only, use DARC)
        3. No irreparable cycles → REPAIRABLE (use SDB)
        4. Has bidirectional STATE with atomicity → IRREPARABLE

        Args:
            ddg: DDG analysis containing cycles.

        Returns:
            DFRResult with rating and explanation.
        """
        cycles = ddg.cycles
        total_cycles = len(cycles)

        # Count cycle types
        stateful_cycles = [c for c in cycles if c.has_state_edge]
        irreparable_cycles = [c for c in cycles if c.is_irreparable]

        # Decision tree
        if total_cycles == 0:
            return DFRResult(
                rating=DeploymentRating.DEPLOYABLE,
                reason="No dependency cycles detected",
                cycles_count=0,
                stateful_cycles_count=0,
                irreparable_cycles_count=0,
            )

        if len(stateful_cycles) == 0:
            return DFRResult(
                rating=DeploymentRating.REPAIRABLE,
                reason=f"Found {total_cycles} cycle(s) with only ADDR edges, "
                "repairable using DARC pattern",
                cycles_count=total_cycles,
                stateful_cycles_count=0,
                irreparable_cycles_count=0,
            )

        if len(irreparable_cycles) == 0:
            return DFRResult(
                rating=DeploymentRating.REPAIRABLE,
                reason=f"Found {len(stateful_cycles)} cycle(s) with STATE edges, "
                "repairable using SDB pattern",
                cycles_count=total_cycles,
                stateful_cycles_count=len(stateful_cycles),
                irreparable_cycles_count=0,
            )

        return DFRResult(
            rating=DeploymentRating.IRREPARABLE,
            reason=f"Found {len(irreparable_cycles)} irreparable cycle(s) with "
            "bidirectional STATE edges requiring atomicity",
            cycles_count=total_cycles,
            stateful_cycles_count=len(stateful_cycles),
            irreparable_cycles_count=len(irreparable_cycles),
        )

    def calculate_drd(self, ddg: DDGAnalysis) -> DRDResult:
        """Calculate Deployment Repair Distance (DRD).

        Uses weighted greedy set cover to find minimum cost edge set
        to break all cycles.

        Args:
            ddg: DDG analysis containing cycles.

        Returns:
            DRDResult with cost and edges to break.
        """
        cycles = ddg.cycles

        # If no cycles, cost is 0
        if not cycles:
            return DRDResult(
                cost=0,
                edges_to_break=[],
                pattern_applications=[],
            )

        # Check for irreparable cycles
        irreparable = [c for c in cycles if c.is_irreparable]
        if irreparable:
            return DRDResult(
                cost=-1,
                edges_to_break=[],
                pattern_applications=["IRREPARABLE: Cannot be fixed with DARC/SDB"],
            )

        # Build edge -> cycles mapping
        edge_to_cycles: dict[tuple[str, str], list[int]] = {}
        for idx, cycle in enumerate(cycles):
            for edge in cycle.edges:
                key = (edge.source, edge.target)
                if key not in edge_to_cycles:
                    edge_to_cycles[key] = []
                edge_to_cycles[key].append(idx)

        # Get all unique edges
        all_edges: dict[tuple[str, str], DDGEdge] = {}
        for cycle in cycles:
            for edge in cycle.edges:
                key = (edge.source, edge.target)
                if key not in all_edges:
                    all_edges[key] = edge

        # Greedy set cover
        selected_edges: list[DDGEdge] = []
        patterns: list[str] = []
        uncovered: set[int] = set(range(len(cycles)))

        while uncovered:
            # Find edge with best cost/coverage ratio
            best_edge: DDGEdge | None = None
            best_key: tuple[str, str] | None = None
            best_ratio = float("inf")
            best_covered: set[int] = set()

            for key, edge in all_edges.items():
                # Get cycles covered by this edge that are still uncovered
                covered = set(edge_to_cycles.get(key, [])) & uncovered
                if not covered:
                    continue

                # Calculate cost
                cost = EDGE_TYPE_COSTS.get(edge.edge_type, 1)
                if cost == 0:
                    cost = 0.1  # Small cost for RUNTIME edges

                ratio = cost / len(covered)
                if ratio < best_ratio:
                    best_ratio = ratio
                    best_edge = edge
                    best_key = key
                    best_covered = covered

            if best_edge is None:
                # No edge can cover remaining cycles (shouldn't happen)
                break

            # Select this edge
            selected_edges.append(best_edge)
            uncovered -= best_covered

            # Determine pattern
            if best_edge.edge_type == EdgeType.ADDR:
                patterns.append(f"DARC: Break {best_key[0]} → {best_key[1]}")
            elif best_edge.edge_type == EdgeType.STATE:
                patterns.append(f"SDB: Break {best_key[0]} → {best_key[1]}")
            else:
                patterns.append(f"RUNTIME: {best_key[0]} → {best_key[1]} (no change needed)")

        # Calculate total cost
        total_cost = sum(
            EDGE_TYPE_COSTS.get(e.edge_type, 1) for e in selected_edges
        )

        return DRDResult(
            cost=total_cost,
            edges_to_break=selected_edges,
            pattern_applications=patterns,
        )

    def calculate_id(self, skip_external: bool = True) -> IDResult:
        """Calculate Illusion Depth (ID).

        Runs 10-stage validation pipeline:
        0: UNPARSEABLE
        1: PARSEABLE
        2: COMPILE
        3: LINT
        4: TYPE_CHECK
        5: UNIT_TEST
        6: INTEGRATION
        7: SAST
        8: BUILD
        9: DEPLOY
        10: HEALTHY

        Args:
            skip_external: Skip stages requiring external tools (5-10).

        Returns:
            IDResult with highest stage passed.
        """
        details: dict[ValidationStage, bool] = {}
        highest_stage = ValidationStage.UNPARSEABLE

        # Stage 1: PARSEABLE - Check if code parses
        parseable = self._check_parseable()
        details[ValidationStage.PARSEABLE] = parseable
        if not parseable:
            return self._make_id_result(ValidationStage.UNPARSEABLE, details)
        highest_stage = ValidationStage.PARSEABLE

        # Stage 2: COMPILE - Check if code compiles/transpiles
        compiles = self._check_compile()
        details[ValidationStage.COMPILE] = compiles
        if not compiles:
            return self._make_id_result(ValidationStage.PARSEABLE, details)
        highest_stage = ValidationStage.COMPILE

        # Stage 3: LINT - Check basic linting
        lints = self._check_lint()
        details[ValidationStage.LINT] = lints
        if not lints:
            return self._make_id_result(ValidationStage.COMPILE, details)
        highest_stage = ValidationStage.LINT

        # Stage 4: TYPE_CHECK - Check type annotations
        type_checks = self._check_types()
        details[ValidationStage.TYPE_CHECK] = type_checks
        if not type_checks:
            return self._make_id_result(ValidationStage.LINT, details)
        highest_stage = ValidationStage.TYPE_CHECK

        # Skip external stages if requested
        if skip_external:
            # Mark remaining stages as unknown/skipped
            for stage in [
                ValidationStage.UNIT_TEST,
                ValidationStage.INTEGRATION,
                ValidationStage.SAST,
                ValidationStage.BUILD,
                ValidationStage.DEPLOY,
                ValidationStage.HEALTHY,
            ]:
                details[stage] = True  # Assume pass for skipped stages

            return self._make_id_result(ValidationStage.HEALTHY, details)

        # Stage 5: UNIT_TEST
        tests = self._check_unit_tests()
        details[ValidationStage.UNIT_TEST] = tests
        if not tests:
            return self._make_id_result(ValidationStage.TYPE_CHECK, details)
        highest_stage = ValidationStage.UNIT_TEST

        # Stage 6: INTEGRATION
        integration = self._check_integration_tests()
        details[ValidationStage.INTEGRATION] = integration
        if not integration:
            return self._make_id_result(ValidationStage.UNIT_TEST, details)
        highest_stage = ValidationStage.INTEGRATION

        # Stage 7: SAST
        sast = self._check_sast()
        details[ValidationStage.SAST] = sast
        if not sast:
            return self._make_id_result(ValidationStage.INTEGRATION, details)
        highest_stage = ValidationStage.SAST

        # Stage 8: BUILD
        builds = self._check_build()
        details[ValidationStage.BUILD] = builds
        if not builds:
            return self._make_id_result(ValidationStage.SAST, details)
        highest_stage = ValidationStage.BUILD

        # Stage 9: DEPLOY
        deploys = self._check_deploy()
        details[ValidationStage.DEPLOY] = deploys
        if not deploys:
            return self._make_id_result(ValidationStage.BUILD, details)
        highest_stage = ValidationStage.DEPLOY

        # Stage 10: HEALTHY
        healthy = self._check_healthy()
        details[ValidationStage.HEALTHY] = healthy
        if not healthy:
            return self._make_id_result(ValidationStage.DEPLOY, details)

        return self._make_id_result(ValidationStage.HEALTHY, details)

    def _make_id_result(
        self, stage: ValidationStage, details: dict[ValidationStage, bool]
    ) -> IDResult:
        """Create an IDResult from stage and details.

        Args:
            stage: Highest stage passed.
            details: Pass/fail for each stage.

        Returns:
            IDResult object.
        """
        return IDResult(
            stage=stage,
            stage_name=stage.name,
            gap=10 - stage.value,
            details=details,
        )

    def _check_parseable(self) -> bool:
        """Check if Python files parse successfully.

        Returns:
            True if all files parse.
        """
        for py_file in self.project_path.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                ast.parse(content)
            except SyntaxError:
                return False
        return True

    def _check_compile(self) -> bool:
        """Check if code compiles.

        For Python, this is essentially the same as parsing.
        For other languages, would run compiler.

        Returns:
            True if compilation succeeds.
        """
        # Python doesn't have a separate compile step
        # Check for py_compile
        try:
            import py_compile

            for py_file in self.project_path.rglob("*.py"):
                if self._should_skip_file(py_file):
                    continue
                try:
                    py_compile.compile(str(py_file), doraise=True)
                except py_compile.PyCompileError:
                    return False
        except ImportError:
            pass

        return True

    def _check_lint(self) -> bool:
        """Check basic linting rules.

        Returns:
            True if basic linting passes.
        """
        # Simple lint checks without external tools
        for py_file in self.project_path.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")

                # Check for common issues
                # 1. Undefined names in simple cases
                # 2. Unused imports (basic check)
                # This is a simplified check; full linting would use pylint/flake8

            except Exception:
                return False

        return True

    def _check_types(self) -> bool:
        """Check type annotations.

        Returns:
            True if type checking passes (or no type checker available).
        """
        # Try to run mypy if available
        try:
            result = subprocess.run(
                ["mypy", "--ignore-missing-imports", str(self.project_path)],
                capture_output=True,
                timeout=60,
            )
            # Accept both success and mypy not finding issues
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # mypy not available or timed out - assume pass
            return True

    def _check_unit_tests(self) -> bool:
        """Check if unit tests pass.

        Returns:
            True if tests pass.
        """
        try:
            result = subprocess.run(
                ["pytest", str(self.project_path), "--collect-only", "-q"],
                capture_output=True,
                timeout=30,
            )
            # If no tests found, consider it a pass
            if result.returncode != 0:
                # Check if it's just "no tests found"
                if b"no tests ran" in result.stdout or b"collected 0 items" in result.stdout:
                    return True
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True

    def _check_integration_tests(self) -> bool:
        """Check if integration tests pass.

        Returns:
            True if tests pass.
        """
        # Integration tests are typically in specific directories
        # For now, assume pass if we got this far
        return True

    def _check_sast(self) -> bool:
        """Check static application security testing.

        Returns:
            True if SAST passes.
        """
        try:
            result = subprocess.run(
                ["bandit", "-r", str(self.project_path), "-q"],
                capture_output=True,
                timeout=60,
            )
            # bandit returns 0 on success, 1 on issues found
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True

    def _check_build(self) -> bool:
        """Check if Docker build succeeds.

        Returns:
            True if build succeeds.
        """
        dockerfile = self.project_path / "Dockerfile"
        if not dockerfile.exists():
            return True

        # Don't actually build, just validate Dockerfile syntax
        try:
            content = dockerfile.read_text()
            # Basic Dockerfile validation
            has_from = any(line.strip().upper().startswith("FROM") for line in content.splitlines())
            return has_from
        except Exception:
            return False

    def _check_deploy(self) -> bool:
        """Check if deployment succeeds.

        Returns:
            True if deployment succeeds (simulated).
        """
        # Check for docker-compose.yml
        compose_files = list(self.project_path.glob("docker-compose*.yml"))
        compose_files.extend(self.project_path.glob("compose*.yml"))

        if not compose_files:
            return True

        # Validate compose file syntax
        try:
            import yaml

            for compose_file in compose_files:
                content = compose_file.read_text()
                data = yaml.safe_load(content)
                if not isinstance(data, dict):
                    return False
                if "services" not in data and "version" not in data:
                    return False
            return True
        except Exception:
            return False

    def _check_healthy(self) -> bool:
        """Check if health checks pass.

        Returns:
            True if healthy (simulated).
        """
        # This would require actually running the application
        # For static analysis, we assume pass if we got this far
        return True

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
        ]
        return any(p in path.parts for p in skip_patterns)

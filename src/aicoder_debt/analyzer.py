"""Main orchestrator for AI Coder Debt analysis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .extractors.ddg import DDGExtractor
from .metrics.tier1_deployment import DeploymentMetrics
from .metrics.tier2_integration import IntegrationMetrics
from .metrics.tier3_assumption import AssumptionMetrics
from .metrics.tier4_maintainability import MaintainabilityMetrics
from .metrics.tier5_boundary import BoundaryMetrics, PythonBoundaryMetrics
from .models import (
    AnalysisResult,
    CCSResult,
    CCXResult,
    CSDResult,
    DDGAnalysis,
    DFRResult,
    DRDResult,
    DRSResult,
    HDResult,
    ICRResult,
    IDResult,
    MetricSummary,
    Tier1Results,
    Tier2Results,
    Tier3Results,
    Tier4Results,
    Tier5Results,
    URRResult,
)


class AICoderDebtAnalyzer:
    """Main analyzer class for AI Coder Debt metrics."""

    def __init__(
        self,
        skip_registry_check: bool = False,
        skip_maintainability: bool = False,
    ) -> None:
        """Initialize the analyzer.

        Args:
            skip_registry_check: Skip npm/PyPI package verification.
            skip_maintainability: Skip Tier 4 metrics calculation.
        """
        self.skip_registry_check = skip_registry_check
        self.skip_maintainability = skip_maintainability

    def analyze(self, project_path: str | Path) -> AnalysisResult:
        """Run full analysis on a project.

        Args:
            project_path: Path to the project directory.

        Returns:
            Complete AnalysisResult with all metrics.
        """
        project_path = Path(project_path).resolve()

        if not project_path.exists():
            raise FileNotFoundError(f"Project path does not exist: {project_path}")
        if not project_path.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {project_path}")

        # Extract DDG
        ddg = self.extract_ddg(project_path)

        # Calculate Tier 1 metrics
        tier1 = self.calculate_tier1(project_path, ddg)

        # Calculate Tier 2 metrics
        tier2 = self.calculate_tier2(project_path)

        # Calculate Tier 3 metrics
        tier3 = self.calculate_tier3(project_path)

        # Calculate Tier 4 metrics (optional)
        tier4 = None
        if not self.skip_maintainability:
            tier4 = self.calculate_tier4(project_path)

        # Calculate Tier 5 boundary metrics (DRS)
        tier5 = self.calculate_tier5(project_path)

        return AnalysisResult(
            project_path=str(project_path),
            timestamp=datetime.now().isoformat(),
            ddg=ddg,
            tier1=tier1,
            tier2=tier2,
            tier3=tier3,
            tier4=tier4,
            tier5=tier5,
        )

    def extract_ddg(self, project_path: str | Path) -> DDGAnalysis:
        """Extract Deployment Dependency Graph.

        Args:
            project_path: Path to the project directory.

        Returns:
            DDGAnalysis with nodes, edges, and cycles.
        """
        extractor = DDGExtractor(project_path)
        return extractor.extract()

    def calculate_tier1(
        self, project_path: str | Path, ddg: DDGAnalysis
    ) -> Tier1Results:
        """Calculate Tier 1 deployment metrics.

        Args:
            project_path: Path to the project directory.
            ddg: DDG analysis result.

        Returns:
            Tier1Results with DFR, DRD, and ID.
        """
        metrics = DeploymentMetrics(project_path)

        dfr = metrics.calculate_dfr(ddg)
        drd = metrics.calculate_drd(ddg)
        id_result = metrics.calculate_id(skip_external=True)

        return Tier1Results(dfr=dfr, drd=drd, id=id_result)

    def calculate_tier2(self, project_path: str | Path) -> Tier2Results:
        """Calculate Tier 2 integration metrics.

        Args:
            project_path: Path to the project directory.

        Returns:
            Tier2Results with ICR and CCS.
        """
        metrics = IntegrationMetrics(project_path)

        icr = metrics.calculate_icr()
        ccs = metrics.calculate_ccs()

        return Tier2Results(icr=icr, ccs=ccs)

    def calculate_tier3(self, project_path: str | Path) -> Tier3Results:
        """Calculate Tier 3 assumption metrics.

        Args:
            project_path: Path to the project directory.

        Returns:
            Tier3Results with URR and HD.
        """
        metrics = AssumptionMetrics(
            project_path,
            skip_registry_check=self.skip_registry_check,
        )

        urr = metrics.calculate_urr()
        hd = metrics.calculate_hd()

        return Tier3Results(urr=urr, hd=hd)

    def calculate_tier4(self, project_path: str | Path) -> Tier4Results:
        """Calculate Tier 4 maintainability metrics.

        Args:
            project_path: Path to the project directory.

        Returns:
            Tier4Results with CSD and CCX.
        """
        metrics = MaintainabilityMetrics(project_path)

        csd = metrics.calculate_csd()
        ccx = metrics.calculate_ccx()

        return Tier4Results(csd=csd, ccx=ccx)

    def calculate_tier5(self, project_path: str | Path) -> Tier5Results | None:
        """Calculate Tier 5 boundary metrics (DRS).

        Auto-detects project type and uses the appropriate checker.

        Args:
            project_path: Path to the project directory.

        Returns:
            Tier5Results with DRS, or None if not applicable.
        """
        project_path = Path(project_path).resolve()
        # Detect project type by checking for Solidity or Python files
        has_solidity = any(project_path.rglob("*.sol"))
        has_python = any(project_path.rglob("*.py"))

        try:
            if has_solidity:
                metrics = BoundaryMetrics(project_path)
            elif has_python:
                metrics = PythonBoundaryMetrics(project_path)
            else:
                # JS/TS-only projects — use generic boundary metrics
                metrics = BoundaryMetrics(project_path)
            drs = metrics.calculate_drs()
            return Tier5Results(drs=drs)
        except Exception:
            return None

    @staticmethod
    def compute_acds(result: "AnalysisResult") -> float | None:
        """Compute the AI Coder Debt Score (ACDS) from an AnalysisResult.

        ACDS = 1 - product(1 - Li) for available levels.

        L1 = 1 - DRS
        L2 = mean(1 - ICR, 1 - CCS, URR)
        L3 = mean(CCX/15, CSD/100)

        Returns:
            ACDS in [0, 1], or None if no levels are available.
        """
        def _clamp(v: float) -> float:
            return max(0.0, min(1.0, v))

        levels: list[float] = []

        # L1: from DRS (Tier 5)
        if result.tier5 and result.tier5.drs:
            l1 = _clamp(1.0 - result.tier5.drs.score)
            levels.append(l1)

        # L2: from ICR, CCS, URR (Tier 2 + Tier 3)
        l2_parts: list[float] = []
        l2_parts.append(_clamp(1.0 - result.tier2.icr.rate))
        l2_parts.append(_clamp(1.0 - result.tier2.ccs.score))
        l2_parts.append(_clamp(result.tier3.urr.rate))
        l2 = sum(l2_parts) / len(l2_parts)
        levels.append(l2)

        # L3: from CCX, CSD (Tier 4)
        if result.tier4:
            l3_parts: list[float] = []
            if result.tier4.ccx.average is not None:
                l3_parts.append(_clamp(result.tier4.ccx.average / 15.0))
            if result.tier4.csd.density is not None:
                l3_parts.append(_clamp(result.tier4.csd.density / 100.0))
            if l3_parts:
                l3 = sum(l3_parts) / len(l3_parts)
                levels.append(l3)

        if not levels:
            return None

        health = 1.0
        for lv in levels:
            health *= (1.0 - lv)
        return _clamp(1.0 - health)

    # Individual metric methods for convenience

    def calculate_dfr(self, project_path: str | Path) -> DFRResult:
        """Calculate DFR metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            DFRResult.
        """
        ddg = self.extract_ddg(project_path)
        metrics = DeploymentMetrics(project_path)
        return metrics.calculate_dfr(ddg)

    def calculate_drd(self, project_path: str | Path) -> DRDResult:
        """Calculate DRD metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            DRDResult.
        """
        ddg = self.extract_ddg(project_path)
        metrics = DeploymentMetrics(project_path)
        return metrics.calculate_drd(ddg)

    def calculate_id(self, project_path: str | Path) -> IDResult:
        """Calculate ID metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            IDResult.
        """
        metrics = DeploymentMetrics(project_path)
        return metrics.calculate_id(skip_external=True)

    def calculate_icr(self, project_path: str | Path) -> ICRResult:
        """Calculate ICR metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            ICRResult.
        """
        metrics = IntegrationMetrics(project_path)
        return metrics.calculate_icr()

    def calculate_ccs(self, project_path: str | Path) -> CCSResult:
        """Calculate CCS metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            CCSResult.
        """
        metrics = IntegrationMetrics(project_path)
        return metrics.calculate_ccs()

    def calculate_urr(self, project_path: str | Path) -> URRResult:
        """Calculate URR metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            URRResult.
        """
        metrics = AssumptionMetrics(
            project_path,
            skip_registry_check=self.skip_registry_check,
        )
        return metrics.calculate_urr()

    def calculate_hd(self, project_path: str | Path) -> HDResult:
        """Calculate HD metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            HDResult.
        """
        metrics = AssumptionMetrics(
            project_path,
            skip_registry_check=self.skip_registry_check,
        )
        return metrics.calculate_hd()

    def calculate_csd(self, project_path: str | Path) -> CSDResult:
        """Calculate CSD metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            CSDResult.
        """
        metrics = MaintainabilityMetrics(project_path)
        return metrics.calculate_csd()

    def calculate_ccx(self, project_path: str | Path) -> CCXResult:
        """Calculate CCX metric only.

        Args:
            project_path: Path to the project directory.

        Returns:
            CCXResult.
        """
        metrics = MaintainabilityMetrics(project_path)
        return metrics.calculate_ccx()

    def get_summary(self, result: AnalysisResult) -> MetricSummary:
        """Get a summary of all metrics.

        Args:
            result: Full analysis result.

        Returns:
            MetricSummary with all metrics.
        """
        return MetricSummary(
            dfr=result.tier1.dfr.rating.value,
            drd=result.tier1.drd.cost,
            id_stage=result.tier1.id.stage.value,
            id_gap=result.tier1.id.gap,
            icr=result.tier2.icr.rate,
            ccs=result.tier2.ccs.score,
            urr=result.tier3.urr.rate,
            hd=result.tier3.hd.density,
            csd=result.tier4.csd.density if result.tier4 else None,
            ccx=result.tier4.ccx.average if result.tier4 else None,
            drs=result.tier5.drs.score if result.tier5 else None,
            acds=self.compute_acds(result),
        )

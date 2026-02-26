"""Pydantic data models for AI Coder Debt metrics."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .constants import Confidence, DeploymentRating, EdgeType, ValidationStage


# =============================================================================
# DDG Models
# =============================================================================


class DDGNode(BaseModel):
    """A node in the Deployment Dependency Graph."""

    id: str = Field(..., description="Unique identifier for the node")
    name: str = Field(..., description="Human-readable name")
    type: str = Field(..., description="Node type (contract, service, database, etc.)")
    file_path: str | None = Field(None, description="Source file path")
    line_number: int | None = Field(None, description="Line number in source file")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class DDGEdge(BaseModel):
    """An edge in the Deployment Dependency Graph."""

    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    edge_type: EdgeType = Field(..., description="Type of dependency")
    confidence: Confidence = Field(
        Confidence.HIGH, description="Confidence level of the edge"
    )
    requires_atomicity: bool = Field(
        False, description="Whether the dependency requires atomic initialization"
    )
    description: str | None = Field(None, description="Description of the dependency")
    file_path: str | None = Field(None, description="Source file where edge is defined")
    line_number: int | None = Field(None, description="Line number where edge is found")


class Cycle(BaseModel):
    """A cycle (strongly connected component) in the DDG."""

    nodes: list[str] = Field(..., description="Node IDs in the cycle")
    edges: list[DDGEdge] = Field(..., description="Edges forming the cycle")
    has_state_edge: bool = Field(
        False, description="Whether cycle contains STATE edges"
    )
    is_irreparable: bool = Field(
        False, description="Whether cycle is irreparable"
    )


class DDGAnalysis(BaseModel):
    """Complete DDG analysis output."""

    nodes: list[DDGNode] = Field(default_factory=list, description="All nodes")
    edges: list[DDGEdge] = Field(default_factory=list, description="All edges")
    cycles: list[Cycle] = Field(default_factory=list, description="Detected cycles")
    statistics: DDGStatistics = Field(
        default_factory=lambda: DDGStatistics(),
        description="Summary statistics",
    )


class DDGStatistics(BaseModel):
    """Statistics about the DDG."""

    total_nodes: int = Field(0, description="Total number of nodes")
    total_edges: int = Field(0, description="Total number of edges")
    addr_edges: int = Field(0, description="Number of ADDR edges")
    state_edges: int = Field(0, description="Number of STATE edges")
    runtime_edges: int = Field(0, description="Number of RUNTIME edges")
    total_cycles: int = Field(0, description="Total number of cycles")
    stateful_cycles: int = Field(0, description="Cycles with STATE edges")
    irreparable_cycles: int = Field(0, description="Irreparable cycles")


# =============================================================================
# Tier 1: Deployment Metrics
# =============================================================================


class DFRResult(BaseModel):
    """Deployment Feasibility Rating result."""

    rating: DeploymentRating = Field(..., description="The deployment rating")
    reason: str = Field(..., description="Explanation for the rating")
    cycles_count: int = Field(0, description="Total number of cycles")
    stateful_cycles_count: int = Field(0, description="Number of stateful cycles")
    irreparable_cycles_count: int = Field(0, description="Number of irreparable cycles")


class DRDResult(BaseModel):
    """Deployment Repair Distance result."""

    cost: int = Field(
        ..., description="Total repair cost (-1 if irreparable)"
    )
    edges_to_break: list[DDGEdge] = Field(
        default_factory=list, description="Edges to break for repair"
    )
    pattern_applications: list[str] = Field(
        default_factory=list, description="Repair patterns to apply"
    )


class IDResult(BaseModel):
    """Illusion Depth result."""

    stage: ValidationStage = Field(..., description="Highest validation stage passed")
    stage_name: str = Field(..., description="Name of the stage")
    gap: int = Field(..., description="Gap from deployment (10 - stage)")
    details: dict[ValidationStage, bool] = Field(
        default_factory=dict, description="Pass/fail for each stage"
    )


# =============================================================================
# Tier 2: Integration Metrics
# =============================================================================


class APICall(BaseModel):
    """An API call extracted from code."""

    file_path: str = Field(..., description="Source file path")
    line_number: int = Field(..., description="Line number")
    method: str = Field(..., description="HTTP method or function name")
    endpoint: str = Field(..., description="Target endpoint or URL")
    is_internal: bool = Field(False, description="Whether call is to internal service")


class APIEndpoint(BaseModel):
    """An API endpoint definition."""

    file_path: str = Field(..., description="Source file path")
    line_number: int = Field(..., description="Line number")
    method: str = Field(..., description="HTTP method")
    path: str = Field(..., description="Endpoint path")
    handler: str | None = Field(None, description="Handler function name")


class ICRResult(BaseModel):
    """Interface Consistency Rate result."""

    rate: float = Field(..., ge=0.0, le=1.0, description="Consistency rate")
    matched_calls: int = Field(0, description="Number of matched internal calls")
    total_internal_calls: int = Field(0, description="Total internal API calls")
    unmatched_calls: list[APICall] = Field(
        default_factory=list, description="Unmatched internal calls"
    )
    endpoints: list[APIEndpoint] = Field(
        default_factory=list, description="Defined endpoints"
    )


class ConfigDefinition(BaseModel):
    """A configuration definition."""

    file_path: str = Field(..., description="Config file path")
    key: str = Field(..., description="Configuration key")
    value: str | None = Field(None, description="Configuration value")
    line_number: int | None = Field(None, description="Line number")


class ConfigReference(BaseModel):
    """A configuration reference in code."""

    file_path: str = Field(..., description="Source file path")
    line_number: int = Field(..., description="Line number")
    key: str = Field(..., description="Referenced configuration key")
    resolved: bool = Field(False, description="Whether reference is resolved")


class CCSResult(BaseModel):
    """Configuration Coherence Score result."""

    score: float = Field(..., ge=0.0, le=1.0, description="Coherence score")
    resolved_configs: int = Field(0, description="Number of resolved config references")
    total_config_refs: int = Field(0, description="Total config references")
    unresolved_refs: list[ConfigReference] = Field(
        default_factory=list, description="Unresolved config references"
    )
    definitions: list[ConfigDefinition] = Field(
        default_factory=list, description="Config definitions"
    )


# =============================================================================
# Tier 3: Assumption Metrics
# =============================================================================


class ImportReference(BaseModel):
    """An import reference in code."""

    file_path: str = Field(..., description="Source file path")
    line_number: int = Field(..., description="Line number")
    module: str = Field(..., description="Imported module")
    name: str | None = Field(None, description="Imported name (if specific)")
    is_internal: bool = Field(False, description="Whether import is internal")
    resolved: bool = Field(False, description="Whether import is resolved")


class URRResult(BaseModel):
    """Undefined Reference Rate result."""

    rate: float = Field(..., ge=0.0, le=1.0, description="Undefined reference rate")
    unresolved_refs: int = Field(0, description="Number of unresolved references")
    total_internal_refs: int = Field(0, description="Total internal references")
    unresolved_list: list[ImportReference] = Field(
        default_factory=list, description="List of unresolved references"
    )


class HallucinatedPackage(BaseModel):
    """A potentially hallucinated package reference."""

    file_path: str = Field(..., description="Source file path")
    line_number: int = Field(..., description="Line number")
    package_name: str = Field(..., description="Package name")
    ecosystem: str = Field(..., description="Package ecosystem (pypi, npm, etc.)")
    exists: bool = Field(False, description="Whether package exists in registry")


class HDResult(BaseModel):
    """Hallucination Density result."""

    density: float = Field(..., ge=0.0, description="Hallucinations per KLOC")
    hallucinated_count: int = Field(0, description="Number of hallucinated packages")
    total_packages: int = Field(0, description="Total external packages")
    kloc: float = Field(0.0, description="Total lines of code in thousands")
    hallucinated_packages: list[HallucinatedPackage] = Field(
        default_factory=list, description="List of hallucinated packages"
    )


# =============================================================================
# Tier 4: Maintainability Metrics
# =============================================================================


class CodeSmell(BaseModel):
    """A code smell issue."""

    file_path: str = Field(..., description="Source file path")
    line_number: int = Field(..., description="Line number")
    code: str = Field(..., description="Issue code")
    message: str = Field(..., description="Issue message")
    severity: str = Field(..., description="Issue severity")


class CSDResult(BaseModel):
    """Code Smell Density result."""

    density: float = Field(..., ge=0.0, description="Issues per KLOC")
    total_issues: int = Field(0, description="Total code smell issues")
    kloc: float = Field(0.0, description="Total lines of code in thousands")
    issues: list[CodeSmell] = Field(
        default_factory=list, description="List of code smells"
    )
    by_severity: dict[str, int] = Field(
        default_factory=dict, description="Issues by severity"
    )
    analysis_failed: bool = Field(
        False, description="True when linting tools failed silently (0 issues on non-empty code)"
    )


class FunctionComplexity(BaseModel):
    """Complexity measurement for a function."""

    file_path: str = Field(..., description="Source file path")
    function_name: str = Field(..., description="Function name")
    line_number: int = Field(..., description="Line number")
    complexity: int = Field(..., description="Cognitive complexity score")


class CCXResult(BaseModel):
    """Cognitive Complexity Index result."""

    average: float = Field(..., ge=0.0, description="Average cognitive complexity")
    max_complexity: int = Field(0, description="Maximum complexity")
    total_functions: int = Field(0, description="Total number of functions")
    high_complexity_count: int = Field(
        0, description="Functions with complexity > 10"
    )
    functions: list[FunctionComplexity] = Field(
        default_factory=list, description="Per-function complexity"
    )
    analysis_failed: bool = Field(
        False, description="True when complexity tools failed silently (0 functions on non-empty code)"
    )


# =============================================================================
# Tier 5: Boundary Metrics
# =============================================================================


class BoundaryCheck(BaseModel):
    """A single boundary check result."""

    name: str = Field(..., description="Check name")
    passed: bool = Field(..., description="Whether the check passed")
    applicable: bool = Field(True, description="Whether the check applies to this project")
    detail: str = Field("", description="Human-readable detail")


class DRSResult(BaseModel):
    """Deployment Readiness Score result."""

    score: float = Field(..., ge=0.0, le=1.0, description="DRS = passing / applicable")
    passing_checks: int = Field(0, description="Number of passing checks")
    total_applicable: int = Field(0, description="Number of applicable checks")
    checks: list[BoundaryCheck] = Field(
        default_factory=list, description="Individual check results"
    )


class THIResult(BaseModel):
    """Template Homogeneity Index result."""

    thi: float = Field(
        ..., ge=0.0, le=1.0,
        description="Mean pairwise Jaccard of file-tree fingerprints",
    )
    cohort_size: int = Field(0, description="Number of projects in cohort")
    pairs_compared: int = Field(0, description="Number of pairwise comparisons")


# =============================================================================
# Aggregate Results
# =============================================================================


class Tier1Results(BaseModel):
    """Tier 1 deployment metrics results."""

    dfr: DFRResult
    drd: DRDResult
    id: IDResult


class Tier2Results(BaseModel):
    """Tier 2 integration metrics results."""

    icr: ICRResult
    ccs: CCSResult


class Tier3Results(BaseModel):
    """Tier 3 assumption metrics results."""

    urr: URRResult
    hd: HDResult


class Tier4Results(BaseModel):
    """Tier 4 maintainability metrics results."""

    csd: CSDResult
    ccx: CCXResult


class Tier5Results(BaseModel):
    """Tier 5 boundary metrics results."""

    drs: DRSResult


class AnalysisResult(BaseModel):
    """Complete analysis result."""

    project_path: str = Field(..., description="Analyzed project path")
    timestamp: str = Field(..., description="Analysis timestamp")
    ddg: DDGAnalysis = Field(..., description="Deployment Dependency Graph")
    tier1: Tier1Results = Field(..., description="Tier 1: Deployment metrics")
    tier2: Tier2Results = Field(..., description="Tier 2: Integration metrics")
    tier3: Tier3Results = Field(..., description="Tier 3: Assumption metrics")
    tier4: Tier4Results | None = Field(
        None, description="Tier 4: Maintainability metrics (optional)"
    )
    tier5: Tier5Results | None = Field(
        None, description="Tier 5: Boundary metrics (optional)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class MetricSummary(BaseModel):
    """Summary of all metrics for reporting."""

    # Tier 1
    dfr: str = Field(..., description="Deployment Feasibility Rating")
    drd: int = Field(..., description="Deployment Repair Distance")
    id_stage: int = Field(..., description="Illusion Depth stage")
    id_gap: int = Field(..., description="Illusion Depth gap")

    # Tier 2
    icr: float = Field(..., description="Interface Consistency Rate")
    ccs: float = Field(..., description="Configuration Coherence Score")

    # Tier 3
    urr: float = Field(..., description="Undefined Reference Rate")
    hd: float = Field(..., description="Hallucination Density")

    # Tier 4 (optional)
    csd: float | None = Field(None, description="Code Smell Density")
    ccx: float | None = Field(None, description="Cognitive Complexity Index")

    # Tier 5 (optional)
    drs: float | None = Field(None, description="Deployment Readiness Score")

    # Composite
    acds: float | None = Field(None, description="AI Coder Debt Score (0-1)")

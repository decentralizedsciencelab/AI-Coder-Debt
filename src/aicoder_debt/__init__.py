"""
AI Coder Debt - Metrics for LLM-generated multi-component systems.

This package computes 8 AI Coder Debt metrics across 4 tiers to measure
deployability of LLM-generated code.
"""

from .analyzer import AICoderDebtAnalyzer
from .constants import (
    DARC_COST,
    EDGE_TYPE_COSTS,
    PROXY_COST,
    SDB_COST,
    Confidence,
    DeploymentRating,
    EdgeType,
    ValidationStage,
)
from .models import (
    AnalysisResult,
    CCSResult,
    CCXResult,
    CSDResult,
    Cycle,
    DDGAnalysis,
    DDGEdge,
    DDGNode,
    DDGStatistics,
    DFRResult,
    DRDResult,
    HDResult,
    ICRResult,
    IDResult,
    MetricSummary,
    Tier1Results,
    Tier2Results,
    Tier3Results,
    Tier4Results,
    URRResult,
)

__version__ = "0.1.0"
__all__ = [
    # Main analyzer
    "AICoderDebtAnalyzer",
    # Constants
    "DARC_COST",
    "SDB_COST",
    "PROXY_COST",
    "EDGE_TYPE_COSTS",
    "EdgeType",
    "DeploymentRating",
    "ValidationStage",
    "Confidence",
    # DDG Models
    "DDGNode",
    "DDGEdge",
    "Cycle",
    "DDGAnalysis",
    "DDGStatistics",
    # Tier 1 Results
    "DFRResult",
    "DRDResult",
    "IDResult",
    # Tier 2 Results
    "ICRResult",
    "CCSResult",
    # Tier 3 Results
    "URRResult",
    "HDResult",
    # Tier 4 Results
    "CSDResult",
    "CCXResult",
    # Aggregate Results
    "Tier1Results",
    "Tier2Results",
    "Tier3Results",
    "Tier4Results",
    "AnalysisResult",
    "MetricSummary",
]

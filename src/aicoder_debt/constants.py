"""Constants for AI Coder Debt metrics calculation."""

from enum import Enum, IntEnum
from typing import Final

# =============================================================================
# Repair Pattern Costs
# =============================================================================

# DARC: Defer Address Resolution via Callback
# Used to break ADDR-only dependencies
DARC_COST: Final[int] = 1

# SDB: Stateful Dependency Breaking
# Used to break STATE dependencies
SDB_COST: Final[int] = 2

# PROXY: Factory/Proxy pattern
# Used for more complex dependency restructuring
PROXY_COST: Final[int] = 3


# =============================================================================
# Edge Types
# =============================================================================


class EdgeType(str, Enum):
    """Types of edges in the Deployment Dependency Graph."""

    # Address discovered at deployment time
    ADDR = "ADDR"

    # Initialization order matters, constructor dependencies
    STATE = "STATE"

    # No deployment constraint, resolved at runtime
    RUNTIME = "RUNTIME"


# Edge type repair costs
EDGE_TYPE_COSTS: Final[dict[EdgeType, int]] = {
    EdgeType.ADDR: DARC_COST,
    EdgeType.STATE: SDB_COST,
    EdgeType.RUNTIME: 0,  # No repair needed for runtime edges
}


# =============================================================================
# Deployment Feasibility Rating
# =============================================================================


class DeploymentRating(str, Enum):
    """Deployment Feasibility Rating values."""

    DEPLOYABLE = "DEPLOYABLE"
    REPAIRABLE = "REPAIRABLE"
    IRREPARABLE = "IRREPARABLE"


# =============================================================================
# Illusion Depth Stages
# =============================================================================


class ValidationStage(IntEnum):
    """Validation stages for Illusion Depth calculation."""

    UNPARSEABLE = 0
    PARSEABLE = 1
    COMPILE = 2
    LINT = 3
    TYPE_CHECK = 4
    UNIT_TEST = 5
    INTEGRATION = 6
    SAST = 7
    BUILD = 8
    DEPLOY = 9
    HEALTHY = 10


# Stage descriptions for reporting
STAGE_DESCRIPTIONS: Final[dict[ValidationStage, str]] = {
    ValidationStage.UNPARSEABLE: "Code cannot be parsed",
    ValidationStage.PARSEABLE: "Code parses successfully",
    ValidationStage.COMPILE: "Code compiles/transpiles",
    ValidationStage.LINT: "Code passes linting",
    ValidationStage.TYPE_CHECK: "Code passes type checking",
    ValidationStage.UNIT_TEST: "Unit tests pass",
    ValidationStage.INTEGRATION: "Integration tests pass",
    ValidationStage.SAST: "Static analysis security testing passes",
    ValidationStage.BUILD: "Docker/container build succeeds",
    ValidationStage.DEPLOY: "Deployment succeeds",
    ValidationStage.HEALTHY: "Health checks pass",
}


# =============================================================================
# Confidence Levels
# =============================================================================


class Confidence(str, Enum):
    """Confidence levels for extracted edges."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# =============================================================================
# Timeouts and Limits
# =============================================================================

# Registry check timeout in seconds
REGISTRY_TIMEOUT: Final[int] = 5

# Maximum file size to analyze (in bytes)
MAX_FILE_SIZE: Final[int] = 10 * 1024 * 1024  # 10 MB

# Maximum number of files to analyze
MAX_FILES: Final[int] = 10000

# Cache TTL for registry checks (in seconds)
REGISTRY_CACHE_TTL: Final[int] = 3600  # 1 hour


# =============================================================================
# File Patterns
# =============================================================================

# Python file patterns
PYTHON_PATTERNS: Final[list[str]] = ["*.py", "*.pyi"]

# JavaScript/TypeScript patterns
JS_PATTERNS: Final[list[str]] = ["*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs", "*.cjs"]

# Solidity patterns
SOLIDITY_PATTERNS: Final[list[str]] = ["*.sol"]

# Docker patterns
DOCKER_PATTERNS: Final[list[str]] = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
]

# Config file patterns
CONFIG_PATTERNS: Final[list[str]] = [
    ".env",
    ".env.*",
    "*.yaml",
    "*.yml",
    "*.json",
    "*.toml",
    "*.ini",
    "*.cfg",
]

# Dependency file patterns
DEPENDENCY_PATTERNS: Final[list[str]] = [
    "requirements.txt",
    "requirements/*.txt",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.toml",
    "go.mod",
]

# Directories to skip during analysis
SKIP_DIRS: Final[set[str]] = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    ".eggs",
    "*.egg-info",
    "node_modules",
    "bower_components",
    "vendor",
    "venv",
    ".venv",
    "env",
    ".env",
    "virtualenv",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    "htmlcov",
}

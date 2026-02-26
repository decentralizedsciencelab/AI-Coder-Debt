"""Tier 2 Integration Metrics: ICR, CCS."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from ..extractors.config import ConfigExtractor
from ..extractors.interface import InterfaceExtractor
from ..models import APICall, APIEndpoint, CCSResult, ConfigReference, ICRResult

if TYPE_CHECKING:
    pass


class IntegrationMetrics:
    """Calculate Tier 2 integration metrics: ICR, CCS."""

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the integration metrics calculator.

        Args:
            project_path: Path to the project directory.
        """
        self.project_path = Path(project_path).resolve()
        self._interface_extractor = InterfaceExtractor(project_path)
        self._config_extractor = ConfigExtractor(project_path)

    def calculate_icr(self) -> ICRResult:
        """Calculate Interface Consistency Rate (ICR).

        ICR = matched_internal_calls / (total_internal_calls + 1)

        Uses additive smoothing (k=1) so zero calls yield 0.0 rather than
        a vacuously perfect score.

        Returns:
            ICRResult with rate and details.
        """
        # Extract API calls and endpoints
        calls = self._interface_extractor.extract_api_calls()
        endpoints = self._interface_extractor.extract_endpoints()

        # Filter to internal calls only
        internal_calls = [c for c in calls if c.is_internal]

        # Build endpoint lookup
        endpoint_patterns = self._build_endpoint_patterns(endpoints)

        # Match calls to endpoints
        matched = 0
        unmatched: list[APICall] = []

        for call in internal_calls:
            if self._matches_endpoint(call, endpoint_patterns):
                matched += 1
            else:
                unmatched.append(call)

        rate = matched / (len(internal_calls) + 1)

        return ICRResult(
            rate=rate,
            matched_calls=matched,
            total_internal_calls=len(internal_calls),
            unmatched_calls=unmatched,
            endpoints=endpoints,
        )

    def calculate_ccs(self) -> CCSResult:
        """Calculate Configuration Coherence Score (CCS).

        CCS = resolved_config_refs / (total_config_refs + 1)

        Uses additive smoothing (k=1) so zero references yield 0.0 rather
        than a vacuously perfect score.

        Returns:
            CCSResult with score and details.
        """
        # Extract config definitions and references
        definitions = self._config_extractor.extract_definitions()
        references = self._config_extractor.extract_references()

        # Build definition lookup
        defined_keys = {d.key for d in definitions}

        # Check references
        resolved = 0
        unresolved: list[ConfigReference] = []

        for ref in references:
            # Check if the key is defined
            if ref.key in defined_keys:
                resolved += 1
                ref.resolved = True
            else:
                # Check for partial matches (e.g., DB_HOST matches DATABASE_HOST)
                if self._fuzzy_config_match(ref.key, defined_keys):
                    resolved += 1
                    ref.resolved = True
                else:
                    unresolved.append(ref)

        score = resolved / (len(references) + 1)

        return CCSResult(
            score=score,
            resolved_configs=resolved,
            total_config_refs=len(references),
            unresolved_refs=unresolved,
            definitions=definitions,
        )

    def _build_endpoint_patterns(
        self, endpoints: list[APIEndpoint]
    ) -> list[tuple[str, re.Pattern, str]]:
        """Build regex patterns for endpoint matching.

        Args:
            endpoints: List of endpoint definitions.

        Returns:
            List of (method, pattern, original_path) tuples.
        """
        patterns: list[tuple[str, re.Pattern, str]] = []

        for endpoint in endpoints:
            # Convert path to regex pattern
            # Replace path parameters like :id or {id} with wildcards
            path = endpoint.path

            # Express-style :param
            path = re.sub(r":(\w+)", r"[^/]+", path)
            # FastAPI/Flask-style {param}
            path = re.sub(r"\{(\w+)\}", r"[^/]+", path)
            # Django-style <param>
            path = re.sub(r"<[^>]+>", r"[^/]+", path)

            # Escape special regex characters (except already processed)
            path = re.escape(path).replace(r"\[", "[").replace(r"\]", "]")
            path = path.replace(r"\^", "^").replace(r"\+", "+")

            try:
                pattern = re.compile(f"^{path}$")
                patterns.append((endpoint.method, pattern, endpoint.path))
            except re.error:
                # Skip invalid patterns
                continue

        return patterns

    def _matches_endpoint(
        self,
        call: APICall,
        endpoint_patterns: list[tuple[str, re.Pattern, str]],
    ) -> bool:
        """Check if a call matches any endpoint.

        Args:
            call: API call to check.
            endpoint_patterns: List of endpoint patterns.

        Returns:
            True if the call matches an endpoint.
        """
        # Extract path from endpoint URL
        call_path = call.endpoint

        # Remove protocol and host if present
        if "://" in call_path:
            call_path = call_path.split("://", 1)[1]
            if "/" in call_path:
                call_path = "/" + call_path.split("/", 1)[1]
            else:
                call_path = "/"

        # Remove query string
        if "?" in call_path:
            call_path = call_path.split("?")[0]

        # Handle template variables - treat as matching any path
        if "${" in call_path or "{{" in call_path or "{" in call_path:
            # Template variable - could match any endpoint
            return True

        for method, pattern, _ in endpoint_patterns:
            # Check method match (or * for any method)
            if method != "*" and method != call.method:
                continue

            # Check path match
            if pattern.match(call_path):
                return True

        return False

    def _fuzzy_config_match(self, key: str, defined_keys: set[str]) -> bool:
        """Check for fuzzy config key matches.

        Args:
            key: Key to look for.
            defined_keys: Set of defined keys.

        Returns:
            True if a fuzzy match is found.
        """
        # Normalize key for comparison
        normalized = key.upper().replace("-", "_")

        for defined_key in defined_keys:
            defined_normalized = defined_key.upper().replace("-", "_")

            # Exact match after normalization
            if normalized == defined_normalized:
                return True

            # Check for common prefixes (e.g., DB_ for database)
            # This handles cases like DB_HOST vs DATABASE_HOST
            common_prefixes = [
                ("DB_", "DATABASE_"),
                ("REDIS_", "CACHE_"),
                ("API_", "SERVICE_"),
                ("APP_", "APPLICATION_"),
            ]
            for prefix1, prefix2 in common_prefixes:
                if normalized.startswith(prefix1):
                    alt_key = prefix2 + normalized[len(prefix1):]
                    if alt_key == defined_normalized:
                        return True
                if normalized.startswith(prefix2):
                    alt_key = prefix1 + normalized[len(prefix2):]
                    if alt_key == defined_normalized:
                        return True

        return False

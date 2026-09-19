"""LLM-as-a-Judge metrics for AI Coder Debt estimation.

Estimates five metrics from the AI Coder Debt taxonomy using a multi-run
protocol with 5-point ordinal scales, system-prompt paraphrases, and
leakage controls:

  Defect Density         -- severity of likely bugs (1-5 ordinal)
  Vulnerability Density  -- severity of security issues (1-5 ordinal)
  Deployment Risk        -- likelihood of deployment failure (1-5 ordinal)
  Ownership Void Index   -- proportion of unreviewed AI output (1-5 ordinal)
  Specification Alignment-- internal coherence & self-documentation (1-5 ordinal)

Each metric is evaluated by presenting sampled source code (up to ~50 KB)
and a structured rubric to an LLM, which returns a JSON result with:
  - integer score (1-5)
  - confidence (high/medium/low)
  - evidence (file:line citations)
  - reasoning

The multi-run protocol uses 3 semantically-equivalent system-prompt
paraphrases per metric and temperature 0.0 for reproducibility.
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

try:
    import openai as _openai
except ImportError:
    _openai = None  # type: ignore[assignment]

from ..constants import SKIP_DIRS
from ..levels import NATIVE_MARKER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source file extensions to consider
# ---------------------------------------------------------------------------

_SOURCE_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".sol", ".go", ".rs",
    ".java", ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".mjs", ".cjs",
}

# Entry-point filenames that should be prioritised when sampling
_ENTRY_POINT_NAMES: set[str] = {
    "main.py", "app.py", "index.js", "index.ts", "server.js", "server.ts",
    "manage.py", "wsgi.py", "asgi.py", "run.py", "cli.py", "__main__.py",
    "index.jsx", "index.tsx", "app.js", "app.ts", "app.jsx", "app.tsx",
}

# ---------------------------------------------------------------------------
# Leakage control instruction (appended to all rubric prompts)
# ---------------------------------------------------------------------------

_LEAKAGE_CONTROL = (
    "\nIMPORTANT: Evaluate ONLY the source code artifacts supplied below. Do not "
    "assume the existence of additional files, documentation, tests, or "
    "infrastructure not shown.\n"
)

SCALE_ORDINAL = "ordinal_1_5"
SCALE_NATIVE = "native"

# Native unit of each metric, and the native midpoint of each 1-5 band.
# Midpoints are read directly off the calibration anchors in the rubrics
# below (e.g. the defect anchor "2-5 per KLOC" -> 3.5); the open-ended top
# anchor uses the lower edge scaled by the width of the one beneath it.
# These drive ordinal->native conversion of the legacy ordinal results.
METRIC_NATIVE_UNITS: dict[str, str] = {
    "defect_density": "defects per KLOC",
    "vulnerability_density": "vulnerabilities per KLOC",
    "deployment_risk": "probability in [0,1]",
    "ownership_void": "percent of codebase",
    "specification_alignment": "coherence in [0,1], higher is better",
}

METRIC_BAND_MIDPOINTS: dict[str, tuple[float, float, float, float, float]] = {
    "defect_density": (1.0, 3.5, 7.5, 15.0, 25.0),
    "vulnerability_density": (0.5, 2.0, 4.0, 7.5, 15.0),
    "deployment_risk": (0.1, 0.3, 0.5, 0.7, 0.9),
    "ownership_void": (10.0, 30.0, 50.0, 70.0, 90.0),
    "specification_alignment": (0.1, 0.3, 0.5, 0.7, 0.9),
}

# Valid range of each metric on its native scale.  ``None`` upper bounds
# are open: the density metrics have no ceiling, though values far above
# the top calibration anchor are logged as suspect.
METRIC_NATIVE_RANGES: dict[str, tuple[float, float | None]] = {
    "defect_density": (0.0, None),
    "vulnerability_density": (0.0, None),
    "deployment_risk": (0.0, 1.0),
    "ownership_void": (0.0, 100.0),
    "specification_alignment": (0.0, 1.0),
}


def ordinal_to_native(metric_name: str, score: float) -> float:
    """Convert a 1-5 ordinal band to the metric's native unit.

    Uses the native interval midpoint that each rubric band already
    names, so the mapping is documented by the rubric rather than chosen
    here.  The conversion is lossy: the ordinal instrument resolves five
    strata where the native instrument resolved a continuum.
    """
    bands = METRIC_BAND_MIDPOINTS.get(metric_name)
    if bands is None:
        raise KeyError(f"No band mapping for metric {metric_name!r}")
    idx = max(1, min(5, int(round(float(score))))) - 1
    return bands[idx]


class ScaleError(ValueError):
    """Base class for scale-determination failures."""


class AmbiguousScaleError(ScaleError):
    """Scores are legal on both scales, so their units cannot be inferred."""


class ConflictingScaleError(ScaleError):
    """Scores carry decisive evidence for both scales at once."""


# Largest legal ordinal band.  A value above this cannot be a band index.
ORDINAL_MAX = 5.0


def infer_scale(
    samples: Iterable[tuple[str, float]],
) -> str | None:
    """Infer whether *samples* are native-unit or 1-5 ordinal scores.

    Inference rests only on values that are impossible on one scale:

    * above the metric's native ceiling -- must be an ordinal band
      (a ``deployment_risk`` of 3.0 cannot be a probability);
    * above :data:`ORDINAL_MAX` -- must be native
      (an ``ownership_void`` of 90 is not a band index).

    Returns ``None`` when no observation is decisive.  This is the common
    case for a lone ``ownership_void`` in [1, 5], which is simultaneously a
    legal percentage and a legal band -- the reason a range check alone
    cannot certify units.  One decisive observation settles a whole set, so
    pass every score from a file rather than one metric at a time.

    Raises:
        ConflictingScaleError: if both scales are decisively indicated.
    """
    says_ordinal: list[str] = []
    says_native: list[str] = []

    for metric_name, score in samples:
        bounds = METRIC_NATIVE_RANGES.get(metric_name)
        if bounds is None:
            continue
        value = float(score)
        _, native_max = bounds
        if native_max is not None and value > native_max:
            says_ordinal.append(f"{metric_name}={value:g}")
        elif value > ORDINAL_MAX:
            says_native.append(f"{metric_name}={value:g}")

    if says_ordinal and says_native:
        raise ConflictingScaleError(
            "Scores indicate both scales at once: "
            f"{', '.join(says_ordinal)} exceed their native range while "
            f"{', '.join(says_native)} exceed the 1-5 ordinal range. "
            "The set likely mixes results from different runs."
        )
    if says_ordinal:
        return SCALE_ORDINAL
    if says_native:
        return SCALE_NATIVE
    return None


def native_scores(
    samples: Iterable[tuple[str, float]],
    scale: str | None = None,
) -> dict[str, float]:
    """Return a native-unit judge dict ready for :func:`compute_l4_debt`.

    *samples* is an iterable of ``(metric_name, score)`` pairs, typically
    every row of a stored results file; repeated metrics are averaged, so
    per-run rows collapse to one score per metric.  The result carries
    :data:`NATIVE_MARKER`, so it needs no further stamping.

    Pass *scale* when the provenance is known.  Otherwise the scale is
    inferred, and an undecidable set is an error rather than a guess:
    silently reading an ordinal 3.67 as 3.67 percent would understate an
    ownership void of roughly 70 percent by an order of magnitude.

    Raises:
        AmbiguousScaleError: if *scale* is omitted and cannot be inferred.
        ConflictingScaleError: if the samples indicate both scales.
    """
    collected: dict[str, list[float]] = {}
    for metric_name, score in samples:
        collected.setdefault(metric_name, []).append(float(score))

    if scale is None:
        scale = infer_scale(
            (name, value)
            for name, values in collected.items()
            for value in values
        )
    if scale is None:
        raise AmbiguousScaleError(
            "Cannot determine the scale of these scores: every value is "
            "legal both as a native unit and as a 1-5 ordinal band. Pass "
            f"scale={SCALE_NATIVE!r} or scale={SCALE_ORDINAL!r} explicitly, "
            "sourcing it from the run that produced them."
        )

    result: dict[str, float] = {NATIVE_MARKER: True}  # type: ignore[dict-item]
    for metric_name, values in collected.items():
        mean = statistics.mean(values)
        result[metric_name] = to_native(metric_name, mean, scale)
    return result


def to_native(metric_name: str, score: float, scale: str) -> float:
    """Return *score* in the metric's native unit, given its *scale*."""
    if scale == SCALE_NATIVE:
        return float(score)
    if scale == SCALE_ORDINAL:
        return ordinal_to_native(metric_name, score)
    raise ValueError(
        f"Unknown score scale {scale!r} for {metric_name!r}; "
        f"expected {SCALE_NATIVE!r} or {SCALE_ORDINAL!r}"
    )


# ---------------------------------------------------------------------------
# Result models (dataclass -- lightweight, no Pydantic dependency)
# ---------------------------------------------------------------------------

@dataclass
class LLMJudgeResult:
    """Result of a single LLM-as-Judge metric evaluation."""

    metric_name: str
    score: float
    confidence: str  # "high", "medium", "low"
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    raw_response: str = ""
    run_index: int = 0


@dataclass
class LLMJudgeReport:
    """Aggregated LLM-as-Judge report for a project."""

    project_path: str
    files_sampled: int = 0
    kloc: float = 0.0
    defect_density: LLMJudgeResult | None = None
    vulnerability_density: LLMJudgeResult | None = None
    deployment_risk: LLMJudgeResult | None = None
    ownership_void: LLMJudgeResult | None = None
    specification_alignment: LLMJudgeResult | None = None


# ---------------------------------------------------------------------------
# System prompt paraphrases (3 per metric, 15 total)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS: dict[str, list[str]] = {
    "defect_density": [
        (
            "You are an expert software quality auditor. Your task is to review "
            "source code and assess the severity of likely functional defects. "
            "Evaluate ONLY the source artifacts supplied below — do not assume or "
            "infer information from external sources, documentation, or commit "
            "history. You must respond ONLY with a JSON object."
        ),
        (
            "Acting as a senior code quality analyst, examine the provided source "
            "code to judge how severely it is affected by probable functional bugs. "
            "Base your evaluation strictly on the supplied code — do not reference "
            "external documentation, commit logs, or assumed context. Respond "
            "exclusively with a JSON object."
        ),
        (
            "You are a seasoned software reliability engineer reviewing source "
            "code for latent functional defects. Restrict your analysis to the "
            "artifacts provided — do not infer the presence of additional files, "
            "tests, or documentation not shown. Return ONLY a JSON object."
        ),
    ],
    "vulnerability_density": [
        (
            "You are an expert application security auditor. Your task is to review "
            "source code and assess the severity of security vulnerabilities. "
            "Evaluate ONLY the source artifacts supplied below — do not assume or "
            "infer information from external sources, documentation, or commit "
            "history. You must respond ONLY with a JSON object."
        ),
        (
            "Acting as a senior penetration tester, examine the provided source "
            "code to judge how severely it is affected by security weaknesses. "
            "Base your evaluation strictly on the supplied code — do not reference "
            "external documentation, threat models, or assumed configurations. "
            "Respond exclusively with a JSON object."
        ),
        (
            "You are a seasoned application security engineer reviewing source "
            "code for exploitable vulnerabilities. Restrict your analysis to the "
            "artifacts provided — do not infer the existence of additional security "
            "controls, WAFs, or infrastructure not shown. Return ONLY a JSON object."
        ),
    ],
    "deployment_risk": [
        (
            "You are an expert DevOps / SRE engineer. Your task is to review a "
            "project's source code and assess how likely a deployment attempt would "
            "fail. Evaluate ONLY the source artifacts supplied below — do not "
            "assume or infer information from external sources, documentation, or "
            "commit history. You must respond ONLY with a JSON object."
        ),
        (
            "Acting as a senior infrastructure reliability engineer, examine the "
            "provided source code to judge the severity of deployment risk. Base "
            "your evaluation strictly on the supplied code — do not reference "
            "external CI/CD pipelines, orchestration configs, or assumed "
            "environments. Respond exclusively with a JSON object."
        ),
        (
            "You are a seasoned release engineer reviewing source code for "
            "deployment readiness. Restrict your analysis to the artifacts "
            "provided — do not infer the existence of additional deployment "
            "tooling, monitoring, or infrastructure not shown. Return ONLY a "
            "JSON object."
        ),
    ],
    "ownership_void": [
        (
            "You are an expert code reviewer specialising in identifying "
            "AI-generated code versus human-authored code. Your task is to "
            "estimate what proportion of a codebase appears to be unreviewed AI "
            "output. Evaluate ONLY the source artifacts supplied below — do not "
            "assume or infer information from external sources, documentation, or "
            "commit history. You must respond ONLY with a JSON object."
        ),
        (
            "Acting as a senior software craftsmanship auditor, examine the "
            "provided source code to judge how much of it appears to be "
            "unreviewed machine-generated output. Base your evaluation strictly "
            "on the supplied code — do not reference external metadata, commit "
            "attribution, or assumed authorship signals. Respond exclusively with "
            "a JSON object."
        ),
        (
            "You are a seasoned code provenance analyst reviewing source code "
            "for signs of unreviewed AI generation. Restrict your analysis to the "
            "artifacts provided — do not infer authorship from filenames, repo "
            "structure, or context not shown. Return ONLY a JSON object."
        ),
    ],
    "specification_alignment": [
        (
            "You are an expert software architect. Your task is to assess the "
            "internal coherence and self-documentation quality of a project's "
            "source code. Evaluate ONLY the source artifacts supplied below — "
            "do not assume or infer information from external sources, "
            "documentation, or commit history. You must respond ONLY with a "
            "JSON object."
        ),
        (
            "Acting as a senior technical lead, examine the provided source code "
            "to judge how well it is internally coherent and self-documenting. "
            "Base your evaluation strictly on the supplied code — do not reference "
            "external READMEs, specifications, or assumed requirements. Respond "
            "exclusively with a JSON object."
        ),
        (
            "You are a seasoned software design reviewer assessing a codebase's "
            "internal consistency and clarity of purpose. Restrict your analysis "
            "to the artifacts provided — do not infer the existence of additional "
            "documentation, specs, or design docs not shown. Return ONLY a "
            "JSON object."
        ),
    ],
}


# ---------------------------------------------------------------------------
# LLMJudge
# ---------------------------------------------------------------------------

class LLMJudge:
    """Estimates AI Coder Debt metrics using an LLM as expert judge.

    Usage::

        judge = LLMJudge()
        report = judge.judge_all(Path("/path/to/project"))
        print(report.defect_density.score)
    """

    def __init__(self, model: str | None = None, backend: str | None = None) -> None:
        """Initialise the judge.

        Parameters
        ----------
        model : str, optional
            Model identifier.  Defaults to ``claude-sonnet-4-20250514`` for
            Anthropic or ``gpt-4o`` for OpenAI.
        backend : str, optional
            ``"anthropic"`` or ``"openai"``.  If *None* the backend is
            auto-detected: Anthropic is preferred when a valid API key is
            available, otherwise OpenAI.
        """
        if backend is None:
            # Auto-detect: try Anthropic first, fall back to OpenAI
            ant_key = os.environ.get("ANTHROPIC_API_KEY", "")
            oai_key = os.environ.get("OPENAI_API_KEY", "")
            if ant_key and anthropic is not None:
                backend = "anthropic"
            elif oai_key and _openai is not None:
                backend = "openai"
            elif anthropic is not None:
                backend = "anthropic"
            else:
                backend = "openai"

        self.backend = backend
        if backend == "anthropic":
            if anthropic is None:
                raise ImportError("anthropic package not installed")
            self.client = anthropic.Anthropic()
            self.model = model or "claude-sonnet-4-20250514"
        else:
            if _openai is None:
                raise ImportError("openai package not installed")
            self.client = _openai.OpenAI()
            self.model = model or "gpt-4o"
        logger.info("LLMJudge using backend=%s, model=%s", self.backend, self.model)

    # ------------------------------------------------------------------
    # File collection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_source_files(project_path: Path) -> list[Path]:
        """Walk *project_path* and return all source files, skipping junk dirs."""
        found: list[Path] = []
        if not project_path.is_dir():
            return found
        for dirpath, dirnames, filenames in os.walk(project_path):
            # Prune directories that should be skipped
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.endswith(".egg-info")
            ]
            for fn in filenames:
                if any(fn.endswith(ext) for ext in _SOURCE_EXTENSIONS):
                    found.append(Path(dirpath) / fn)
        return found

    def _collect_source(self, project_path: Path, max_bytes: int = 50_000) -> tuple[str, int, float]:
        """Collect representative source from *project_path* up to *max_bytes*.

        Prioritisation order:
          1. Entry-point files (main.py, app.py, index.js, ...)
          2. Remaining files sorted by size descending (larger = more logic)

        Returns ``(concatenated_source, files_sampled, kloc)``.
        """
        all_files = self._find_source_files(project_path)
        if not all_files:
            return "", 0, 0.0

        # Partition into entry points and others
        entry_points: list[Path] = []
        others: list[Path] = []
        for fp in all_files:
            if fp.name in _ENTRY_POINT_NAMES:
                entry_points.append(fp)
            else:
                others.append(fp)

        # Sort others by file size descending so we capture the most logic-dense files
        others.sort(key=lambda p: p.stat().st_size, reverse=True)

        ordered = entry_points + others

        # Read files until we hit the byte budget
        chunks: list[str] = []
        total_bytes = 0
        files_sampled = 0
        total_lines_all = 0  # count lines across ALL source files for KLOC

        # First pass: count total lines for KLOC (fast scan)
        for fp in all_files:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                non_blank = sum(1 for line in text.splitlines() if line.strip())
                total_lines_all += non_blank
            except Exception:
                pass

        # Second pass: sample files for the prompt
        for fp in ordered:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            file_bytes = len(text.encode("utf-8"))

            # If a single file exceeds the remaining budget, truncate it
            remaining = max_bytes - total_bytes
            if remaining <= 0:
                break

            if file_bytes > remaining:
                # Truncate to remaining budget (at a line boundary)
                lines = text.splitlines(keepends=True)
                truncated_lines: list[str] = []
                acc = 0
                for line in lines:
                    acc += len(line.encode("utf-8"))
                    if acc > remaining:
                        break
                    truncated_lines.append(line)
                text = "".join(truncated_lines)
                if not text:
                    break
                file_bytes = len(text.encode("utf-8"))

            rel_path = fp.relative_to(project_path) if fp.is_relative_to(project_path) else fp
            header = f"\n{'='*60}\n# FILE: {rel_path}\n{'='*60}\n"
            chunks.append(header + text)
            total_bytes += file_bytes + len(header.encode("utf-8"))
            files_sampled += 1

        kloc = total_lines_all / 1000.0
        return "".join(chunks), files_sampled, kloc

    @staticmethod
    def _collect_readme(project_path: Path) -> str:
        """Read the first README-like file found in *project_path*."""
        candidates = [
            "README.md", "README.rst", "README.txt", "README",
            "readme.md", "readme.rst", "readme.txt",
            "docs/README.md", "docs/index.md",
        ]
        for name in candidates:
            p = project_path / name
            if p.exists() and p.is_file():
                try:
                    return p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
        return ""

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        temperature: float = 0.0,
    ) -> str:
        """Call the LLM and return the assistant's text response.

        Parameters
        ----------
        system_prompt : str
            System-level instructions for the judge.
        user_prompt : str
            User-level prompt containing the rubric and source code.
        max_retries : int
            Maximum number of retries on rate-limit errors.
        temperature : float
            Sampling temperature.  Default 0.0 for deterministic output.

        Retries with exponential backoff on rate-limit (429) errors.
        """
        for attempt in range(max_retries + 1):
            try:
                if self.backend == "anthropic":
                    message = self.client.messages.create(
                        model=self.model,
                        max_tokens=4096,
                        temperature=temperature,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    parts: list[str] = []
                    for block in message.content:
                        if hasattr(block, "text"):
                            parts.append(block.text)
                    return "\n".join(parts)
                else:
                    # OpenAI-compatible
                    response = self.client.chat.completions.create(
                        model=self.model,
                        max_tokens=4096,
                        temperature=temperature,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    )
                    return response.choices[0].message.content or ""
            except Exception as exc:
                exc_str = str(exc)
                is_rate_limit = "429" in exc_str or "rate_limit" in exc_str.lower()
                if is_rate_limit and attempt < max_retries:
                    wait = 2 ** attempt * 10  # 10s, 20s, 40s
                    logger.warning(
                        "Rate limited (attempt %d/%d), waiting %ds...",
                        attempt + 1, max_retries + 1, wait,
                    )
                    time.sleep(wait)
                    continue
                logger.error("LLM call failed (%s): %s", self.backend, exc)
                raise RuntimeError(f"LLM call failed ({self.backend}): {exc}") from exc
        # Should not reach here, but just in case
        raise RuntimeError("LLM call failed: max retries exceeded")

    @staticmethod
    def _parse_json_response(response: str) -> dict:
        """Extract and parse the first JSON object from *response*.

        The LLM may wrap JSON in markdown fences or include preamble text.
        This method tries multiple strategies to locate valid JSON.
        """
        if not response:
            return {}

        # Strategy 1: look for ```json ... ``` fenced block
        fenced = re.search(r"```json\s*\n?(.*?)```", response, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 2: look for any ``` ... ``` fenced block
        fenced_any = re.search(r"```\s*\n?(.*?)```", response, re.DOTALL)
        if fenced_any:
            try:
                return json.loads(fenced_any.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: find the first { ... } span
        brace_start = response.find("{")
        if brace_start != -1:
            # Walk forward to find matching closing brace
            depth = 0
            for i in range(brace_start, len(response)):
                if response[i] == "{":
                    depth += 1
                elif response[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(response[brace_start : i + 1])
                        except json.JSONDecodeError:
                            break

        # Strategy 4: try parsing the whole response as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        logger.warning("Could not parse JSON from LLM response (length=%d)", len(response))
        return {}

    def _build_result(
        self,
        metric_name: str,
        raw_response: str,
        default_score: float = 3.0,
        run_index: int = 0,
    ) -> LLMJudgeResult:
        """Parse a raw LLM response into an ``LLMJudgeResult``.

        Scores are rounded and clamped to the 1-5 integer range.
        """
        parsed = self._parse_json_response(raw_response)

        score = parsed.get("score", default_score)
        if isinstance(score, str):
            try:
                score = float(score)
            except ValueError:
                score = default_score

        # Clamp to 1-5 integer ordinal scale
        score = max(1, min(5, int(round(float(score)))))

        confidence = parsed.get("confidence", "low")
        if confidence not in ("high", "medium", "low"):
            confidence = "low"

        evidence = parsed.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        evidence = [str(e) for e in evidence]

        reasoning = parsed.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)

        return LLMJudgeResult(
            metric_name=metric_name,
            score=float(score),
            confidence=confidence,
            evidence=evidence,
            reasoning=reasoning,
            raw_response=raw_response,
            run_index=run_index,
        )

    # ------------------------------------------------------------------
    # Helper: select system prompt for a run
    # ------------------------------------------------------------------

    @staticmethod
    def _get_system_prompt(metric_key: str, run_index: int) -> str:
        """Return the system prompt for *metric_key* and *run_index*."""
        prompts = _SYSTEM_PROMPTS.get(metric_key, [])
        if not prompts:
            return ""
        return prompts[run_index % len(prompts)]

    # ------------------------------------------------------------------
    # Metric: Defect Density (5-point ordinal)
    # ------------------------------------------------------------------

    _RS1_RUBRIC = """\
Analyze the following source code and rate the severity of its **Defect \
Density** (likely functional bugs) on a 1-5 integer scale.

Consider these defect categories:
- Logic errors (wrong conditions, incorrect algorithm)
- Off-by-one errors
- Null / None dereference or missing None checks
- Unhandled edge cases (empty inputs, boundary values)
- Race conditions or concurrency issues
- Incorrect API usage (wrong argument order, missing required args)
- Resource leaks (unclosed files, connections)
- Error handling gaps (bare except, swallowed exceptions)
- Type confusion or implicit coercion bugs

Scoring rubric (integer 1-5):
  1 = Negligible: fewer than 2 likely bugs per KLOC; high-quality, well-reviewed code
  2 = Low: 2-5 per KLOC; typical production code with minor issues
  3 = Moderate: 5-10 per KLOC; below average, needs review
  4 = High: 10-20 per KLOC; poor quality, many issues
  5 = Severe: 20+ per KLOC; pervasively defect-prone

The project has {kloc:.1f} KLOC of source code.
{leakage_control}
Respond with ONLY a JSON object in this exact format:
{{
  "score": <integer 1-5>,
  "confidence": "<high|medium|low>",
  "evidence": ["<file:line - description>", ...],
  "reasoning": "<1-3 sentence summary of overall code quality>"
}}

SOURCE CODE:
{source}
"""

    def judge_defect_density(
        self, project_path: Path, run_index: int = 0
    ) -> LLMJudgeResult:
        """Estimate defect density severity (1-5 ordinal)."""
        project_path = Path(project_path).resolve()
        source, _, kloc = self._collect_source(project_path)

        if not source:
            return LLMJudgeResult(
                metric_name="defect_density",
                score=1.0,
                confidence="low",
                reasoning="No source files found in project.",
                run_index=run_index,
            )

        system = self._get_system_prompt("defect_density", run_index)
        prompt = self._RS1_RUBRIC.format(
            kloc=kloc, source=source, leakage_control=_LEAKAGE_CONTROL,
        )
        raw = self._call_llm(system, prompt, temperature=0.0)
        return self._build_result("defect_density", raw, default_score=3.0, run_index=run_index)

    # ------------------------------------------------------------------
    # Metric: Vulnerability Density (5-point ordinal)
    # ------------------------------------------------------------------

    _RS2_RUBRIC = """\
Analyze the following source code and rate the severity of its \
**Vulnerability Density** (security weaknesses) on a 1-5 integer scale.

Consider the OWASP Top 10 and common vulnerability classes:
1. Injection (SQL, command, LDAP, XPath)
2. Broken Authentication (weak passwords, missing MFA, session issues)
3. Sensitive Data Exposure (hardcoded secrets, unencrypted data, logging PII)
4. XML External Entities (XXE) (unsafe XML parsing)
5. Broken Access Control (missing auth checks, IDOR, privilege escalation)
6. Security Misconfiguration (debug mode, default creds, verbose errors)
7. Cross-Site Scripting (XSS) (unsanitized user input in output)
8. Insecure Deserialization (pickle, eval, unsafe JSON parsing)
9. Using Components with Known Vulnerabilities (outdated dependencies)
10. Insufficient Logging & Monitoring (no audit trail, silent failures)

Also consider:
- Path traversal
- SSRF (Server-Side Request Forgery)
- Cryptographic weaknesses (weak algorithms, hardcoded keys)
- Unsafe file operations

Scoring rubric (integer 1-5):
  1 = Negligible: 0-1 vulnerabilities per KLOC; well-secured code
  2 = Low: 1-3 per KLOC; typical code with some issues
  3 = Moderate: 3-5 per KLOC; concerning, needs security review
  4 = High: 5-10 per KLOC; poorly secured
  5 = Severe: 10+ per KLOC; pervasively vulnerable

The project has {kloc:.1f} KLOC of source code.

Where possible, cite CWE IDs in the evidence.
{leakage_control}
Respond with ONLY a JSON object in this exact format:
{{
  "score": <integer 1-5>,
  "confidence": "<high|medium|low>",
  "evidence": ["<file:line - CWE-XXX: description>", ...],
  "reasoning": "<1-3 sentence summary of security posture>"
}}

SOURCE CODE:
{source}
"""

    def judge_vulnerability_density(
        self, project_path: Path, run_index: int = 0
    ) -> LLMJudgeResult:
        """Estimate vulnerability density severity (1-5 ordinal)."""
        project_path = Path(project_path).resolve()
        source, _, kloc = self._collect_source(project_path)

        if not source:
            return LLMJudgeResult(
                metric_name="vulnerability_density",
                score=1.0,
                confidence="low",
                reasoning="No source files found in project.",
                run_index=run_index,
            )

        system = self._get_system_prompt("vulnerability_density", run_index)
        prompt = self._RS2_RUBRIC.format(
            kloc=kloc, source=source, leakage_control=_LEAKAGE_CONTROL,
        )
        raw = self._call_llm(system, prompt, temperature=0.0)
        return self._build_result("vulnerability_density", raw, default_score=3.0, run_index=run_index)

    # ------------------------------------------------------------------
    # Metric: Deployment Risk (5-point ordinal)
    # ------------------------------------------------------------------

    _RS3_RUBRIC = """\
Analyze the following project source code and rate its **Deployment Risk** \
-- the likelihood that a deployment attempt would fail -- on a 1-5 \
integer scale.

Consider these failure modes:
- Missing or broken dependency declarations (requirements.txt, package.json)
- Hardcoded paths, IPs, or environment-specific values
- Missing environment variable definitions
- No error handling in startup / initialization code
- Race conditions in initialization (services starting before dependencies ready)
- Missing health checks or readiness probes
- No graceful shutdown handling
- Missing database migrations or schema management
- Incompatible dependency versions
- Missing build configuration (Dockerfile, CI/CD)
- No deployment scripts or infrastructure-as-code
- Missing secrets management

Scoring rubric (integer 1-5):
  1 = Very low: well-prepared for deployment, minimal gaps
  2 = Low: mostly ready, a few minor gaps
  3 = Moderate: significant gaps, deployment outcome uncertain
  4 = High: many missing pieces, likely to fail
  5 = Very high: almost certain to fail on deployment

The project has {kloc:.1f} KLOC of source code.
{leakage_control}
Respond with ONLY a JSON object in this exact format:
{{
  "score": <integer 1-5>,
  "confidence": "<high|medium|low>",
  "evidence": ["<file:line - description of issue>", ...],
  "reasoning": "<1-3 sentence summary including top failure scenarios>"
}}

SOURCE CODE:
{source}
"""

    def judge_deployment_risk(
        self, project_path: Path, run_index: int = 0
    ) -> LLMJudgeResult:
        """Estimate deployment risk severity (1-5 ordinal)."""
        project_path = Path(project_path).resolve()
        source, _, kloc = self._collect_source(project_path)

        if not source:
            return LLMJudgeResult(
                metric_name="deployment_risk",
                score=5.0,
                confidence="low",
                reasoning="No source files found in project -- deployment would certainly fail.",
                run_index=run_index,
            )

        system = self._get_system_prompt("deployment_risk", run_index)
        prompt = self._RS3_RUBRIC.format(
            kloc=kloc, source=source, leakage_control=_LEAKAGE_CONTROL,
        )
        raw = self._call_llm(system, prompt, temperature=0.0)
        return self._build_result("deployment_risk", raw, default_score=3.0, run_index=run_index)

    # ------------------------------------------------------------------
    # Metric: Ownership Void Index (5-point ordinal)
    # ------------------------------------------------------------------

    _G2_RUBRIC = """\
Analyze the following source code and rate the **Ownership Void Index** \
-- the proportion of this codebase that appears to be unreviewed \
AI-generated output -- on a 1-5 integer scale.

Signs of unreviewed AI-generated code:
- Boilerplate-heavy structure with minimal customisation
- Generic, non-domain-specific variable and function names
- Repetitive patterns that a human would refactor (copy-paste style)
- Missing edge case handling that a domain expert would include
- Template-like code structure (TODO comments, placeholder logic)
- Overly verbose comments explaining obvious code
- Inconsistent coding style within the same file
- Features that appear complete at first glance but lack depth
- No project-specific domain knowledge reflected in the code
- Missing integration between components (each file is an island)
- Unrealistic or non-functional configuration values
- Code that "looks right" but wouldn't work in practice

Signs of human-reviewed / human-authored code:
- Domain-specific naming and conventions
- Consistent style and idioms throughout
- Edge cases and error handling for realistic scenarios
- Comments explaining "why", not "what"
- Evidence of iteration (refactored patterns, optimisations)
- Integration awareness (components reference each other correctly)

Scoring rubric (integer 1-5):
  1 = Minimal: 0-20% unreviewed AI code; clearly human-crafted or thoroughly reviewed
  2 = Low: 20-40%; mostly reviewed, some unreviewed sections
  3 = Moderate: 40-60%; mixed, significant unreviewed AI output
  4 = High: 60-80%; predominantly unreviewed AI output
  5 = Pervasive: 80-100%; entirely unreviewed AI output

The project has {kloc:.1f} KLOC of source code.
{leakage_control}
Respond with ONLY a JSON object in this exact format:
{{
  "score": <integer 1-5>,
  "confidence": "<high|medium|low>",
  "evidence": ["<file:line - description of AI-generated pattern>", ...],
  "reasoning": "<1-3 sentence summary of ownership analysis>"
}}

SOURCE CODE:
{source}
"""

    def judge_ownership_void(
        self, project_path: Path, run_index: int = 0
    ) -> LLMJudgeResult:
        """Estimate ownership void severity (1-5 ordinal).

        Note the unit and the denominator when citing this alongside the
        paper's definition.  The Ownership Void Index is *defined* as a
        ratio of module counts, ``N_void / N_AI`` (Eq. eq:ovi).  This
        estimate is not that arithmetic: the judge rates each system as a
        single whole on a 1-5 band and never enumerates modules, so there
        is no numerator or denominator to report.

        The score is an ordinal band, not a percentage.  Convert it with
        :func:`to_native` (band midpoints put 4 at 70 percent) before
        comparing it to native-unit results or feeding
        :func:`aicoder_debt.levels.compute_l4_debt`, which rejects
        unconverted input.  Reading a band of 4 as 4 percent understates
        the estimate by an order of magnitude.

        Repository-signal measurement of the defined ratio requires
        ownership metadata the corpora lack; see
        :mod:`aicoder_debt.ownership` for detecting whether a given
        project could support it.
        """
        project_path = Path(project_path).resolve()
        source, _, kloc = self._collect_source(project_path)

        if not source:
            return LLMJudgeResult(
                metric_name="ownership_void",
                score=1.0,
                confidence="low",
                reasoning="No source files found in project.",
                run_index=run_index,
            )

        system = self._get_system_prompt("ownership_void", run_index)
        prompt = self._G2_RUBRIC.format(
            kloc=kloc, source=source, leakage_control=_LEAKAGE_CONTROL,
        )
        raw = self._call_llm(system, prompt, temperature=0.0)
        return self._build_result("ownership_void", raw, default_score=3.0, run_index=run_index)

    # ------------------------------------------------------------------
    # Metric: Specification Alignment (5-point ordinal)
    # ------------------------------------------------------------------

    _G3_RUBRIC = """\
Assess the **Internal Coherence and Self-Documentation Quality** of the \
following source code on a 1-5 integer scale.

Consider:
- Is the code internally consistent (naming, patterns, architecture)?
- Do modules and components reference each other correctly?
- Are function signatures, type hints, and docstrings accurate?
- Is the purpose of each module clear from its structure and naming?
- Do configuration values, constants, and defaults make sense together?
- Are error messages informative and consistent?
- Is the code self-documenting without requiring external documentation?

Scoring rubric (integer 1-5):
  1 = Incoherent: chaotic structure, contradictory patterns, purpose unclear
  2 = Poor: some structure but significant internal inconsistencies
  3 = Adequate: generally coherent but with notable gaps in self-documentation
  4 = Good: well-structured, mostly self-documenting, minor inconsistencies
  5 = Excellent: highly coherent, clearly self-documenting, consistent throughout
{leakage_control}
Respond with ONLY a JSON object in this exact format:
{{
  "score": <integer 1-5>,
  "confidence": "<high|medium|low>",
  "evidence": ["<description of coherence or inconsistency>", ...],
  "reasoning": "<1-3 sentence summary of internal coherence assessment>"
}}

SOURCE CODE:
{source}
"""

    def judge_specification_alignment(
        self, project_path: Path, run_index: int = 0
    ) -> LLMJudgeResult:
        """Rate internal coherence and self-documentation quality (1-5 ordinal)."""
        project_path = Path(project_path).resolve()
        source, _, kloc = self._collect_source(project_path)

        if not source:
            return LLMJudgeResult(
                metric_name="specification_alignment",
                score=1.0,
                confidence="low",
                reasoning="No source files found in project.",
                run_index=run_index,
            )

        system = self._get_system_prompt("specification_alignment", run_index)
        prompt = self._G3_RUBRIC.format(
            source=source, leakage_control=_LEAKAGE_CONTROL,
        )
        raw = self._call_llm(system, prompt, temperature=0.0)
        return self._build_result("specification_alignment", raw, default_score=3.0, run_index=run_index)

    # ------------------------------------------------------------------
    # Aggregate: run all metrics
    # ------------------------------------------------------------------

    def judge_all(
        self, project_path: Path, run_index: int = 0
    ) -> LLMJudgeReport:
        """Run all 5 LLM-as-Judge metrics on a project.

        Each metric is run sequentially so we do not overwhelm the API.
        Failures in individual metrics are logged but do not abort the report.

        Parameters
        ----------
        project_path : Path
            Root directory of the project to evaluate.
        run_index : int
            Index of the judge run (0, 1, 2) — selects system-prompt variant.
        """
        project_path = Path(project_path).resolve()
        _, files_sampled, kloc = self._collect_source(project_path)

        report = LLMJudgeReport(
            project_path=str(project_path),
            files_sampled=files_sampled,
            kloc=kloc,
        )

        # RS1: Defect Density
        try:
            report.defect_density = self.judge_defect_density(project_path, run_index)
        except Exception as exc:
            logger.error("defect_density failed: %s", exc)

        # RS2: Vulnerability Density
        try:
            report.vulnerability_density = self.judge_vulnerability_density(project_path, run_index)
        except Exception as exc:
            logger.error("vulnerability_density failed: %s", exc)

        # RS3: Deployment Risk
        try:
            report.deployment_risk = self.judge_deployment_risk(project_path, run_index)
        except Exception as exc:
            logger.error("deployment_risk failed: %s", exc)

        # G2: Ownership Void Index
        try:
            report.ownership_void = self.judge_ownership_void(project_path, run_index)
        except Exception as exc:
            logger.error("ownership_void failed: %s", exc)

        # G3: Specification Alignment
        try:
            report.specification_alignment = self.judge_specification_alignment(project_path, run_index)
        except Exception as exc:
            logger.error("specification_alignment failed: %s", exc)

        return report

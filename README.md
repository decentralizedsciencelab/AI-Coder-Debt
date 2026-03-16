# AI Coder Debt


## Table of Contents

- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Metric Provenance](#metric-provenance)
- [DRS Check Catalog](#drs-check-catalog)
- [Failure Mode Derivation](#failure-mode-derivation)
- [Statistical Methodology](#statistical-methodology)
- [Threshold Calibration](#threshold-calibration)
- [ACDS Normalization Sensitivity](#acds-normalization-sensitivity)
- [LLM-as-Judge Protocol](#llm-as-judge-protocol)
- [Paradigm Definitions](#paradigm-definitions)
- [Research Pipeline](#research-pipeline)

---

## Quick Start

### Install

```bash
cd aicoder-debt/
pip install -e .
```

### Analyze a Project

```bash
aicoder-debt analyze ./path/to/project
```

This runs all five metric tiers and prints a summary table with the composite ACDS score.

### Export Results

```bash
aicoder-debt analyze ./path/to/project --format json -o report.json
aicoder-debt analyze ./path/to/project --format markdown -o report.md
aicoder-debt analyze ./path/to/project --format html -o report.html
```

## CLI Reference

### Run a Single Metric

```bash
aicoder-debt dfr ./path/to/project    # Deployment Feasibility Rating
aicoder-debt drd ./path/to/project    # Deployment Repair Distance
aicoder-debt id  ./path/to/project    # Illusion Depth
aicoder-debt icr ./path/to/project    # Interface Consistency Rate
aicoder-debt ccs ./path/to/project    # Configuration Coherence Score
aicoder-debt urr ./path/to/project    # Undefined Reference Rate
aicoder-debt hd  ./path/to/project    # Hallucination Density
aicoder-debt csd ./path/to/project    # Code Smell Density
aicoder-debt ccx ./path/to/project    # Cognitive Complexity Index
```

### Extract the Dependency Graph

```bash
aicoder-debt extract-ddg ./path/to/project
aicoder-debt extract-ddg ./path/to/project -o ddg.json
```

### Useful Flags

| Flag | Effect |
|------|--------|
| `--format table\|json\|markdown\|html` | Change output format |
| `-o FILE` | Write output to a file |
| `--skip-registry-check` | Skip PyPI/npm lookups (faster, offline) |
| `--skip-maintainability` | Skip Tier 4 metrics (faster) |
| `--verbose` | Show progress details |

### Run Tests

```bash
pytest tests/
pytest tests/ -k "test_name"
```

---

## Metric Provenance


### Original Metrics

| Metric | Full Name | Level | Design Rationale |
|--------|-----------|-------|------------------|
| DRS | Deployment Readiness Score | L1 | Fraction of applicable deployment checks that pass. Captures whether the generator produced the connective tissue (manifests, configs, scripts) required for deployment. |
| APS | Architectural Presence Score | L1 | Evaluates 14 boolean architectural features to determine whether multi-component structure exists. APS = 0 classifies the system as Scenario A (Absent Architecture). |
| THI | Template Homogeneity Index | L1 | Pairwise Jaccard similarity on normalized file-tree fingerprints across a population of generated systems. Captures systematic recurrence of identical structural liabilities. |
| SID | System Integration Density | L1 | Cross-component edge density in the Deployment Dependency Graph. |
| ICR | Interface Consistency Rate | L2 | Fraction of API calls matching a corresponding endpoint definition. Additive smoothing (k=1): zero API calls yields 0.0, not undefined. |
| CCS | Configuration Coherence Score | L2 | Fraction of configuration references resolving to defined values. Additive smoothing (k=1). |
| URR | Undefined Reference Rate | L2 | Fraction of internal imports unresolvable within the project structure. Additive smoothing (k=1). |
| HD | Hallucination Density | L2 | External package imports failing to resolve against public registries (npm, PyPI), normalized by KLOC. Named by analogy to factual hallucination: the model references packages that do not exist. |
| DFR | Deployment Feasibility Rate | L2 | Fraction of systems admitting a feasible deployment plan. |
| DRD | Deployment Repair Distance | L2 | Minimal transformation cost to achieve feasible deployment. |
| ID | Illusion Depth | Meta | Highest verification stage a system passes before failure. |
| ACDS | AI Coder Debt Score | Composite | Multiplicative aggregation across levels: ACDS = 1 - ∏(1 - L_i). A single level with high debt drives the composite high. Level 3 inputs are normalized by fixed domain-anchored caps before aggregation. |
| Ownership Void Index | L4 | Fraction of modules with no assigned human owner. Assessed via LLM-as-Judge. |
| Specification Alignment | L4 | Degree to which generated code fulfills stated requirements. Assessed via LLM-as-Judge. |

### Original Metrics Using Established Tool Output

These metrics define novel composite formulations (names, formulas, multi-language aggregation, framework placement) over output from established static analysis tools.

| Metric | Full Name | Level | Data Sources | Novel Formulation |
|--------|-----------|-------|--------------|-------------------|
| CSD | Code Smell Density | L3 | Pylint, ESLint, Solhint | Multi-language issue aggregation with severity weighting, normalized by KLOC |
| CCX | Cognitive Complexity Index | L3 | Radon (Python), custom tree-sitter analyzer (JavaScript) | Cross-language average complexity with analysis_failed handling |
| SDD | Security Debt Density | L3 | 60+ OWASP-aligned SAST patterns across five languages | Multi-language security finding aggregation normalized by KLOC |
| Defect/Vulnerability Density | L4 | LLM-as-Judge with calibrated rubrics | Structured rubric-based estimation with reproducibility protocol |

---

## DRS Check Catalog

The Deployment Readiness Score applies domain-specific check suites. Checks inapplicable to a given project are excluded from the denominator (Equation 1 in the paper).

### Python Suite

| # | Check | What It Verifies |
|---|-------|-----------------|
| 1 | Test presence | At least one test file or test directory exists |
| 2 | Build configuration | setup.py, setup.cfg, pyproject.toml, or Makefile present |
| 3 | Dependency manifest | requirements.txt, Pipfile, or pyproject.toml with dependencies |
| 4 | Entry point | Identifiable application entry point (__main__.py, main.py, app.py, or console_scripts) |
| 5 | Environment configuration | .env.example, .env.template, or documented environment variables |
| 6 | CI/CD | .github/workflows/, .gitlab-ci.yml, Jenkinsfile, or equivalent |
| 7 | Dockerfile or compose | Containerization configuration present |
| 8 | README with setup instructions | README contains installation or setup section |
| 9 | Linter/formatter config | .flake8, .pylintrc, pyproject.toml with tool config, or .pre-commit-config.yaml |
| 10 | Dependency lock file | requirements.txt with pinned versions, Pipfile.lock, or poetry.lock |
| 11 | Error handling patterns | Exception handling present beyond bare except clauses |
| 12 | Logging configuration | Logging module usage or logging configuration file |

### DApp Suite

Applied to Solidity/JavaScript projects. Serves as the general-purpose fallback for JavaScript/TypeScript projects.

| # | Check | What It Verifies |
|---|-------|-----------------|
| 1 | Test presence | Test files or test directory exists |
| 2 | Build configuration | Hardhat config, Truffle config, package.json with build scripts |
| 3 | Dependency manifest | package.json with dependencies |
| 4 | Entry point | Deploy scripts, migration files, or application entry point |
| 5 | Environment configuration | .env.example or documented environment variables |
| 6 | CI/CD | CI/CD configuration present |
| 7 | Dockerfile or compose | Containerization configuration present |
| 8 | ABI artifacts | Compiled contract ABIs or build output directory |
| 9 | Contract verification | Verification scripts or Etherscan integration |
| 10 | Network configuration | Deployment network definitions (mainnet, testnet) |
| 11 | Dependency lock file | package-lock.json or yarn.lock |
| 12 | README with setup instructions | README contains installation or setup section |

Checks 8, 9, and 10 are specific to blockchain projects and are excluded from the denominator when applied to non-blockchain JavaScript/TypeScript projects.

---

## Failure Mode Derivation

The 47 failure modes in Table 3 were derived through three sources:

1. **Literature analysis.** Systematic review of LLM code generation evaluation literature, extracting reported failure types from HumanEval, SWE-bench, DevBench, DI-Bench, DependEval, and security evaluation studies. Primary source for Level 2 and 3 failure modes.

2. **Empirical generation analysis.** Iterative analysis of generation failures across the 10 corpora during pipeline development. Each pipeline failure was traced to root cause and classified. Primary source for Level 1 failure modes (infrastructure and deployment), which are not captured by existing benchmarks.

3. **Cross-referencing with established taxonomies.** Candidate failure modes were mapped against ISO 25010 quality characteristics, SonarQube rule categories, and OWASP Top 10 to verify coverage and confirm that novel failure modes were not already captured under different terminology.

Saturation was reached when analysis of additional corpora and literature sources yielded no new categories. Distribution: Infrastructure and Deployment (8, L1), Service Integration (9, L2), Configuration Coherence (5, L2), Dependency and Environment (8, L2), Multi-File Coordination (7, L2), Code Quality and Complexity (10, L3).

### Table 3 Column Definitions

| Column | Meaning |
|--------|---------|
| **Category** | Failure mode group |
| **Level** | Framework level (1, 2, or 3) |
| **Modes** | Count of distinct failure modes in the category |
| **Stage** | Detection pipeline stage(s) in Section 3.4 where the failure is first detectable, corresponding to the three-layer extraction pipeline and downstream analysis |
| **Coverage** | Existing tool/benchmark coverage: None, Weak, Partial, or Strong |

Level 4 (Traceability) failure modes are assessed via LLM-as-Judge and are not included in the automated taxonomy.

---

## Statistical Methodology

### Test Selection

Mann-Whitney U was selected because metric distributions are non-normal. DRS exhibits strong bimodality (systems cluster near 0.0 and near 1.0). ICR, CCS, CCX, and CSD are heavily skewed. Shapiro-Wilk tests reject normality for all metrics (p < 0.001). Mann-Whitney U is the standard nonparametric alternative for comparing two independent groups under these conditions.

### Effect Size Interpretation

Rank-biserial correlation r ranges from -1 to +1:

| r range | Interpretation |
|---------|----------------|
| Positive r | Human systems rank higher (AI has more debt) |
| Negative r | AI systems rank higher (AI has less debt) |
| \|r\| < 0.1 | Negligible |
| 0.1 <= \|r\| < 0.3 | Small |
| 0.3 <= \|r\| < 0.5 | Medium |
| \|r\| >= 0.5 | Large |

### Multiple Comparisons

Ten metrics tested simultaneously. Bonferroni-corrected alpha = 0.005. All significant results in Table 5 achieve p < 10^-4. URR (p = 0.360) is the only non-significant result.

---

## Threshold Calibration

The 0.8 DRS threshold classifies systems as "deployment-ready."

1. **Sampling.** 30 repositories stratified across DRS bands (0.0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0).
2. **Manual labeling.** An author labeled each as "deployable with reasonable effort" (24 of 30 resolvable).
3. **ROC analysis.** AUC = 0.84. Youden's J maximized at DRS = 0.25 (sensitivity = 1.00, specificity = 0.78).
4. **Threshold selection.** 0.8 chosen as deliberately conservative (specificity = 0.89, sensitivity = 0.53), providing a sufficient but not necessary condition for readiness.
5. **Sensitivity.** Extreme bimodality (only 8 of 695 systems in [0.75, 0.95)) makes conclusions insensitive to threshold choice.

---

## ACDS Normalization Sensitivity

Level 3 debt uses domain-anchored caps rather than corpus-dependent normalization:

| Cap | Default | Aggressive | Lenient |
|-----|---------|------------|---------|
| kappa_CCX | 15 | 8 | 25 |
| kappa_CSD | 100 | 50 | 200 |
| kappa_SDD | 10 | 5 | 20 |

Under all three regimes: Spearman rho >= 0.96 for corpus-median rankings, maximum absolute corpus-median ACDS shift < 0.08, mean per-system shift < 0.01.

---

## LLM-as-Judge Protocol

Level 4 metrics assessed on 27 systems (17 AI-Python, 10 Multi-Agent DApps).

**Models:** GPT-4o (primary, 2 runs), Claude Haiku 4.5 (stability, 3 runs). Temperature 0.0. Distinct system-prompt paraphrase per run.

**Leakage control:** Prompts instruct "evaluate ONLY the source code supplied."

**Reliability:**

| Metric | GPT-4o alpha | Haiku alpha | Cross-model |
|--------|-------------|-------------|-------------|
| Defect density | 1.000 | 1.000 | Strong |
| Vulnerability density | >= 0.846 | 0.889 | Offset (~1.2 pts), rank preserved |
| Ownership void | 0.156-0.625 | Variable | rho = 0.50 |
| Spec alignment | Strong | Strong | rho = 0.74 (p = .015) |
| Deployment risk | 0.313 | -0.680 | Least reliable |

Density estimates are robust. Subjective governance metrics are ordinal indicators.

---

## Paradigm Definitions

| Paradigm | Definition | Inclusion Criteria | Corpora |
|----------|------------|--------------------|---------|
| **Fully Autonomous** | AI receives specification, produces complete output with no post-generation human editing | No human commits after generation; single pass | Multi-Agent DApps, Benchmark, AI-Python |
| **Platform-Backed** | Generated through tools providing scaffolding templates and architectural patterns | Platform scaffolding detectable in file structure | GPT-Engineer/Lovable/Bolt.new, v0.dev |
| **Human-Guided** | Human developers use AI assistants iteratively, maintaining architectural oversight | Evidence of iterative human-AI interaction; human makes integration decisions | Vibe-Coded, Vibe Platforms, AI Detection, Vibe Solidity |
| **Human Baseline** | Human-authored, no AI generation | No evidence of AI tool usage | Human Baseline |

Applied consistently across all corpora.

---

## Research Pipeline

### Run the Full Pipeline

```bash
python pipeline/run_all_experiments.py
```

### Individual Phases

```bash
# Level 1: Boundary Metrics (DRS, THI, APS, SID)
python pipeline/run_boundary_metrics.py --data-root data/ --results-dir results/

# Levels 2-3: Tier Metrics (ICR, CCS, URR, HD, CSD, CCX, DFR, DRD)
python pipeline/run_tier_metrics.py --data-root data/ --results-dir results/

# Security Scan (SDD)
python pipeline/run_security_scan.py --data-root data/ --results-dir results/

# Level 4: LLM-as-Judge
python pipeline/run_llm_judge.py --data-root data/ --results-dir results/ --subset ai_python,multi_agent
```

Results are written to `results/` with per-corpus and per-system breakdowns.

See [Dataset.md](Dataset.md) for full dataset documentation including collection criteria, corpus breakdowns, and pipeline applicability.
# AI Coder Debt

Measures technical debt in AI-generated software systems across four levels and
aggregates them into a composite score (ACDS).



| Level | Name | Debt formula |
|-------|------|--------------|
| L1 | System Existence | `1 - DRS` |
| L2 | System Coherence | `mean(1-ICR, 1-CCS, URR)` |
| L3 | Component Quality | `mean(CCX, CSD, SDD)` capped |
| L4 | Traceability | mean of 5 LLM-as-Judge metrics |
| ACDS | Composite | `1 - prod(1 - L)` |

Levels whose inputs are unavailable are reported as `unmeasured` and excluded
from ACDS rather than counted as zero debt.

## Install

```bash
pip install -e .            # or ".[maintainability]" for Level 3
```

## Usage

```bash
aicoder-debt score ./path/to/project              # per-level debt + ACDS
aicoder-debt score ./path/to/project --judge      # adds Level 4 (billed API calls)
aicoder-debt analyze ./path/to/project            # all metric tiers
aicoder-debt list-metrics                         # list available metrics
```

Export to a file:

```bash
aicoder-debt analyze ./path/to/project --format json -o report.json
aicoder-debt analyze ./path/to/project --format markdown -o report.md
aicoder-debt analyze ./path/to/project --format html -o report.html
```

Single metrics and the dependency graph:

```bash
aicoder-debt dfr ./project    # Deployment Feasibility Rate
aicoder-debt drd ./project    # Deployment Repair Distance
aicoder-debt id  ./project    # Illusion Depth
aicoder-debt icr ./project    # Interface Consistency Rate
aicoder-debt ccs ./project    # Configuration Coherence Score
aicoder-debt urr ./project    # Undefined Reference Rate
aicoder-debt hd  ./project    # Hallucination Density
aicoder-debt csd ./project    # Code Smell Density
aicoder-debt ccx ./project    # Cognitive Complexity Index

aicoder-debt extract-ddg ./project -o ddg.json
aicoder-debt ownership-signals ./project [--children]
```

`ownership-signals` reports whether a project carries the repository metadata
the Ownership Void Index is defined over (a `CODEOWNERS` entry, or history with
more than one distinct author).

### Flags

| Flag | Effect |
|------|--------|
| `--format table\|json\|markdown\|html` | Change output format |
| `-o FILE` | Write output to a file |
| `--skip-registry-check` | Skip PyPI/npm lookups (faster, offline) |
| `--skip-maintainability` | Skip Tier 4 metrics (faster) |
| `--verbose` | Show progress details |

## Example

```console
$ aicoder-debt score examples/checkout-flow
                              AI Coder Debt —
                         examples/checkout-flow
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Level ┃ Name              ┃       Debt ┃ Formula                         ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ L1    │ System Existence  │      0.000 │ 1 - DRS                         │
│ L2    │ System Coherence  │      0.278 │ mean(1-ICR, 1-CCS, URR)         │
│ L3    │ Component Quality │      0.071 │ mean(CCX, CSD, SDD) capped      │
│ L4    │ Traceability      │ unmeasured │ mean of 5 LLM-as-Judge metrics  │
│ ACDS  │ Composite         │      0.329 │ 1 - prod(1 - L) over 3 level(s) │
└───────┴───────────────────┴────────────┴─────────────────────────────────┘
Inputs: drs=1.000, icr=0.333, ccs=0.833, urr=0.000, ccx=2.120, csd=0.000
Unmeasured: sdd, llm_judge (excluded from ACDS, not counted as zero debt)
```

Here L1 and L3 are clean, and the tests pass. L2 catches the defect: `checkout`
calls `POST /payments/charge`, while `payments` defines `/payments/authorize`
and `/payments/refund`, so every checkout returns 502.

Sample systems live in [`examples/`](examples/):

```bash
for d in taskboard orders-api checkout-flow bookclub \
         ms-video-platform defi-lending voicetrade-schwab; do
  aicoder-debt score "examples/$d"
done
```

## Metrics

| Metric | Full Name | Level | What it measures |
|--------|-----------|-------|------------------|
| DRS | Deployment Readiness Score | L1 | Fraction of applicable deployment checks that pass |
| APS | Architectural Presence Score | L1 | 14 boolean architectural features; APS = 0 means absent architecture |
| THI | Template Homogeneity Index | L1 | Pairwise Jaccard similarity of file-tree fingerprints across systems |
| SID | System Integration Density | L1 | Cross-component edge density in the Deployment Dependency Graph |
| ICR | Interface Consistency Rate | L2 | Fraction of API calls matching an endpoint definition |
| CCS | Configuration Coherence Score | L2 | Fraction of config references resolving to defined values |
| URR | Undefined Reference Rate | L2 | Fraction of internal imports unresolvable in the project |
| HD | Hallucination Density | L2 | External imports not found on npm/PyPI, per KLOC |
| DFR | Deployment Feasibility Rate | L2 | Fraction of systems admitting a feasible deployment plan |
| DRD | Deployment Repair Distance | L2 | Minimal transformation cost to reach feasible deployment |
| CSD | Code Smell Density | L3 | Pylint/ESLint/Solhint issues, severity-weighted, per KLOC |
| CCX | Cognitive Complexity Index | L3 | Radon (Python) + tree-sitter (JS) average complexity |
| SDD | Security Debt Density | L3 | 60+ OWASP-aligned SAST patterns across five languages, per KLOC |
| Ownership Void Index | — | L4 | Fraction of modules with no assigned human owner (LLM-as-Judge) |
| Specification Alignment | — | L4 | Degree to which code fulfills stated requirements (LLM-as-Judge) |
| Defect / Vulnerability Density | — | L4 | Rubric-based estimation (LLM-as-Judge) |
| ID | Illusion Depth | Meta | Highest verification stage a system passes before failure |
| ACDS | AI Coder Debt Score | Composite | `1 - prod(1 - L_i)` across measured levels |

ICR, CCS, and URR use additive smoothing (k=1), so an empty input yields 0.0
rather than being undefined.

## Tests

```bash
pytest tests/
pytest tests/ -k "test_name"
```

## Research Pipeline

```bash
python pipeline/run_boundary_metrics.py --data-root data/ --results-dir results/  # DRS, THI, APS, SID
python pipeline/run_tier_metrics.py     --data-root data/ --results-dir results/  # ICR, CCS, URR, HD, CSD, CCX, DFR, DRD
python pipeline/run_security_scan.py                                              # SDD
python pipeline/run_dapp_audit.py                                                 # DApp corpus audit
python pipeline/regenerate_statistical_tests.py                                   # significance tests
```

Results are written to `results/` with per-corpus and per-system breakdowns.

## Further Reading

- [Dataset.md](Dataset.md) — dataset documentation, collection criteria, corpus breakdowns.
- [docs/METHODOLOGY.md](docs/METHODOLOGY.md) — DRS check catalog, failure-mode derivation, statistical methodology, threshold calibration, LLM-as-Judge protocol, paradigm definitions.

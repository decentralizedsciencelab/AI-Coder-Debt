# How to Run aicoder-debt

## 1. Install

```bash
cd aicoder-debt/
pip install -e .
```


## 2. Analyze a Project

```bash
aicoder-debt analyze ./path/to/project
```

This runs all five metric tiers and prints a summary table with the composite ACDS score.

## 3. Export Results

```bash
aicoder-debt analyze ./path/to/project --format json -o report.json
aicoder-debt analyze ./path/to/project --format markdown -o report.md
aicoder-debt analyze ./path/to/project --format html -o report.html
```

## 4. Run a Single Metric

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

## 5. Extract the Dependency Graph

```bash
aicoder-debt extract-ddg ./path/to/project
aicoder-debt extract-ddg ./path/to/project -o ddg.json
```

## 6. Useful Flags

| Flag | Effect |
|------|--------|
| `--format table\|json\|markdown\|html` | Change output format |
| `-o FILE` | Write output to a file |
| `--skip-registry-check` | Skip PyPI/npm lookups (faster, offline) |
| `--skip-maintainability` | Skip Tier 4 metrics (faster) |
| `--verbose` | Show progress details |

## 7. Run Tests

```bash
pytest tests/
pytest tests/ -k "test_name"
```

## 8. Run the Full Research Pipeline

```bash
python pipeline/run_all_experiments.py
```

Or individual phases:

```bash
python pipeline/run_tier_metrics.py --data-root data/ --results-dir results/
python pipeline/run_boundary_metrics.py --data-root data/ --results-dir results/
```
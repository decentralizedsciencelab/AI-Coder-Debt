# maker-dss — framework analysis

**MakerDAO DSS**, the core contract system of the Maker protocol: human-written,
audited, deployed, securing real value. From the Human Baseline corpus.

It is here for one reason: **the framework gives it the same composite debt
score as a six-file AI-generated stub.**

## Score

```
$ aicoder-debt score examples/maker-dss
│ L1    │ System Existence  │      0.000 │ 1 - DRS                         │
│ L2    │ System Coherence  │      0.667 │ mean(1-ICR, 1-CCS, URR)         │
│ L3    │ Component Quality │ unmeasured │ mean(CCX, CSD, SDD) capped      │
│ L4    │ Traceability      │ unmeasured │ mean of 5 LLM-as-Judge metrics  │
│ ACDS  │ Composite         │      0.667 │ 1 - prod(1 - L) over 2 level(s) │
Inputs: drs=1.000, icr=0.000, ccs=0.000, urr=0.000
```

`ACDS = 0.667`. [`../defi-lending/`](../defi-lending/) — an AI-generated
lending protocol of six flat files with no build config and no deploy script —
also scores **exactly 0.667**, by the same arithmetic: `L1 = 0`, `L2` pinned at
its additive-smoothing floor, `L3` unmeasured.

The composite cannot distinguish production MakerDAO from an AI stub. Any
reading of ACDS has to start there.

## What it does exercise, and nothing else here does

This is the only example that puts Tier 1 to work:

| | |
|---|---|
| DDG | **120 nodes, 939 edges** |
| edge types | 569 `STATE`, 51 `ADDR`, 319 `RUNTIME` |
| cycles | **7** |
| DFR | `REPAIRABLE` |
| DRD | **cost 10**, 7 edges to break |
| ID | stage 10 |

Seven deployment-ordering cycles, repaired at a cost of 10 by breaking seven
`STATE` edges. The six other real examples have zero cycles and `DRD = 0`, so
the cycle detection and greedy set-cover repair machinery is untested by them.

**Deployment cycles are not an AI failure mode in this corpus.** Of the 37
systems with a cycle and a non-zero repair distance, **36 are human** and one
is AI. Cycles track size and maturity: this system has 939 edges where the
median AI system has 20.

## Why DRS = 1.000 here

One applicable check of twelve: `no_placeholder_abi` passes and the other
eleven are marked not-applicable. Same vacuity as `defi-lending`, from the
opposite direction — there the tree was too sparse to check, here the project
does not ship the JavaScript/ABI artifacts the DApp checker looks for, because
it is a pure Solidity library built with its own tooling.

## Why L2 sits at its floor

`ICR`, `CCS` and `URR` all report `0/0` — no HTTP calls, no `os.getenv`/
`process.env` references, no internal module imports of the kind the
extractors recognise, because this is Solidity. `L2 = 0.667` is the floor for
"nothing measured", and it is the **only** contributor to the composite. The
0.667 is therefore a statement about the extractors, not about MakerDAO.

## What to take from it

Three caveats the paper needs, all visible in one system:

1. **DRS without its applicable-check count is uninterpretable** — 1.000 from
   one check.
2. **L2's floor is not a measurement** — and here it produces the entire
   composite.
3. **Cycles and size are confounded** — the metric that fires hardest on this
   system fires because it is large, not because it is bad.

## Reproducing

```bash
aicoder-debt score examples/maker-dss
aicoder-debt dfr   examples/maker-dss
aicoder-debt drd   examples/maker-dss
```

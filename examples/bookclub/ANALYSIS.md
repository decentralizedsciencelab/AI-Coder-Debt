# bookclub — framework analysis

A reading-group platform: a React/Vite SPA (`frontend/`), an Express+TypeScript
REST API with route modules (`backend/`), PostgreSQL with schema and seed data
(`database/`), and a background worker that closes expired votes (`worker/`),
wired by `docker-compose.yml` with per-component Dockerfiles.

Real AI output, **generated for this repository** with the benchmark's own
naive prompt — see [`PROVENANCE.md`](PROVENANCE.md). Its `README.md` is the
agent's output too.

This is the folder's **counter-example**. Every other real system here scores
between 0.667 and 0.957; this one scores 0.554, and it was produced from the
same naive prompt template. What differs is the generation method.

## Score

```
$ aicoder-debt score examples/bookclub
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Level ┃ Name              ┃       Debt ┃ Formula                         ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ L1    │ System Existence  │      0.333 │ 1 - DRS                         │
│ L2    │ System Coherence  │      0.190 │ mean(1-ICR, 1-CCS, URR)         │
│ L3    │ Component Quality │      0.174 │ mean(CCX, CSD, SDD) capped      │
│ L4    │ Traceability      │ unmeasured │ mean of 5 LLM-as-Judge metrics  │
│ ACDS  │ Composite         │      0.554 │ 1 - prod(1 - L) over 3 level(s) │
└───────┴───────────────────┴────────────┴─────────────────────────────────┘
Inputs: drs=0.667, icr=0.500, ccs=0.929, urr=0.000, ccx=0.684, csd=30.179
Unmeasured: sdd, llm_judge (excluded from ACDS, not counted as zero debt)
```

Supplying SDD (2.342/KLOC, 4 findings) gives L3 = 0.194 and ACDS = 0.565.
L4 was not estimated: LLM-as-Judge needs API calls, and this system was
generated deliberately without them.

## What it got right

| Metric | Value | |
|--------|-------|--|
| CCS | **0.929** (13/13) | every `process.env` reference resolves against compose and `.env` handling |
| URR | **0.000** (0/61) | every internal import resolves — no module is referenced that was not written |
| HD | **0.000** (0/25) | all 25 declared packages exist on npm |
| CCX | 0.684 over 209 functions | low complexity |
| CSD | 30.179 /KLOC | 37 ESLint findings over 1.226 KLOC |
| SDD | 2.342 /KLOC | 4 findings |

For comparison, `ms-video-platform` — a single-shot generation from the same
benchmark — has CCS 0.000, URR at its floor, and CSD 378.8/KLOC.

## What it got wrong

**`env_vars_defined` fails: `DATABASE_URL` and `PORT` are undefined.** That is
the same failure mode as [`taskboard`](../taskboard/): the compose file and
code reference configuration that no committed file supplies. DRS = 2/3.

**One deployment-ordering cycle.** The DDG holds 35 nodes and 41 edges
(35 `RUNTIME`, 5 `STATE`, 1 `ADDR`) with a single `STATE` self-edge on
`backend/src/db` (`backend/src/db.ts:6`, "connects via pg"). DFR is therefore
`REPAIRABLE` rather than `DEPLOYABLE`, and DRD = 2: the greedy set-cover
selects that one `STATE` edge, repaired by the SDB pattern.

That is the same shape as Vibelens's PostgreSQL self-edge, which suggests the
pattern survives a change of both model and generation method.

## Two numbers not to quote

**DRS = 0.667 comes from 3 applicable checks of 12.** Being TypeScript plus
Docker, it routes to the DApp checker where nine checks are Solidity- or
Python-specific. Two pass (`no_placeholder_abi`, `frontend_calls_backend`) and
one fails. Same caveat as `taskboard` and `defi-lending`: read DRS with its
applicable count.

**ICR = 0.500 is one call site, not a measurement.** `frontend/src/api.ts:11`
routes every request through a single `fetch(\`${API_URL}${path}\`, …)`
wrapper, with each endpoint passed in as `path`. The extractor sees one call
and matches it by wildcard, so twenty-odd logical calls are invisible. The
backend compounds it: routes are registered as `router.post('/register')` and
mounted under prefixes with `app.use`, so extracted endpoint paths lack their
prefixes. Both sides are wrong and agree by accident.

A centralized API client is the dominant modern frontend pattern, so ICR is
structurally blind to well-factored frontends. That is a limitation of the
metric, not a property of this system.

## Reproducing

```bash
aicoder-debt score examples/bookclub
```

L3 needs the `maintainability` extra, plus ESLint on `PATH` and
`configs/linter_configs/` and `tools/extractors/` present in the repository
root — without them CSD and CCX report `unmeasured` for JavaScript rather than
failing loudly.

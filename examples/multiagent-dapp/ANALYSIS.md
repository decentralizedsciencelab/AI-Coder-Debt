# multiagent-dapp — framework analysis

A DeFi DApp from the **Multi-Agent** corpus: Solidity contracts, a React
frontend, Hardhat-style tests, `.env` and `.env.example`, 32 files. Generated
by a multi-agent pipeline. See [`PROVENANCE.md`](PROVENANCE.md) -- this one
project stands in for 366, because they are near-clones.

Two things make it worth shipping: it is the **only example where the DApp
checker is fully exercised**, and it is the only one that demonstrates what
happens when a study's largest group is 365 copies of one system.

## Score

```
$ aicoder-debt score examples/multiagent-dapp
│ L1    │ System Existence  │      0.917 │ 1 - DRS                         │
│ L2    │ System Coherence  │      0.396 │ mean(1-ICR, 1-CCS, URR)         │
│ L3    │ Component Quality │ unmeasured │ mean(CCX, CSD, SDD) capped      │
│ L4    │ Traceability      │ unmeasured │ mean of 5 LLM-as-Judge metrics  │
│ ACDS  │ Composite         │      0.950 │ 1 - prod(1 - L) over 2 level(s) │
Inputs: drs=0.083, icr=0.000, ccs=0.812, urr=0.000
```

## DRS = 1/12 — the non-vacuous opposite of `defi-lending`

Every one of the twelve DApp boundary checks is **applicable**, and eleven
fail. No other example in this folder assesses more than three:

| Check | Result | Detail |
|-------|--------|--------|
| `imports_resolve` | ✅ | OK |
| `abi_exists` | ❌ | ABI has 0 entries |
| `abi_matches_contract` | ❌ | Jaccard = 0.000 (ABI: 0, Sol: 9) |
| `no_placeholder_abi` | ❌ | placeholder ABI detected |
| `frontend_calls_backend` | ❌ | frontend does **not** call the backend |
| `no_dead_backend_routes` | ❌ | backend routes exist that the frontend never calls |
| `env_vars_defined` | ❌ | 2 undefined: `CHAIN_ID`, `REACT_APP_DEFI_…` |
| `no_placeholder_addresses` | ❌ | 2 placeholder addresses |
| `no_port_conflicts` | ❌ | **both components bind port 3000** |
| `build_config_exists` | ❌ | no hardhat/truffle/foundry config |
| `deploy_script_exists` | ❌ | no deploy script |
| `tests_match_contract` | ❌ | contract-function coverage 0 |

This is the profile the paper's headline claim rests on, in one system: nine
Solidity contracts and a frontend that never calls them, an ABI with no
entries, placeholder addresses, both services on one port, and no way to build
or deploy any of it. `defi-lending` scores DRS **1.000** on one applicable
check; this scores **0.083** on twelve. Read together they show the metric is
sound and its denominator is everything.

## The measurement problem this example exists to expose

`L2 = 0.396` comes from `CCS = 0.812` and `URR = 0.000` -- and those are the
*same two numbers* in 365 of the 366 systems. So are the DDG counts. The group
contributes one observation, repeated.

That matters for §Statistical Methodology. The Mann--Whitney tests treat 366
near-identical systems as independent draws, which is pseudo-replication: it
inflates the effective sample size of the AI arm and, because the tied mass is
enormous, shrinks the tie-corrected variance and drives the *p*-values down.
The AI arm's effective size is closer to 230 independent systems than 595.

It also explains the shape of the aggregate results. Any AI-vs-Human contrast
computed over the pooled corpus is, at 61.5% weight, a contrast between *this
one template* and 100 mature repositories.

## Reproducing

```bash
aicoder-debt score   examples/multiagent-dapp
aicoder-debt analyze examples/multiagent-dapp   # full 12-check table
```

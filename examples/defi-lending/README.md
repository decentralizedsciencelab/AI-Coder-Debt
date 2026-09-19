# defi-lending

A Solidity lending protocol: `LendingPool` composed with `PriceOracle`,
`InterestModel`, and an ERC-20 `CollateralToken`, plus a `Controller` stub and a
`DEPLOYMENT_MANIFEST.md` describing deployment order.

Real LLM output, copied unmodified from the benchmark corpus — see
[`PROVENANCE.md`](PROVENANCE.md).

## Score

```
$ aicoder-debt score examples/defi-lending
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Level ┃ Name              ┃       Debt ┃ Formula                         ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ L1    │ System Existence  │      0.000 │ 1 - DRS                         │
│ L2    │ System Coherence  │      0.667 │ mean(1-ICR, 1-CCS, URR)         │
│ L3    │ Component Quality │ unmeasured │ mean(CCX, CSD, SDD) capped      │
│ L4    │ Traceability      │ unmeasured │ mean of 5 LLM-as-Judge metrics  │
│ ACDS  │ Composite         │      0.667 │ 1 - prod(1 - L) over 2 level(s) │
└───────┴───────────────────┴────────────┴─────────────────────────────────┘
Inputs: drs=1.000, icr=0.000, ccs=0.000, urr=0.000
Unmeasured: ccx, csd, sdd, llm_judge (excluded from ACDS, not counted as zero debt)
```

## Reading the result

DRS = 1.000 comes from **one** applicable check out of twelve. Three checks
failed — no ABI, no build config, no deploy script — and were excluded as
not-applicable, so none of it reaches the score. L1 debt is 0.000 for a system
that cannot be deployed.

L2 = 0.667 is the smoothing floor: the contracts contain no HTTP calls or config
references for those extractors to find. L3 is `unmeasured` — no analyzer covers
Solidity. The composite comes entirely from the level that measured nothing.

Do not read DRS without the applicable-check count. See [`ANALYSIS.md`](ANALYSIS.md)
for the full check table.

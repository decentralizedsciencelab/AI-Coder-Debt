# checkout-flow

A two-service Python system: `checkout` prices a cart and charges it through
`payments`, wired together by `docker-compose.yml`.

AI-generated fixture written for this repository, with no generation record.

Every applicable deployment check passes, the test suite passes, and the linter
is silent. It still cannot complete a checkout.

## Score

```
$ aicoder-debt score examples/checkout-flow
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

## The defect

`checkout` posts every charge to `/payments/charge`. The payments service
defines `/payments/authorize` and `/payments/refund` — never `/charge`. Every
checkout returns 502 while both health endpoints report healthy.

The tests pass because each suite mocks the boundary, so no test holds both
services at once. L2 is the only level that sees it (ICR 0.333), and the
multiplicative composite keeps it visible at ACDS 0.329 where a mean of the
three levels would report 0.116.

The route mismatch is the point of the fixture — do not "fix" it. See
[`ANALYSIS.md`](ANALYSIS.md) for the check-by-check breakdown, the test that
hides the bug, affected files, and maintenance notes.

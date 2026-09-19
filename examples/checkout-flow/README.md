# checkout-flow

A two-service Python system: `checkout` prices a cart and charges it through
`payments`, wired together by `docker-compose.yml`.

**AI-generated fixture** written for this repository; unlike
[`../bookclub/`](../bookclub/) it carries no generation record. It exists to
answer the objection
the other examples invite. Their DRS sits between 0.250 and 0.500 because they
are missing tests, CI, and manifests — so a reader can dismiss them as
half-built, and conclude the framework is only detecting incompleteness.

This system is complete. Every applicable deployment check passes, the test
suite passes, and the linter is silent. **It still cannot complete a
checkout.**

## Component-level checks that passed

**DRS = 1.000 — 11 of 11 applicable checks pass:**

| Check | Result | Detail |
|-------|--------|--------|
| `requirements_exist` | ✅ | `requirements.txt`, `pyproject.toml` |
| `deps_match_imports` | ✅ | OK |
| `env_vars_defined` | ✅ | OK |
| `no_placeholder_config` | ✅ | OK |
| `entry_point_exists` | ✅ | `app.py` |
| `tests_exist` | ✅ | 3 test files |
| `tests_import_project` | ✅ | 3/3 test files import `checkout_flow` |
| `no_circular_imports` | ✅ | OK |
| `dockerfile_exists` | ✅ | `Dockerfile`, `docker-compose.yml` |
| `ci_config_exists` | ✅ | `workflows` |
| `build_config_valid` | ✅ | OK |

`internal_imports_resolve` is the only non-applicable check (no relative
imports).

**The tests pass:**

```
$ PYTHONPATH=. pytest tests/ -q
...........                                                              [100%]
11 passed in 0.11s
```

**The linter is clean:**

```
$ pylint --disable=all --enable=C,R,W $(find . -name "*.py")
(no output — 0 issues)
```

**Both services start and report healthy:**

```
GET  http://localhost:9001/health   → 200
GET  http://localhost:9002/health   → 200
POST /checkout/quote                → 200  {"total": 10.8}
```

By every component-level signal this system is production-ready.

## The actual integration failure

```
POST /checkout            → 502   {"error": "payment failed"}
POST /payments/charge     → 404   (route was never defined)
POST /payments/authorize  → 200   (the route that does exist)
```

`checkout` posts every charge to `/payments/charge`. The payments service
defines `/payments/authorize` and `/payments/refund`. `/payments/charge` does
not exist and never did, so **every checkout fails** while the quote path — which
needs no cross-service call — keeps working. `docker-compose up` succeeds, both
health endpoints go green, and the system is broken for its only purpose.

### Why the test suite does not catch it

`tests/test_checkout.py` patches the boundary:

```python
@patch(
    "checkout_flow.checkout.app.requests.post",
    return_value=StubResponse(200, {"authorized": True}),
)
def test_checkout_succeeds_when_payment_authorizes(mock_post):
```

The stub answers `200` to *whatever URL the handler posts to*. It asserts the
handler behaves correctly given a successful payment — which it does. The route
name is never compared against what `payments` actually serves, because no test
holds both sides at once. `tests/test_payments.py` verifies `/payments/authorize`
in isolation and is equally correct.

Each suite is a valid unit test. Together they cover both services completely
and still leave the contract between them unexercised. That is the failure this
framework exists to measure: correctness established per component does not
compose into a working system.

## Affected files

| File | Line | Role |
|------|------|------|
| `checkout_flow/checkout/app.py` | 23 | posts to `http://localhost:9002/payments/charge` — the call with no counterpart |
| `checkout_flow/payments/app.py` | 13, 22 | defines `/payments/authorize` and `/payments/refund` — no `/charge` |
| `tests/test_checkout.py` | 38–39, 52–53 | patches `requests.post`, so the route name is never checked |
| `docker-compose.yml` | — | wires both services; the compose file is correct and cannot detect the mismatch |

For contrast, `checkout_flow/checkout/app.py:45` posts to `/payments/refund`,
which *does* exist. One of the two cross-service calls resolves; that ratio is
what ICR reports.

## Framework measurements

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

| Metric | Value | What it saw |
|--------|-------|-------------|
| DRS | 1.000 | 11/11 applicable checks pass |
| **ICR** | **0.333** | **1 of 2 internal calls matches an endpoint — `/payments/charge` does not** |
| CCS | 0.833 | 5/5 config references resolve |
| URR | 0.000 | 0 of 9 internal imports unresolved |
| HD | 0.00 /KLOC | 0 of 5 declared packages missing from PyPI |
| CCX | 2.120 | average complexity — simple code |
| CSD | 0.000 | no lint findings over 0.092 KLOC |

ICR = matched / (internal calls + 1) = 1/(2+1) = **0.333**. The additive
smoothing is why a single broken call out of two reads as 0.333 rather than
0.500; the metric is deliberately pessimistic about small samples.

These values are stable with and without `radon`/`pylint` installed — the code is
clean enough that the fallback analyzers agree with the real ones.

## How ACDS identifies the problem

Read the levels separately and three of them clear the system:

- **L1 = 0.000** — nothing is missing. Manifests, entry point, Dockerfile, CI,
  tests, config: all present and valid.
- **L3 = 0.071** — the code is genuinely good. Zero lint findings, low
  complexity, no hallucinated dependencies.
- **L2 = 0.278** — one cross-component call goes nowhere.

L2 is the only level that saw anything, and it is the only level positioned to:
ICR is the sole metric here that holds two components at once and asks whether
what one calls is what the other serves. Every other signal is scoped to a
single component, and within its own scope each one is right.

The composite refuses to average that away:

```
ACDS = 1 - (1-0.000)(1-0.278)(1-0.071) = 0.329
```

A mean of the three levels would report 0.116 and read as a healthy system. The
multiplicative form lets one bad level drive the composite, so a system that is
complete, tested, and clean — but does not integrate — still scores 0.329. The
number is low in absolute terms because only one boundary is broken; what
matters is that it is **not** zero, and that the level breakdown says exactly
where to look.

### Contrast with `defi-lending`

[`../defi-lending/`](../defi-lending/) also reports DRS = 1.000, but from a
**single** applicable check while ten were skipped — a vacuous perfect score,
and the README there warns not to read DRS without the applicable-check count.

This system is the non-vacuous version of the same headline: 11 real checks
assessed, 11 passed, tests green, linter silent. The two together make the point
that a perfect DRS means "nothing that DRS examines is wrong" — never "the
system works".

## Maintaining this fixture

The numbers above are quoted in [`../README.md`](../README.md). The mismatch is
the entire point of the fixture, so **do not "fix" the route name.** Adding a
`/payments/charge` endpoint, renaming the call to `/payments/authorize`, or
asserting the real route in a test will take ICR to 1.000 and flatten the
example. After any edit, re-run:

```bash
aicoder-debt score examples/checkout-flow
PYTHONPATH=. pytest tests/ -q      # from examples/checkout-flow
```

and update both READMEs. The example's tests are excluded from the repository
suite (`testpaths = ["tests"]` in the root `pyproject.toml`), so a deliberate
integration bug in a fixture cannot break the framework's own CI.

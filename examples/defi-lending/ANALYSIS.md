# defi-lending — analysis

Detail behind [`README.md`](README.md). Real LLM output, copied unmodified from
the benchmark corpus — see [`PROVENANCE.md`](PROVENANCE.md).

## DRS = 1.000 rests on a single check

Of the DApp checker's 12 boundary checks, 11 are not applicable and 1 applies:

| Check | Passed | Applicable | Detail |
|-------|--------|------------|--------|
| `no_placeholder_abi` | ✅ | **yes** | OK |
| `abi_exists` | ❌ | no | No ABI file found |
| `build_config_exists` | ❌ | no | No build config (hardhat/truffle/foundry) |
| `deploy_script_exists` | ❌ | no | No deploy script |
| `abi_matches_contract` | — | no | No contracts directory |
| `frontend_calls_backend` | — | no | No frontend+backend pair |
| `no_dead_backend_routes` | — | no | No frontend+backend pair |
| `env_vars_defined` | — | no | No `process.env` references |
| `no_placeholder_addresses` | — | no | No `.env` files |
| `no_port_conflicts` | — | no | No backend `app.js` |
| `imports_resolve` | — | no | No internal `require()` calls |
| `tests_match_contract` | — | no | No contracts or test directory |

DRS is the fraction of applicable checks that pass, so DRS = 1/1 = 1.000.

Three checks **failed and were still excluded**: `abi_exists`,
`build_config_exists`, and `deploy_script_exists`. A protocol with no build
configuration and no deploy script is not deployable, and the checker says so in
the `detail` column — but because each is marked not-applicable, none of it
reaches the score. L1 debt is 0.000 for a system that cannot be deployed.

Several exclusions are triggered by the shape of the extracted tree rather than
its content: `abi_matches_contract` and `tests_match_contract` both bail on "no
contracts directory", because extraction flattened the contracts to the root.
Two others (`build_config_exists`, `deploy_script_exists`) name files the model
did emit but extraction dropped — see [`PROVENANCE.md`](PROVENANCE.md).

Do not read DRS without the applicable-check count. A perfect DRS can mean
"everything passed" or, as here, "almost nothing was assessed".

## What the composite catches

L2 = 0.667 is itself the additive-smoothing floor rather than a measurement —
the Solidity contracts contain no HTTP calls or config references for those
extractors to find, so `icr`, `ccs`, and `urr` all report 0. L3 is `unmeasured`
because no analyzer covers Solidity.

So the reported ACDS of 0.667 comes entirely from a level that measured nothing,
while the level that did measure something reported zero debt. No single level
should be read on its own.

L3 previously reported `0.000` here — zero debt for contracts nothing had
examined. That is now fixed and reports `unmeasured`; see the fixed behaviours
in [`../README.md`](../README.md#known-framework-limitations). ACDS is unchanged
either way, because a level with zero debt contributes a factor of 1 to the
composite.

[`../checkout-flow/`](../checkout-flow/) is the non-vacuous version of the same
DRS = 1.000 headline: 11 real checks assessed, all passing.

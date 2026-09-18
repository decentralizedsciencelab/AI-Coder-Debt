# Provenance

This system was **generated for this repository** rather than collected from a
public corpus, using the benchmark's own naive prompt through a local coding
agent. The generation record sits beside the code, so nothing here depends on
an upstream URL that can disappear.

| Field | Value |
|-------|-------|
| Spec | `web-011` BookClub (see [`spec.json`](spec.json)) |
| Domain | web |
| Prompt variant | naive |
| Prompt source | `benchmark/prompts/naive.py :: _generate_web_naive_prompt`, verbatim |
| Runner | `codex exec` (codex-cli 0.147.0), `-s workspace-write --skip-git-repo-check` |
| Generated | 2026-09-18T19:07:10Z -- 19:27:57Z (1247 s) |
| Files | 53 generated |

Full record: [`metadata.json`](metadata.json) and [`spec.json`](spec.json),
which carry the spec, the exact prompt, the runner and its flags, timings, and
the list of generated files.

The complete agent transcript (9.0 MB, 2.0 MB compressed) is **not kept here**:
it accounted for more than half the size of the whole `examples/` tree, and
everything needed to identify what was generated and how is in
`metadata.json`. It is retained with the corresponding entry in the generation
corpus, `benchmark/outputs/web-011_codex-cli_naive/`. Ask if you want it
shipped alongside the example instead.

## One deviation from the benchmark prompt

The naive template ends "Provide complete, working code for all components."
That suits an API call returning a transcript; a CLI agent needs to be told
where to put things, so one line was appended:

> Write all files into the current working directory.

Nothing else was added. In particular no deployment guidance was given -- that
is what separates the naive variant from the structured one, and adding any
would have changed what the prompt measures.

## What the runner does that an API call does not

The model id is not recorded because the CLI selects it; the runner routes
through local Codex authentication, so no API key was used and no per-call
charge was incurred. More importantly the agent worked **agentically**: it
planned, wrote files, then ran its own type checks and fixed what they
surfaced. Its closing message reports that "the frontend, API, and worker
passed offline TypeScript checks" and that a container build was impossible
because the sandbox had no Docker binary and no registry access.

That self-verification is the most likely reason this system is the least
indebted real artifact in this folder, and it is why the comparison to the
single-shot `gpt-4-turbo` corpus entries is a comparison of *generation
methods*, not only of models.

## What was and was not kept

Everything the agent wrote is here. No dependency trees were installed --
the sandbox had no registry access -- so there is no `node_modules` to strip,
and every file is model-authored. The system's own `README.md` is its output
too, which is why the framework analysis lives in
[`ANALYSIS.md`](ANALYSIS.md).

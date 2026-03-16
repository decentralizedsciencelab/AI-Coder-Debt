# Dataset Documentation

## Overview

The evaluation employs two complementary datasets totaling 1,240 systems (1,140 AI-generated, 100 human-authored baselines) plus 536 single-file generations used for targeted metric evaluation.

## Dataset Summary

| Dataset | Scope | N | Purpose |
|---------|-------|---|---------|
| Dataset 1 | Benchmark completions | 545 | Context-sensitivity analysis |
| Dataset 2 | Multi-component systems | 695 | Four-level debt measurement |
| Single-file | Prompt-to-file outputs | 536 | APS and SID evaluation only |
| **Total** | | **1,776** | |

## Dataset 1: Benchmark Completions (N = 545)

Benchmark completions drawn from SWE-bench and EvoCodeBench, evaluating how context availability affects both functional correctness and system-level integration.

**Models (4):** GPT-4o, Claude 3.5 Sonnet, Qwen-7B, CodeLlama-34B. Selected to span the capacity spectrum from open-weight 7B models to frontier closed-source systems.

**Prompting Strategies (4):** Ranging from minimal context (signature and docstring only) to oracle access (full repository context).

## Dataset 2: Multi-Component Systems (N = 695)

Multi-component systems drawn from 10 corpora organized into three generation paradigms. All systems contain two or more components with detectable inter-component relationships or declared multi-service structure.

### Generation Paradigms

**Fully Autonomous (N = 503):** Generated with no post-generation human editing. The AI system receives a specification and produces the complete output without iterative human feedback.

| Corpus | N | Source | Languages | Domain |
|--------|---|--------|-----------|--------|
| Multi-Agent DApps | 366 | Multi-agent framework generations | Solidity, JavaScript | DeFi, blockchain |
| Benchmark | 120 | GPT-4-Turbo generations | Python, JavaScript | General software |
| AI-Python | 17 | Public AI-generated Python repositories | Python | Web, CLI, data science |

**Platform-Backed (N = 28):** Generated through tools that provide scaffolding templates, deployment configurations, and architectural patterns as part of the generation process.

| Corpus | N | Source | Languages | Domain |
|--------|---|--------|-----------|--------|
| GPT-Engineer/Lovable/Bolt.new | 21 | Platform-generated applications | TypeScript, JavaScript | Web applications |
| v0.dev | 7 | Vercel v0.dev generations | TypeScript, React | Frontend, full-stack |

**Human-Guided (N = 64):** Iterative AI-assisted development where human developers use AI tools as coding assistants, maintaining architectural oversight and making integration decisions.

| Corpus | N | Source | Languages | Domain |
|--------|---|--------|-----------|--------|
| Vibe-Coded | 47 | Curated vibe-coding projects | 12 languages, 15 AI tools | Diverse |
| Vibe Platforms | 10 | Larger vibe-coded platforms | TypeScript, Python | SaaS, developer tools |
| AI Detection | 5 | AI detection tool projects | Python, JavaScript | ML, classification |
| Vibe Solidity | 2 | Vibe-coded blockchain projects | Solidity | DeFi |

**Human Baseline (N = 100):** Human-authored open-source projects with no AI-assisted generation, selected for comparable scope to AI-generated systems (single-purpose applications, not frameworks or libraries).

| Property | Detail |
|----------|--------|
| Primary language | Python (~60%) |
| Secondary languages | JavaScript, Go, Solidity |
| Domains | Web, CLI, data science, DevOps |
| Selection criteria | Single-purpose applications, active repositories, comparable component count range |
| Median DDG nodes | 1,528 |

## Single-File Generations (N = 536)

Used exclusively for Architectural Presence Score (APS) and System Integration Density (SID) evaluation, as these systems lack the multi-component structure required for boundary metrics (DRS, THI) and coherence metrics (ICR, CCS).

| Subset | N | Source |
|--------|---|--------|
| Claude + GPT-4o prompt-to-file | 200 | Direct prompt-to-code generation |
| Extracted single-file systems | 336 | Single-file extractions from multi-component corpora |

## Pipeline Applicability

Not all corpora are evaluated by all pipelines. The table below clarifies which N appears in which analysis.

| Pipeline | Scope | N |
|----------|-------|---|-----------------|
| Boundary Metrics (Level 1) | Dataset 2 | 695 | 
| Tier Metrics (Levels 2-3) | Dataset 2 | 695 | 
| Security Scan (SAST) | SAST-applicable corpora from Dataset 2 | 209 |
| LLM-as-Judge (Level 4) | AI-Python + Multi-Agent DApps subset | 27 | 
| APS/SID | Single-file generations | 536 | 
| Statistical Tests | Dataset 2 AI systems vs. Human Baseline | 595 vs. 100 | 

## Collection Process

**AI corpora** were collected from three sources: (1) public GitHub repositories identified through topic tags, organization pages, and curated awesome-lists for each generation paradigm, (2) direct generation using platform tools (GPT-Engineer, Lovable, Bolt.new, v0.dev) with standardized application specifications, and (3) curated vibe-coding projects identified through developer communities and social media documentation of AI-assisted development workflows.

**Human baseline** projects were selected from open-source repositories meeting four criteria: (1) single-purpose application (not a framework, library, or plugin), (2) multi-component structure with at least two distinct services or deployment targets, (3) active maintenance within the past 12 months, and (4) no evidence of AI-assisted generation in commit history or documentation. Projects were stratified across four domains (web, CLI, data science, DevOps) to match the domain distribution of AI-generated corpora.

**Inclusion criteria for all corpora:** (1) repository contains parseable source code in a supported language (Python, JavaScript/TypeScript, Solidity, Go), (2) repository is publicly accessible, (3) repository is not a fork or duplicate of another included repository.

**Exclusion criteria:** (1) tutorial or educational repositories with no functional purpose, (2) repositories containing only configuration or documentation, (3) repositories with fewer than 3 source files.
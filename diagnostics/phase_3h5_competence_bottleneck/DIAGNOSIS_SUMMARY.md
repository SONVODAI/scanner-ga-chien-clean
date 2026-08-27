# Phase 3H.5 — Competence-to-Action Bottleneck Diagnosis

**Status:** FROZEN — diagnosis only, no research behavior changes.

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3h5-competence-bottleneck-aad2` |
| BB09 session | `bb09-autonomous-001` |
| Frozen research | `0df4597b2` |
| Artifacts | `diagnostics/phase_3h5_competence_bottleneck/artifacts/` |

## Executive Summary

BB09 showed the researcher **understands** what investigation is needed and **can construct** appropriate experiments, but **planner valuation systematically favors** horizon/partition/threshold reframing over competence-matched decomposition and falsification candidates.

Phase 3H.4 competence is **audit-only** — it did not change candidate generation, filtering, scoring, or selection. This explains identical aggregate behavior vs BB08.

## Four Required Questions

| Question | Answer |
|----------|--------|
| Q1 — Does Bot understand what research it needs? | **YES** |
| Q2 — Can Bot translate need into experiment? | **YES** |
| Q3 — Does valuation select appropriately? | **PARTIAL** |
| Q4 — Why no BB09 improvement vs BB08? | Competence is observational; grammar already emits same gap-driven candidates; planner/ERV unchanged |

## Verdict

| Field | Value |
|-------|-------|
| Diagnosis confidence | **HIGH** |
| Primary bottleneck | **B7 — Planner Valuation** |
| Secondary bottleneck | **B10 — Branch-Depth / Saturation** |

## Problem Classification (A/B/C)

| Problem | Dominates? |
|---------|------------|
| A — Doesn't know what to investigate | **No** |
| B — Knows but can't create experiment | **No** (minor B5 for inferred needs without grammar templates) |
| C — Creates but doesn't choose | **Yes** |

## Recommended Next Phase

**Phase 3H.6 — Valuation bridge:** connect competence-identified research needs to planner/ERV inputs so scientifically relevant candidates are not dominated by `search_complexity_penalty` on decomposition tools. Do not expand grammar or competence mappings first.

## What NOT to Change

- Competence inference
- Operational Awareness
- Global Allocator
- Exposure governance
- Experiment identity / dedup

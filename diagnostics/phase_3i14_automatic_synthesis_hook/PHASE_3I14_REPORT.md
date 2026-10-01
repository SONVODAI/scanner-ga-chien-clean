# Phase 3I.14 — Automatic Lifecycle Synthesis Hook

**Verdict:** `AUTOMATIC_SYNTHESIS_HOOK_PASS`  
**Hook version:** `lifecycle_synthesis_hook_v1_3i14`  
**Engine hash:** `ee00da71…` (unchanged)

No new experiment. `ResearchPriorityDecision → ACTION_RECORDED_ONLY → STOP`.

---

## Summary

Evidence synthesis is now an **automatic consequence** of completed epistemic updates in production lifecycle runners via `on_epistemic_update_completed()`.

## Lifecycle entry points

| Path | Class | Hooked |
|------|-------|--------|
| `run_minimal_lifecycle()` | PRODUCTION_LIFECYCLE | Yes |
| `run_one_shot_falsification_execution()` | RESEARCH_EXECUTION | Yes |
| `real_ledger_adapter` | DIAGNOSTIC_ONLY | No |
| BB fixtures / direct synthesis calls | TEST_ONLY | No |

## Source of authority

| Question | Authoritative record |
|----------|-------------------|
| Single ToolResult interpretation | `EpistemicUpdateRecord` |
| Current proposition knowledge | `EvidenceSynthesisRecord` |
| Next research-budget recommendation | `ResearchPriorityDecision` |
| Immediate single-evidence advice | `ResearchDecisionRecord` (transitional; does **not** override priority) |

## Real replay (frozen, no execution)

| | T1 (EPU1) | T2 (EPU1+EPU2) |
|--|-----------|----------------|
| State | SUPPORTED | SUPPORTED |
| Priority | SEEK_FALSIFICATION | SEEK_FALSIFICATION |
| 3I.13 equivalent | Yes | Yes |
| E2 relationship | — | PARTIAL_REPLICATION |

## Tests

**124 passed** (includes 3I.7–3I.14 regression).

## Proposed next phase

**Phase 3I.15** — Research orchestration layer that *reads* `ResearchPriorityDecision` under explicit human/policy gates (still no auto-experiment).

---

## Final answers A–D

**A.** Is synthesis now automatic in the normal lifecycle? **Yes.**

**B.** Can a valid EPU survive synthesis failure? **Yes** — failure isolated; EPU preserved.

**C.** When immediate vs multi-evidence conflict? **`ResearchPriorityDecision` is authoritative.**

**D.** Does lifecycle stop before next experiment? **Yes** — `ACTION_RECORDED_ONLY`.

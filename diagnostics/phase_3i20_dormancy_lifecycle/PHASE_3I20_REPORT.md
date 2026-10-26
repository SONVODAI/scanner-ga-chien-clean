# Phase 3I.20 — Automatic Research Dormancy & Reopening Lifecycle Integration

## Verdict: `DORMANCY_LIFECYCLE_INTEGRATION_PASS`

**Execution status:** `NOT_EXECUTED` — no experiment, no ToolResult, no deployment.

---

## 1. Branch / HEAD / PR

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3i20-dormancy-lifecycle-aad2` |
| Base | `main` (includes accepted 3I.19) |

---

## 2. Mode

**IMPLEMENTATION + INTEGRATION + REPLAY AUDIT**

---

## 3. Files changed

| File | Role |
|------|------|
| `lifecycle_dormancy_integration.py` | Canonical hooks, ResearchOpportunityState, pipeline |
| `lifecycle_synthesis_hook.py` | Extended LifecycleKnowledgeState + authority declarations |
| `dormancy_records.py` | ReopeningEvaluationRecord, ResearchActivityTransition |
| `bb_dormancy_lifecycle_01_fixtures.py` | BB-DormancyLifecycle-01 (20 cases) |
| `dormancy_audit.py` | Lifecycle integration leakage audit |
| `diagnostics/phase_3i20_dormancy_lifecycle/` | Runner + artifacts |
| `tests/test_edge_research_opr_phase_3i20.py` | Integration tests |

---

## 4. Frozen scientific hash verification

| Component | Status |
|-----------|--------|
| Synthesis engine | `ee00da71…` unchanged |
| Dormancy module (3I.19) | `a6a70005…` unchanged |
| Frontier reassessor | unchanged |
| Integration hash (3I.20) | `409f55fd…` |

---

## 5. Authoritative lifecycle records

```
PropositionRecord → scientific identity
EpistemicUpdateRecord → single experiment interpretation
EvidenceSynthesisRecord → body-of-evidence knowledge
ResearchPriorityDecision → research-budget recommendation
ScientificFrontierAssessment → information frontier
ResearchDormancyRecord → why research is inactive
ReopeningEvaluationRecord → response to opportunity change
```

`ResearchDecisionRecord` does not override multi-evidence state.

---

## 6. Dormancy hook

`on_scientific_frontier_completed()` — downstream of frontier assessment.

- Triggers on `NO_HIGH_INFORMATION_ACTION` / `HOLD_PROVISIONALLY`
- Idempotent via `(synthesis_hash, frontier_hash)` key
- Append-only, failure-isolated
- No epistemic mutation

---

## 7. ResearchMemoryLedger integration

`LifecycleKnowledgeState` extended with:

- `frontier_history`, `dormancy_history`, `reopening_history`
- `research_activity_state` (ACTIVE / DORMANT / REOPEN_CANDIDATE)
- `_dormancy_idempotency_keys`, `_opportunity_hashes_seen`
- `reconstruct_authoritative_state()` for session bootstrap

---

## 8. ResearchOpportunityState

Pre-result structure only: overlap, operators, executability, semantic continuity flags.

Forbidden: profitability, ToolResult, Zone C, human "look again" signals.

Deterministic `content_hash()` for material-change gate.

---

## 9. Reopening hook

`on_research_opportunity_state_changed()` — dormant propositions only.

Uses **frozen** DormancyRecord conditions (no re-derivation).

Outputs: `REMAIN_DORMANT | REOPEN_RESEARCH | NEW_PROPOSITION_REQUIRED | INSUFFICIENT_EVIDENCE`

`REOPEN_RESEARCH` → activity state `REOPEN_CANDIDATE` — **STOP**, no experiment.

---

## 10–14. Gates, anti-thrashing, terminal states

- Equivalent opportunity hash → skip evaluation
- Duplicate trigger fingerprint dedup (3I.19)
- FALSIFIED/ABANDONED → terminal precedence, no reopen
- CONFLICTED → evaluated via frozen conditions, not hardcoded reopen
- Malformed/stale lineage → FAILED, no fabricated decision

---

## 17–18. Benchmarks

- **BB-Dormancy-01 regression:** 20/20 pass (unchanged)
- **BB-DormancyLifecycle-01:** 20/20 pass

---

## 19. Counterfactuals CF-L1–L8

All passed.

---

## 20. Freeze hashes

See `artifacts/04_t2_lifecycle_replay.json`

---

## 21. Real T2 replay

| Field | Value |
|-------|-------|
| epistemic_state | **SUPPORTED** |
| frontier_decision | **NO_HIGH_INFORMATION_ACTION** |
| research_activity_state | **DORMANT** |
| dormancy_hash | `a09db7b6868d11134836ecec419f8a626d1835795469d43f7c20f14b2bc15dc3` |

Derived through integrated lifecycle — not manually inserted.

---

## 22. Synthetic opportunity demonstrations

| Demo | Outcome |
|------|---------|
| A. Redundant data | REMAIN_DORMANT |
| B. Independent structure | REOPEN_RESEARCH |
| C. Relevant capability | REOPEN_RESEARCH |
| D. Irrelevant capability | REMAIN_DORMANT |
| E. Semantic drift | NEW_PROPOSITION_REQUIRED |

---

## 23. Learning-vs-answer audit

**PASS** — no market regime, clock, row count, or T2-specific reopen rules in integration code.

---

## 24. Verdict

**`DORMANCY_LIFECYCLE_INTEGRATION_PASS`**

---

## 25–26. Gap + next phase

None for PASS.

**Phase 3I.21 — Research Resume Orchestration:** consume `REOPEN_CANDIDATE` to re-enter frontier assessment without auto-execution.

---

## 27. Confirmation

**NO EXPERIMENT EXECUTED. NO TOOLRESULT. NO DEPLOYMENT.**

---

## Final answers A–E

| Q | Answer |
|---|--------|
| **A.** Auto dormancy on exhausted research? | **Yes** — pipeline creates DormancyRecord on `NO_HIGH_INFORMATION_ACTION` |
| **B.** Future sessions reconstruct why dormant? | **Yes** — `reconstruct_authoritative_state()` + append-only history |
| **C.** Material opportunity triggers reopening automatically? | **Yes** — `on_research_opportunity_state_changed()` |
| **D.** Redundant change leaves dormant without thrashing? | **Yes** — opportunity hash dedup + CF-L3 |
| **E.** Reopening STOPs before action generation? | **Yes** — REOPEN_CANDIDATE only, no experiment |

**STOP.**

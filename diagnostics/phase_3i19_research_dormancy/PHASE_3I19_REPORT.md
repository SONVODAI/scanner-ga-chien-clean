# Phase 3I.19 — Autonomous Research Dormancy & Reopening Readiness

## Verdict: `AUTONOMOUS_RESEARCH_DORMANCY_PASS`

**Execution status:** `NOT_EXECUTED` — no experiment run, no ToolResult read, no future trigger simulated.

---

## 1. Branch / HEAD / PR

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3i19-research-dormancy-aad2` |
| Base | `main` (includes accepted 3I.18) |
| PR | opened on push |

---

## 2. Mode

**AUDIT + DESIGN** with minimal general mechanism implementation.

- No market experiment
- No future ToolResult
- No trading integration
- No deployment
- Reopening stops at `REOPEN_RESEARCH` — no experiment generation

---

## 3. Frozen lineage integrity

| Artifact | Status |
|----------|--------|
| PropositionRecord | Unchanged |
| E1/E2 | Unchanged |
| EpistemicUpdateRecords | Unchanged |
| EvidenceSynthesisRecord / engine | Unchanged hash `ee00da71…` |
| ResearchPriorityDecision | Unchanged |
| 3I.17b `NO_DEFENSIBLE_COHORT` | Preserved as constraint |
| 3I.18 frontier assessment | Preserved — T2 still `NO_HIGH_INFORMATION_ACTION` |
| ScientificActionGenerator | Unchanged |
| Cohort binder | Unchanged |
| Frontier reassessor | Unchanged |
| Historical packages | Unchanged; all `NOT_EXECUTED` |

Epistemic state: **SUPPORTED** (unchanged by dormancy).  
Frontier decision: **NO_HIGH_INFORMATION_ACTION** (preserved).

---

## 4. Existing dormancy capability audit (pre-3I.19)

| Concept | Pre-existing? | Location |
|---------|---------------|----------|
| `HOLD_PROVISIONALLY` | Yes — priority-level hold | `ResearchPriorityAction` |
| `NO_HIGH_INFORMATION_ACTION` | Yes — action/frontier silence | 3I.16 / 3I.18 |
| `silence_rationale` | Yes — diagnostic prose | `FrontierReassessmentResult` |
| Research activity state | **No** | — |
| DormancyRecord | **No** | — |
| Reopening conditions | **No** (prose only in 3I.18 report) | — |
| Reopening evaluator | **No** | — |
| Cross-session research memory | **No** | — |

**Distinction enforced:**

| Term | Meaning |
|------|---------|
| `SUPPORTED` | Epistemic belief state |
| `UNRESOLVED` | Uncertainty still listed in synthesis |
| `NO_HIGH_INFORMATION_ACTION` | Frontier decision — no justified next experiment |
| `HOLD_PROVISIONALLY` | Priority recommendation — provisional knowledge |
| `DORMANT` | **Research activity state** — budget inactive, proposition alive |
| `FALSIFIED` / `ABANDONED` | Epistemic terminal states — separate from dormancy |

---

## 5. Research-activity state model

```
ACTIVE  →  research budget justified (frontier has high-information action)
DORMANT →  proposition epistemically alive, research budget inactive
```

Reopening evaluator outputs (not activity states):
- `REMAIN_DORMANT`
- `REOPEN_RESEARCH`
- `NEW_PROPOSITION_REQUIRED`
- `INSUFFICIENT_EVIDENCE`

Dormancy does **not** mean: true, false, abandoned, uncertainty disappeared, or future investigation forbidden.

---

## 6. DormancyRecord

Append-only `ResearchDormancyRecord` in `dormancy_records.py`:

- proposition_id / hash
- synthesis_hash, frontier_assessment_hash
- epistemic_state_at_dormancy
- research_activity_state = `DORMANT`
- unresolved_uncertainties, blocked_axes, redundant_axes
- dormancy_reason, evidence_coverage, independence_limitations
- reopening_conditions (structured)
- forbidden_reopening_triggers
- deterministic record_hash

Derived by `derive_dormancy_record()` when frontier ∈ `{NO_HIGH_INFORMATION_ACTION, HOLD_PROVISIONALLY}`.

---

## 7. ReopeningConditionRecord

Structured conditions with:

- target_uncertainty
- blocking_reason (`COHORT_INDEPENDENCE_DEFICIT`, `CAPABILITY_GAP`, `AXIS_SATURATED`, `MARGINAL_INFORMATION_GATE`, …)
- required_scientific_change
- measurable pre-result criterion (overlap ceiling, operator relevance, …)
- independence requirement
- does_not_qualify list
- provenance from frontier/binder assessment
- deterministic hash

---

## 8. Evidence-derived reopening logic

Reopening requirements derived from:

```
unresolved uncertainty
+ why actions unavailable/low-information
+ evidence coverage
+ independence deficits (max_cohort_overlap, ledger fingerprints)
```

**Not** from human market expectations. Generic transformation example:

```
blocked: cohort overlap too strong (3I.17b NO_DEFENSIBLE_COHORT)
→ reopening requires measured row_overlap < 0.5 AND relation ≠ subset
```

---

## 9. Scientific continuity gate

`DormantResearchReopeningEvaluator` returns `NEW_PROPOSITION_REQUIRED` when opportunity changes:

- feature, outcome, horizon, population claim, or proposition_hash

Prevents dormant propositions becoming containers for arbitrary future ideas.

---

## 10. Independence-based reopening

Uses 3I.17b overlap framework conceptually:

- `new label ≠ new information` — context rename without overlap improvement rejected
- `later date ≠ automatically independent` — row count alone rejected
- Measured `new_evidence_overlap` compared to stored ceiling (0.5, generic not T2-tuned)

---

## 11. Capability-change reopening

```
new capability AND relevant unresolved uncertainty AND non-redundant path → REOPEN
```

Operator→axis mapping is structural (not preference). Irrelevant tools do not reopen.

---

## 12. Data-growth audit

No `N new days → reopen` rule.

Additional rows with overlap ≥ 0.95 → `REMAIN_DORMANT`.  
Only material independence improvement or relevant capability change qualifies.

---

## 13. Reopening evaluator

`DormantResearchReopeningEvaluator`:

**Inputs:** DormancyRecord, CurrentResearchSnapshot, ResearchOpportunityDescriptor (structured, not outcomes)

**Outputs:** exactly one of `REMAIN_DORMANT | REOPEN_RESEARCH | NEW_PROPOSITION_REQUIRED | INSUFFICIENT_EVIDENCE`

---

## 14. Anti-thrashing

- `ResearchMemoryLedger.seen_trigger_fingerprints` deduplicates equivalent triggers
- Clock elapsed alone → forbidden (`CLOCK_ELAPSED`)
- BBD-18: second identical trigger → `REMAIN_DORMANT`

---

## 15. Research-memory persistence

`ResearchMemoryLedger` — append-only dormancy + evaluation history, generalizes to many propositions. Not auto-wired into lifecycle hook this phase (audit recommendation only).

---

## 16. Multi-proposition generalization

No privilege for oldest/newest/T2/highest-return. Evaluator keyed by proposition_id + dormancy record hash.

---

## 17. BB-Dormancy-01 results

**20/20 passed** — see `artifacts/01_bb_dormancy_01.json`

---

## 18. Counterfactual results

All passed — see `artifacts/02_counterfactuals.json`

| CF | Expected | Result |
|----|----------|--------|
| CF-D1 | 100% overlapping evidence → REMAIN_DORMANT | Pass |
| CF-D2 | Independent opportunity → REOPEN | Pass |
| CF-D3 | Rename only → unchanged | Pass |
| CF-D4 | Unrelated tool → unchanged | Pass |
| CF-D5 | Relevant operator → may reopen | Pass |
| CF-D6 | Resolved uncertainty → condition withdrawn | Pass |
| CF-D7 | Semantics change → NEW_PROPOSITION_REQUIRED | Pass |
| CF-D8 | Order reversal → same result | Pass |

---

## 19. Freeze hashes

| Artifact | Hash |
|----------|------|
| Synthesis engine (unchanged) | `ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a` |
| Frontier reassessor (unchanged) | `bd0c4a0231bced2518f3e2febbe8ffc376154cb40f9c1a98c5c30cc30bc0834b` |
| Dormancy module (3I.19) | `a6a70005511d5894ec0fbcead9ad5b4589ce3162cbe01b7c761a12026b9adfa6` |

---

## 20. Real T2 dormancy diagnostic

| Field | Value |
|-------|-------|
| Should enter dormancy | **Yes** |
| Research activity state | **DORMANT** |
| Epistemic state | **SUPPORTED** (unchanged) |
| Frontier decision | **NO_HIGH_INFORMATION_ACTION** (preserved) |
| Dormancy trigger | `NO_HIGH_INFORMATION_ACTION` |
| Independence limitation | `max_cohort_overlap=0.9767` |

Full record: `artifacts/03_t2_dormancy_diagnostic.json`

---

## 21. Real T2 reopening requirements (qualifying)

1. **Major axes** (temporal, population, horizon, effect, regime): `MATERIAL_INDEPENDENCE_IMPROVEMENT` — measured row overlap < 0.5, not subset of prior ledger
2. **Counterexample/alternative**: `NEW_RELEVANT_OPERATOR` — non-cohort counterexample capability intersecting unresolved axis
3. **Marginal-information gate**: must address major unresolved bundle with non-redundant path

All derived from frozen frontier + binder — not hardcoded market waits.

---

## 22. Non-qualifying future changes

Forbidden triggers stored on record:

- Outcome profitability / future return magnitude
- Zone C match / known hidden edge
- Human review request
- Label rename only / row count only / clock elapsed
- Subgroup outcome mining

T2-specific temptations **not** hardcoded (e.g., no "wait for crash/regime/X days").

---

## 23. Lifecycle integration recommendation

Dormancy **should** become authoritative downstream of `NO_HIGH_INFORMATION_ACTION`, but is **not auto-wired** in this phase. Epistemic state must not change when research becomes dormant. Recommend wiring in Phase 3I.20.

---

## 24. Learning-vs-answer audit

**PASS** — no human rule specifying future market events, regimes, or profitable outcomes to wait for.

---

## 25. Verdict

**`AUTONOMOUS_RESEARCH_DORMANCY_PASS`**

---

## 26. Remaining gap

None for PASS.

---

## 27. Minimal next phase

**Phase 3I.20 — Lifecycle Dormancy Integration**

Append `ResearchDormancyRecord` to `LifecycleKnowledgeState` when frontier returns silence; expose reopening evaluation on new evidence/capability events.

---

## 28. Explicit confirmation

**NO EXPERIMENT EXECUTED. NO TOOLRESULT ACCESSED. NO FUTURE MARKET OUTCOME SIMULATED.**

---

## Final answers A–E

| Question | Answer |
|----------|--------|
| **A.** Know when to stop researching without abandoning? | **Yes** — `DORMANT` when `NO_HIGH_INFORMATION_ACTION`; epistemic state preserved |
| **B.** Remember why it stopped? | **Yes** — `ResearchDormancyRecord` with reason, blocked axes, independence limits |
| **C.** Determine what future opportunity would justify reopening? | **Yes** — structured `ReopeningConditionRecord` per blocking reason |
| **D.** Redundant new data leaves dormant? | **Yes** — CF-D1/D3, BBD-02/03/05/15 |
| **E.** Distinguish reopen vs new proposition? | **Yes** — `NEW_PROPOSITION_REQUIRED` on semantic change (CF-D7, BBD-09) |

**STOP.**

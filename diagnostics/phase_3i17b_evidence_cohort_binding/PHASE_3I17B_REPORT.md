# Phase 3I.17b — Evidence-Derived Cohort Binding

## Verdict: `EVIDENCE_DERIVED_COHORT_BINDING_PASS`

**Execution status:** `NOT_EXECUTED` — no experiment run, no ToolResult read.

---

## 1. Branch / HEAD / PR

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3i17b-evidence-cohort-binding-aad2` |
| Base | `main` |
| Historical 3I.16 core hash | `efe9abd43ea9a8fbae86a69ea3648adefe83f955df34fafb61cc9221ed1a712f` (unchanged) |
| Binder content hash | `cfaf175de409fd2e893497bc8f68d4a6ddc081b3b17158e4dfd9c266ca788b51` |

---

## 2. Files changed

| File | Role |
|------|------|
| `modules/edge_research/opr_bridge/cohort_binding_records.py` | `CohortCandidateRecord`, overlap/independence record types |
| `modules/edge_research/opr_bridge/cohort_overlap_estimator.py` | Pre-result overlap estimator (no outcome columns) |
| `modules/edge_research/opr_bridge/evidence_derived_cohort_binder.py` | **EvidenceDerivedCohortBinder** — generate, evaluate, rank, silence |
| `modules/edge_research/opr_bridge/bb_cohort_01_fixtures.py` | BB-Cohort-01 (18 pre-registered cases) |
| `modules/edge_research/opr_bridge/scientific_action_executability.py` | Removed hardcoded `NORMAL`/`STRESS`; requires evidence-derived `population_spec` |
| `modules/edge_research/opr_bridge/scientific_action_operators.py` | Integrates binder; evidence-computed independence profiles |
| `modules/edge_research/opr_bridge/evidence_ledger_builder.py` | Adds pre-result `experiment_spec` reference to evidence specs |
| `tests/test_edge_research_opr_phase_3i17b.py` | BB-Cohort-01 + leakage + counterfactual tests |
| `diagnostics/phase_3i17b_evidence_cohort_binding/run_phase_3i17b.py` | Diagnostic runner |

---

## 3. Frozen scientific inputs (preserved)

- PropositionRecord — unchanged
- E1 / E2 ledger — unchanged content; specs enriched with pre-result `experiment_spec` structure only
- EvidenceSynthesisRecord — unchanged engine hash `ee00da71…`
- ResearchPriorityDecision — unchanged rules
- 3I.16 generator — preserved; historical package `NOT_EXECUTED`
- 3I.17 audit artifacts — preserved

---

## 4. Leakage audit

- No `t5_return` or outcome columns used in cohort selection
- No ToolResult access
- No Zone C / hidden edges
- BBC-16 explicitly tests outcome-leakage prohibition
- Binder reads panel metadata only (`trade_date`, `symbol`, `research_market_state`)

---

## 5. Old hardcoded binding audit

**Removed from `scientific_action_executability._population_for_strategy`:**
- `research_market_state in [NORMAL]` for `population_subgroup_contrast`
- `research_market_state in [STRESS]` for `regime_separated_contrast`

These strategies now **raise** if called without evidence-derived `population_spec_override`.

**Removed from `scientific_action_operators._independence_estimate`:**
- Strategy-name → `HIGH` mapping for `population_subgroup_contrast` and `regime_separated_contrast`

Replaced with `_independence_from_cohort()` using measured overlap profiles.

---

## 6. EvidenceDerivedCohortBinder architecture

```
Unresolved uncertainty + ledger priors + legal grammar + panel metadata
  → generate categorical + temporal candidates
  → overlap vs prior fingerprints
  → derive ScientificEvidenceIndependenceProfile
  → semantic-preservation gate / anti-rescue gate
  → lexicographic rank
  → SELECTED | AMBIGUOUS_COHORT_SELECTION | NO_DEFENSIBLE_COHORT
```

Integrated into `FalsificationOperator` via `_propose_cohort_bound_action()` for `population_subgroup_contrast` and `regime_separated_contrast`.

---

## 7–13. Record types and gates

- **CohortCandidateRecord** — cohort semantics, provenance, overlap, independence, redundancy, rescue, executability, hash
- **CohortOverlapProfile** — row/date/symbol/context overlap, subset/superset/complement relation
- **ScientificEvidenceIndependenceProfile** — six structured dimensions derived from overlap (not strategy labels)
- **Semantic-preservation gate** — rejects feature/outcome/refine filters (`FORK_REQUIRED`)
- **Anti-rescue gate** — blocks post-contradiction narrowing and high-overlap slice mining
- **Ranking** — lexicographic: fork → rescue → redundancy → weak independence → overlap → sample → executability → semantic hash tiebreak
- **Silence** — `NO_DEFENSIBLE_COHORT` when all candidates redundant/rescue/invalid

---

## 14. BB-Cohort-01 results

**18/18 passed** — see `diagnostics/phase_3i17b_evidence_cohort_binding/artifacts/01_bb_cohort_01.json`

Covers: independent complement, row-diff≠independence, label invariance, insufficient sample, fork, rescue, ambiguity, full redundancy silence, tool removal, outcome leakage prohibition, ordering invariance, cross-family generalization.

---

## 15. Counterfactual results (CF-C1–C8)

All passed — see `artifacts/04_counterfactuals.json`

| CF | Result |
|----|--------|
| CF-C1 | Population uncertainty resolved → `population_subgroup_contrast` absent |
| CF-C2 | Added prior coverage → disposition degrades to silence |
| CF-C3 | Ranking follows overlap not label |
| CF-C4 | Rename invariant |
| CF-C5 | Ordering invariant |
| CF-C6 | Tool removal → scientific assessment survives |
| CF-C7 | No tool representation inflation |
| CF-C8 | High ledger overlap → loses priority / silence |

---

## 16. Freeze hashes

| Artifact | Hash |
|----------|------|
| Binder | `cfaf175de409fd2e893497bc8f68d4a6ddc081b3b17158e4dfd9c266ca788b51` |
| Synthesis engine (unchanged) | `ee00da71e38310af531631b4fbb79b5d2a6961107d47a1ee21ce1d91a358724a` |
| Historical 3I.16 core | `efe9abd43ea9a8fbae86a69ea3648adefe83f955df34fafb61cc9221ed1a712f` |

---

## 17–19. Real T2 diagnostic

**Population robustness:** `NO_DEFENSIBLE_COHORT`  
**Temporal regime robustness:** `NO_DEFENSIBLE_COHORT`

All generated candidates reported in `artifacts/05_t2_cohort_diagnostic.json`.

Key finding: every legal `research_market_state` slice and episode holdout shows **row_overlap_fraction = 1.0** against E1 (full universe) and high overlap with E2 (date-filtered partial replication ~97.7%). Evidence-computed independence is LOW; redundancy REDUNDANT; rescue risk flagged where appropriate.

**This overturns the historical 3I.16 hardcoded NORMAL winner** — correctly. Frozen evidence implies silence, not forced subgroup selection.

---

## 20. 3I.17 defect re-audit

| Question | Answer |
|----------|--------|
| 1. Evidence-derived cohort choice? | **Yes** — legal dimensions + overlap |
| 2. Independence evidence-computed? | **Yes** — overlap-derived profiles |
| 3. Requires ledger structure? | **Yes** — prior fingerprints from E1/E2 population specs |
| 4. Winner changes with coverage? | **Yes** — CF-C2 demonstrated |
| 5. Ordering irrelevant? | **Yes** — BBC-17 / CF-C5 |
| 6. Survives tool representation change? | **Yes** — BBC-15 / CF-C6 |
| 7. Slice mining prevented? | **Yes** — anti-rescue + redundancy gates |
| 8. Cohort semantics frozen pre-result? | **Yes** — no outcome columns read |

---

## 21. Verdict

### `EVIDENCE_DERIVED_COHORT_BINDING_PASS`

---

## 22. Remaining defect

None material for this phase scope.

---

## 23. Minimal next phase

**Phase 3I.18 — One-Shot Execution Audit:** If a future synthesis state produces a `SELECTED` cohort binding, freeze that package and audit execution readiness once — still `NOT_EXECUTED` until explicit approval.

Current T2 state: **Mr.BOT should remain silent** on cohort-bound population/temporal actions.

---

## 24. NO EXPERIMENT EXECUTED

Confirmed. Historical 3I.16 package remains `NOT_EXECUTED`. No new executable package created for T2.

---

## Answers A–E

**A.** Yes — Mr.BOT generates and evaluates legal cohort candidates from pre-result evidence structure.

**B.** Yes — independence dimensions derive from measured row/date/symbol/context overlap, not strategy-name HIGH/MEDIUM labels.

**C.** Yes — returns `NO_DEFENSIBLE_COHORT` when all candidates are redundant, rescue-like, or invalid (T2 demonstrates this).

**D.** Yes — overlap drives ranking (BBC-02, CF-C3/C8); label rename and enumeration order do not (BBC-03, BBC-17, CF-C4/C5).

**E.** Mr.BOT should **remain silent** on cohort-bound actions for current frozen T2 evidence. No scientifically defensible cohort-bound next action to freeze for execution. Non-cohort actions (concentration, measurement, counterexample) remain available via the unchanged 3I.16 generator if selected by priority — but cohort-specific binding correctly refuses.

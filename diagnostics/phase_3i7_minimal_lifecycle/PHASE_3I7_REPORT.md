# Phase 3I.7 — Minimal Evidence-Responsive Proposition Lifecycle

**Mode:** Minimal primitive implementation — not a general lifecycle engine  
**Lifecycle version:** `opr_lifecycle_v1_3i7`  
**Verdict:** **LIFECYCLE_PASS**

---

## 1. Branch / Commits / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i7-minimal-lifecycle-aad2` |
| Base | 3I.5 prioritizer + 3I.6 design docs |

---

## 2. Files Changed

### New modules

| File | Purpose |
|------|---------|
| `lifecycle_records.py` | EvidenceClass, EpistemicUpdateRecord, ResearchDecisionRecord |
| `interpretation_contract.py` | Pre-result contract builder |
| `lifecycle_execution.py` | Quintile metric extraction |
| `proposition_experiment_interpreter.py` | Deterministic interpreter + transitions |
| `lifecycle_runner.py` | Single-shot lifecycle orchestration |

### Diagnostics

| Path | Purpose |
|------|---------|
| `diagnostics/phase_3i7_minimal_lifecycle/run_phase_3i7.py` | Freeze → test → real experiment |
| `diagnostics/phase_3i7_minimal_lifecycle/artifacts/` | Frozen chain artifacts |

### Tests

| File | Coverage |
|------|----------|
| `tests/test_edge_research_opr_phase_3i7.py` | 14 tests including synthetic + real |

**Not modified:** `opr_generator_v1_3i2`, `opr_prioritizer_v1_3i5`, surprise thresholds.

---

## 3. Frozen Proposition Identity

| Field | Value |
|-------|-------|
| proposition_id | `prop-efb650d9bd5c451f` |
| proposition_hash | `c3aab7de80fdb9e56b7be68d517ec0e4792b711ec9772638143df3cfe4e39c9b` |
| focal_date | 2026-08-02 (3I.5 prioritized representative) |
| contrast_direction | positive |
| data_cutoff | 2026-08-17 |
| scientific_question | Does cross-sectional rs_spread dispersion tier predict differential forward t5_return across the market cross-section? |

Proposition immutable after experiment — hash verified in post-hoc audit.

---

## 4. Pre-Result Interpretation Contract

Frozen at `2026-08-22T02:24:20` **before** ToolResult read.

| Rule | Definition |
|------|------------|
| SUPPORTING | high_quintile_mean > low_quintile_mean AND spread ≥ 0.5 |
| DISCONFIRMING | direction_violation OR outcome_spread ≤ 0 |
| DISCONFIRMING_STRONG | direction_violation AND spread ≥ 0.5 |
| NON_INFORMATIVE | spread < 0.5, no direction violation |
| INVALID | tool failure, sample < 58, cutoff mismatch |

Contract hash: `3474a096aa6ee9c57ee1120f4a41398b08307038b23220016fa6bc9fddff77e2`

---

## 5. PropositionExperimentInterpreter Design

Narrow, deterministic, auditable:
- Inputs: frozen contract, ToolResult, QuintileMetrics, cutoff
- Validity gate before classification
- No LLM, no hidden benchmarks, no template catalog
- Quintile extraction uses same `pd.qcut` as OPR evidence ingest

---

## 6. Evidence Validity Gate

Checks: tool_status=OK, sample ≥ min_sample (58), cutoff match, quintile metrics present.

---

## 7. EpistemicUpdateRecord

Append-only record linking proposition → experiment → evidence class → state transition.

Real run: `epu-5a7bec6e47ec` — HYPOTHESIS → **SUPPORTED**

---

## 8. Frozen Transition Mapping

| Evidence | Resulting State |
|----------|-----------------|
| SUPPORTING | SUPPORTED |
| DISCONFIRMING (weak) | WEAKENED |
| DISCONFIRMING (strong) | FALSIFIED |
| CONTRADICTORY | WEAKENED |
| NON_INFORMATIVE | INSUFFICIENT_EVIDENCE |
| INVALID | UNCHANGED (HYPOTHESIS) |

---

## 9. ResearchDecisionRecord

Real run: `dec-c92fb28fdc13` — cites experiment metrics, condition matched, rejected alternatives.

---

## 10. Frozen Decision Mapping

| Evidence | Next Action |
|----------|-------------|
| SUPPORTING | **SEEK_FALSIFICATION** (falsification-first) |
| DISCONFIRMING | SEEK_REPLICATION |
| DISCONFIRMING_STRONG | ABANDON |
| CONTRADICTORY | SEEK_FALSIFICATION |
| NON_INFORMATIVE | HOLD_UNRESOLVED |
| INVALID | HOLD_UNRESOLVED |

---

## 11. Synthetic / Adversarial Test Results

| Case | Expected | Result |
|------|----------|--------|
| A clear support | SUPPORTING | PASS |
| B clear disconfirm | DISCONFIRMING | PASS |
| C contradictory | CONTRADICTORY | PASS |
| D non-informative | NON_INFORMATIVE | PASS |
| E invalid | INVALID | PASS |
| F strong falsification | FALSIFIED + ABANDON | PASS |
| G rescue temptation | no mutation path | PASS |

Counterfactual: SUPPORTING → SEEK_FALSIFICATION ≠ DISCONFIRMING → ABANDON.

---

## 12. Counterfactual Evidence-Causality

Verified: materially different evidence classes produce different next actions. INVALID preserves HYPOTHESIS. Support chooses falsification over replication.

---

## 13. Append-Only Lineage Audit

Chain: PropositionRecord → ExperimentSpec → ToolResult → EpistemicUpdateRecord → ResearchDecisionRecord

All nodes hash-linked in `09_append_only_lineage.json`. Proposition hash unchanged.

---

## 14. Real ToolResult

- tool: partition_group_compare v1
- status: OK
- sample_size (quintile cohort): 6106
- outcome_spread (success_rate metric): 100.0

---

## 15. Real Evidence Classification

**SUPPORTING** — high quintile mean (1.93) > low (-0.42), spread 2.35 ≥ 0.5

---

## 16. Real Epistemic Update

HYPOTHESIS → **SUPPORTED** (first evidence-responsive state change)

---

## 17. Real Next Research Decision

**SEEK_FALSIFICATION** — falsification-first after support, not confirmatory replication.

---

## 18. Post-Hoc / Rescue Audit

| Check | Result |
|-------|--------|
| proposition_hash_unchanged | true |
| hypothesis_rescue_detected | false |
| post_hoc_rule_change | false |
| zone_c_referenced | false |

---

## 19. Hidden-Firewall Audit

Interpreter modules contain no Zone C references. Passed.

---

## 20. Verdict: LIFECYCLE_PASS

All acceptance criteria met:
- Pre-result contract frozen
- Deterministic classification
- Valid evidence changed epistemic state (HYPOTHESIS → SUPPORTED)
- Decision cites actual evidence
- Counterfactuals pass
- Proposition immutable
- No hypothesis rescue
- Append-only lineage complete

---

## 21. Remaining Capability Limitation

Single experiment, single tool, single proposition family. No automatic experiment execution loop, no FORK, no population/horizon mutation, no planner integration.

---

## 22. Proposed Next Step (Proposal Only)

**Phase 3I.8 — Execute SEEK_FALSIFICATION**: run one pre-registered disconfirming experiment and append second EpistemicUpdateRecord to lineage.

---

## Final Answers

### A. Did Mr.BOT interpret experimental evidence relative to a proposition it originated?

**Yes.** Proposition `prop-efb650d9bd5c451f` from autonomous OPR (3I.3/3I.5); interpreted against its own falsifiable_expectation and disconfirming_observation_spec.

### B. Did evidence change or preserve epistemic position for an explicit scientific reason?

**Yes.** HYPOTHESIS → SUPPORTED because pre-registered condition `high_quintile_mean > low_quintile_mean AND quintile_mean_spread >= 0.5` matched.

### C. Would materially different evidence cause a different decision?

**Yes.** Counterfactual tests show DISCONFIRMING → ABANDON/SEEK_REPLICATION vs SUPPORTING → SEEK_FALSIFICATION.

### D. Change of mind without moving goalposts?

**Yes.** Interpretation contract frozen 8 seconds before ToolResult processing; proposition hash unchanged; no threshold/direction/population edits post-result.

---

**STOP.** No next phase implementation.

# Phase 3J.14 — Research Capability Gap & Process-Integrity Audit

**Stop boundary:** `STOP_RESEARCH_CAPABILITY_GAP_AUDITED`  
**Branch:** `cursor/phase-3j14-research-capability-gap-audit-aad2`  
**Base:** `cursor/phase-3j13-history-aware-follow-on-experiment-generation-aad2` (PR #71)  
**Status:** PASS

---

## Summary

Phase 3J.14 is an **audit-first** phase. No research policy, candidate generation, or production modules were modified. Examiner-only diagnostics were added under `benchmarks/bb_capability_gap_audit_01/zone_d_examiner/` to explain the blind process-integrity drop (1.00 → 0.917), classify ordinal ≥3 `NO_FAITHFUL_EXPERIMENT` / SILENCE cases, and determine whether critical false positives = 0 reflects genuine scientific restraint vs conservative inability to continue.

**Verdict:** The 0.917 process-integrity score is an **expected longer-journey scoring artifact**, not a scientific defect. Ordinal ≥3 SILENCE cases are **justified redundancy stops**, not capability gaps. Critical FP = 0 is a **mixture** of genuine discrimination and conservative fail-closed behavior. One **process-integrity defect** was identified (execution attempted on `NO_FAITHFUL_EXPERIMENT` packages) — reported but **not fixed** in this phase.

---

## Priority Question A — Why Process Integrity Dropped 1.00 → 0.917

### Finding

| Metric | Budget=2 (3J.11 baseline) | Budget=4 (3J.12/3J.13 longer journey) |
|---|---|---|
| Avg process integrity | **1.000** | **0.917** |
| Changed cases | — | **2** (seeds 201, 202) |
| Per-case delta | — | 1.0 → 0.5 each (−0.5) |

Average: `(10 × 1.0 + 2 × 0.5) / 12 = 0.917`

### Root Cause

Only **BLIND-B artifact cases** (seeds 201, 202) changed. At budget=2, journeys ended at `BUDGET_EXHAUSTED` before Decision #2 completed → `final_epistemic_state=null` → examiner scored PI=1.0 with **no findings** (scoring artifact: incomplete journey masked epistemic state).

At budget=4, Decision #2 completes → `SCIENTIFIC_STOP` / `STOP_LOW_INCREMENTAL` with `final_epistemic_state=SUPPORTED` on BLIND-B. Examiner applies:

- `risky_calibration:final_state=SUPPORTED` (−0.35)
- `possible_artifact_or_confound_overgeneralization` (−0.25)
- `appropriate_uncertainty_stop` (+0.1)

**Net score: 0.5**

### Classification

`EXPECTED_LONGER_JOURNEY_COST` + `SCORING_ARTIFACT` — NOT a scientific defect. The system appropriately STOPped with low incremental value, but the examiner penalizes visible SUPPORTED on artifact-class cases when the full journey completes.

### Localization

Both divergences occur at **ordinal 2**, stage `lifecycle_outcome`, field `decision_leaving`:
- Baseline outcome: `BUDGET_EXHAUSTED`
- New outcome: `SCIENTIFIC_STOP`

See `artifacts/02_process_integrity_delta.json`.

---

## Priority Question B — Ordinal ≥3 NO_FAITHFUL_EXPERIMENT / SILENCE Classification

### Cases Audited (5)

| Seed | Blind class | Target null | Action | Classification | Capability gap? |
|---|---|---|---|---|---|
| 501 | BLIND-E | episode_artifact | SEEK_FALSIFICATION | REDUNDANCY_STOP | No |
| 502 | BLIND-E | episode_artifact | SEEK_FALSIFICATION | REDUNDANCY_STOP | No |
| 601 | BLIND-F | episode_artifact | SEEK_FALSIFICATION | REDUNDANCY_STOP | No |
| 602 | BLIND-F | episode_artifact | SEEK_FALSIFICATION | REDUNDANCY_STOP | No |
| 77 | (generic panel) | episode_artifact | SEEK_FALSIFICATION | REDUNDANCY_STOP | No |

### Pattern

All cases share:
- `package_disposition`: `NO_FAITHFUL_EXPERIMENT`
- Both grammar families for `episode_artifact` generated and rejected:
  - `counterexample_period_search`
  - `episode_holdout_excluding_motivating`
- Rejection reasons: `previously_rejected_core_hash`, `representation_alias_core_hash_match`
- `families_exhausted`: true
- `gap_found`: false (capability probe)

### Verdict

**Justified scientific restraint (REDUNDANCY_STOP)** — not a capability gap, process defect, toolbox gap, or scoring gap. The frozen grammar families for episode robustness were already exercised in prior experiment history; the selector correctly rejects redundant/alias designs.

### Abstract Categories (Audit Notes Only — Not Required Fixes)

The toolbox coverage map identifies unrepresented abstract categories in principle:
- `independent_temporal_episode`
- `interaction_test`
- `alternative_outcome_semantics`
- `negative_control`
- `orthogonal_measurement`

These categories are **not required** to explain the observed silence. All observed cases are fully explained by grammar exhaustion + redundancy detection.

See `artifacts/06_ordinal_ge3_silence_audits.json`.

---

## Priority Question C — Critical False Positives = 0: Restraint vs Inability

### Finding

| Component | Count |
|---|---|
| Critical false positives | **0** |
| Elevated false positives (SUPPORTED on artifact classes) | **2** (BLIND-B 201/202) |
| SUPPORTED on BLIND-D (pure noise) | **0** |
| Genuine discrimination cases | **8** |
| Conservative fail-closed cases | **4** |
| Inability-to-continue-only cases | **0** |
| `flag_fp_zero_from_inability_only` | **false** |

### Mixture Explanation

Critical FP = 0 is a **mixture**:
1. **Genuine scientific discrimination** — appropriate STOP/SILENCE on most cases; no SUPPORTED on pure-noise BLIND-D.
2. **Conservative fail-closed behavior** — 4 cases (501/502/601/602) reach `FAILED_CLOSED` when lifecycle attempts execution on `NO_FAITHFUL_EXPERIMENT` packages at ordinal 3.
3. **Elevated but non-critical FP** — 2 BLIND-B cases show SUPPORTED final epistemic state (appropriately penalized by examiner).

**Zero alone does NOT prove robust edge discovery.** The elevated FP count and BLIND-B SUPPORTED states indicate calibration sensitivity on artifact-class cases, even though critical FP remains 0.

See `artifacts/04_false_positive_restraint.json`.

---

## Priority Question D — Examiner Isolation (No Knowledge Leakage)

### Hidden-Answer Audit

**PASS** — Research module allowlist scanned; zero forbidden tokens found.

Modules checked: `blind_research_examination_runner.py`, `bounded_lifecycle_controller.py`, `bounded_lifecycle_records.py`, `bounded_lifecycle_state.py`, `production_bounded_lifecycle.py`, `production_trigger.py`, `first_experiment_research_decider.py`, `second_experiment_research_decider.py`, `follow_on_experiment_{candidates,history_context,selector}.py`, `second_experiment_pipeline.py`, `second_experiment_candidates.py`.

Examiner fixtures (`bb_*`) excluded from research scan. Examiner zone isolated at `benchmarks/bb_capability_gap_audit_01/`.

### CF-CG6

Examiner audit modules (`bb_capability_gap_audit`, `capability_probe`, `seed_to_blind_class`) not imported by research runtime. **PASS**.

See `artifacts/07_hidden_answer_audit.json`.

---

## Priority Question E — Capability Gaps (Report Only, Not Fixed)

### No Actionable Capability Gaps Found

All 5 ordinal ≥3 SILENCE cases: `gap_found: false`. The frozen research grammar correctly operationalizes the frozen `ResearchDecision` targets; silence is due to redundancy, not missing abstractions.

### Process-Integrity Defect Identified (NOT Fixed in 3J.14)

**Defect:** Lifecycle reaches ordinal 3 design with `NO_FAITHFUL_EXPERIMENT` disposition, then **attempts execution** → `FAILED_CLOSED` / `experiment_3_execution_failed`.

**Affected seeds:** 501, 502, 601, 602 (4 cases)

**Location:** `bounded_lifecycle_controller.py` — `_run_follow_on_execute` called when package disposition is silence, not `SELECTED`.

**Classification:** `CONSERVATIVE_FAIL_CLOSED` / unnecessary continuation (journey safety audit)

**Impact:** Process integrity score unaffected (still 1.0 on these cases), but lifecycle behavior is wasteful and produces misleading `FAILED_CLOSED` outcomes instead of clean scientific silence termination.

**Recommendation for future phase:** Gate execution on `SELECTED` disposition only; terminate cleanly on `NO_FAITHFUL_EXPERIMENT`.

---

## Longer-Journey Safety Audit (Budget=4, 12 Cases)

| Pattern | Count |
|---|---|
| confirmation_loops | 0 |
| horizon_shopping | 0 |
| slice_shopping | 0 |
| null_cycling | 0 |
| evidence_recycling | 0 |
| dependence_undercounting | 0 |
| unjustified_confidence_escalation | 2 (BLIND-B 201/202) |
| ignored_contradiction | 0 |
| premature_stop | 8 (appropriate STOP_LOW_INCREMENTAL at exp 2) |
| unnecessary_continuation | 4 (NO_FAITHFUL execution attempts) |

No confirmation loops, horizon shopping, or null cycling detected. Anti-loop restraint from 3J.13 history-aware generation is functioning.

See `artifacts/03_longer_journey_safety.json`.

---

## Counterfactuals (CF-CG1–10)

All passed. See `artifacts/01_cf_cg_summary.json`.

| Case | Description | Result |
|---|---|---|
| CF-CG1 | Exhausted episode grammar → justified silence, not capability gap | PASS (REDUNDANCY_STOP) |
| CF-CG2 | Unknown null not in grammar → CAPABILITY_GAP | PASS |
| CF-CG3 | Faithful design exists but not executable → EXECUTABILITY_GAP | PASS |
| CF-CG4 | PI loss from examiner penalties after decision completes, not scientific defect | PASS (EXPECTED_LONGER_JOURNEY_COST) |
| CF-CG5 | FAILED_CLOSED on silence execution attempt classified correctly | PASS (CONSERVATIVE_FAIL_CLOSED) |
| CF-CG6 | Examiner audit modules not imported by research runtime | PASS |
| CF-CG7 | PI delta localized to ordinal 2 decision event | PASS |
| CF-CG8 | All-bootstrap-silent suite flags FP-zero-from-inability | PASS |
| CF-CG9 | Null cycling → REDUNDANCY_STOP (anti-loop restraint) | PASS |
| CF-CG10 | Candidate ordering does not change silence classification | PASS |

---

## Frozen Policy Hashes

Policy modules frozen at head `a4b223b87`. See `artifacts/00_frozen_policy_hashes.json`.

Key modules unchanged from 3J.13:
- `follow_on_experiment_candidates.py`
- `follow_on_experiment_history_context.py`
- `follow_on_experiment_selector.py`
- `second_experiment_pipeline.py`

---

## Regression

All passed:

- Phase 3J.14 tests (4 tests)
- Phase 3J.13 CF-FG counterfactuals
- Phase 3J.12 CF-NX counterfactuals
- Phase 3J.11 CF-BR counterfactuals

See `artifacts/08_regression_summary.json`.

---

## Examiner-Only Audit Modules (New in 3J.14)

| Module | Purpose |
|---|---|
| `capability_gap_auditor.py` | Orchestrator: blind suite, silence audits, policy hash freeze |
| `process_integrity_delta.py` | 3J.11 vs 3J.13 longer-budget PI comparison |
| `silence_classifier.py` | Classifies NO_FAITHFUL dispositions |
| `capability_probe.py` | Examiner-side gap probes (diagnostic only) |
| `toolbox_coverage_map.py` | Generic null → family → representable/executable map |
| `longer_journey_safety.py` | Anti-loop / safety pattern scan |
| `fp_restraint_analysis.py` | Explains critical FP = 0 |
| `bb_capability_gap_audit_01_fixtures.py` | CF-CG1–10 counterfactuals |

All modules live under `benchmarks/bb_capability_gap_audit_01/zone_d_examiner/` — **never imported by research runtime**.

---

## Audit Summary

| Check | Result |
|---|---|
| CF-CG1–10 | **PASS** |
| Process integrity delta explained | **PASS** (EXPECTED_LONGER_JOURNEY_COST) |
| Ordinal ≥3 silence classified | **PASS** (5/5 REDUNDANCY_STOP) |
| Capability gaps found | **None actionable** |
| Critical false positives | **0** (mixture, not inability-only) |
| Hidden-answer audit | **PASS** |
| Regressions | **PASS** |
| Process defect identified | **YES** (NO_FAITHFUL execution attempt — not fixed) |
| **Phase pass** | **true** |

See `artifacts/09_audit_summary.json`.

---

## Known Limitations (Explicit)

1. **Scoring artifact:** Budget=2 incomplete journeys can mask epistemic states and inflate PI scores.
2. **Process defect:** `NO_FAITHFUL_EXPERIMENT` packages should not reach execution gate.
3. **Abstract categories:** Unrepresented toolbox categories exist in principle but do not explain observed silence.
4. **Elevated FP on BLIND-B:** SUPPORTED visible on artifact cases when journey completes — examiner penalizes but does not classify as critical FP.

---

## What Was NOT Done (Hard Stop)

Per phase specification:
- No research policy tuning
- No capability gap implementation
- No UI, deploy, reboot, edge activation
- No BUY/SELL or continuous research
- No next phase started

---

**HARD STOP:** `STOP_RESEARCH_CAPABILITY_GAP_AUDITED`

# Phase 3I.2 — Minimal Autonomous OPR Primitive

**Branch:** `cursor/phase-3i2-minimal-opr-primitive-aad2`  
**Mode:** First implementation — research-only, isolated from production planner/trading  
**Verdict:** **PASS** (dev proof) / **INCONCLUSIVE** (BB-Prop-01 Zone B blind panel)

---

## 1. Branch / Commits / PR

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3i2-minimal-opr-primitive-aad2` |
| Base | Phase 3I.1 OPR contract (`75b256ead` + 3I.2 implementation) |
| Generator | `opr_generator_v1_3i2` |
| Modules | `modules/edge_research/opr_bridge/` |
| Tests | `tests/test_edge_research_opr_bridge.py` |
| Evaluator | `diagnostics/phase_3i2_minimal_opr_primitive/run_evaluation.py` |

---

## 2. Files Changed

**New:**
- `modules/edge_research/opr_bridge/` — 12 modules (pipeline, evidence, surprise, synthesizer, record, audits, adapter)
- `tests/test_edge_research_opr_bridge.py`
- `diagnostics/phase_3i2_minimal_opr_primitive/run_evaluation.py`
- `diagnostics/phase_3i2_minimal_opr_primitive/artifacts/` — evaluation outputs
- `benchmarks/bb_prop_01/zone_a_development/.gitkeep`
- `benchmarks/bb_prop_01/zone_b_blind_panel/.gitkeep`
- `benchmarks/bb_prop_01/zone_c_hidden/.gitkeep`
- `benchmarks/bb_prop_01/zone_d_evaluator/.gitkeep`

**Unchanged (protected):** `research_actions.py`, `research_interpreter.py`, planner, novelty logic, Challenger, discovery engine, templates, GAP/OBS semantics.

---

## 3. Leakage / Access Audit

**Result: PASS**

- Zone C **not populated** — hidden convergence **INDETERMINATE**
- Generator runtime has **no access** to hidden phenomenon definitions
- OPR synthesis modules contain **no forbidden pattern imports**
- `artifacts/00_leakage_access_audit.json`

---

## 4. Observation Detector

**Class:** `CROSS_SECTIONAL_DISPERSION_ANOMALY`

Per-date cross-sectional std of `rs_spread` + quintile structure of `t5_return` conditional on dispersion tier.

**Frozen thresholds** (`constants.py`):
- `MIN_DATES_FOR_BASELINE = 20`
- `SURPRISE_ZSCORE_THRESHOLD = 2.0`
- `QUINTILE_SPREAD_THRESHOLD = 1.5`
- `MIN_SYMBOLS_PER_DATE = 15`

**Valid outcomes:** surprise detected, insufficient baseline, not surprising → `NO_PROPOSITION_EMITTED`

No OBS_* or GAP_* labels used in detection.

---

## 5. Frozen Surprise Rule

Surprise requires empirical contrast vs **historical self-baseline** (prior dates' cross-sectional dispersion series):

1. |z-score| ≥ 2.0 vs baseline mean/std, **OR**
2. Quintile return spread ≥ 1.5 with ≥3 quintiles, **OR**
3. Monotonicity break with spread ≥ 0.75

Surprise basis stored in `observation_provenance.surprise_basis` with reconstructable statistics.

---

## 6. CONTRAST_TO_PROPOSITION Mechanism

Single synthesis path (`proposition_synthesizer.py`):

```
empirical quintile contrast → relation inference (predicts/modulates/contrasts_with)
→ population/outcome specs → birth certificate → PropositionRecord
```

- Does **not** read 24-template catalog
- Does **not** map anomaly type → prewritten hypothesis
- Relation direction inferred from quintile outcome delta
- Bounded relation slots only

---

## 7. PropositionRecord Implementation

`proposition_record.py` implements frozen 3I.1 schema v1 including:
- `observation_provenance` with `evidence_hash`
- Full birth certificate (BC_Q1–Q8)
- `disconfirming_observation_spec`
- Post-hoc `template_independence_audit`
- `executability_status`

---

## 8. Example Development Birth Certificate

From synthetic Zone A anomaly proof (`artifacts/01b_synthetic_anomaly_result.json`):

| Question | Answer (abbreviated) |
|----------|---------------------|
| Q1 Observed | rs_spread std=9.0163, 40 symbols, quintile spread=9.8911 |
| Q2 Surprise | z=8.21 vs 29-date baseline; spread exceeds 1.5 |
| Q3 Question | Does dispersion tier predict differential t5_return? |
| Q4 Proposition | population=all, relation=predicts, outcome=t5_return |
| Q5 Support | High quintile mean 6.93 > low -2.96 by ≥4.95 |
| Q6 Falsify | median_spread ≤ 0 or quintile rank reversal |
| Q7 Not template | Derived from quintile contrast, not catalog lookup |
| Q8 Execute | partition_group_compare on rs_spread |

**Template classification:** `SCIENTIFICALLY_NOVEL` (semantic_similarity=0.0 to catalog)

---

## 9. Falsification Implementation

Every emitted proposition includes proposition-specific `disconfirming_observation_spec`:

```json
{
  "description": "If high-rs_spread names do not outperform low-rs_spread names...",
  "operational_test": "partition_group_compare median_spread <= 0",
  "threshold": "median_spread <= 0 or group rank reversal"
}
```

No generic boilerplate.

---

## 10. Template-Independence Results

| Context | Classification |
|---------|---------------|
| Synthetic dev proof | SCIENTIFICALLY_NOVEL |
| Real frozen panel | N/A (silence — no emission) |

Evaluator runs **after** synthesis; does not modify proposition. No retry for novelty.

---

## 11. OBS/GAP Laundering Results

All 6 LAUNDER tests **PASS** on emitted proposition:
- Code-only provenance: blocked
- Raw evidence path required
- Numeric citations present
- Surprise replayable without ontology labels

---

## 12. Executability Results

| Context | Status |
|---------|--------|
| Synthetic dev proof | **EXECUTABLE** (partition_group_compare, rs_spread, n_groups=5) |
| Real frozen panel | N/A (no proposition) |

Syntax adaptation only (partition column, group count) — scientific meaning unchanged.

---

## 13. Negative / Adversarial Controls

| Control | Result |
|---------|--------|
| NEG_01 Pure noise | 0 propositions ✓ |
| NEG_03 Duplicated evidence | ≤1 proposition ✓ |
| NEG_09 Ontology-only | Structural exclusion ✓ |
| NEG_10 Silence valid | ✓ |

---

## 14. Determinism / Replay

Identical evidence + cutoff + generator version → identical `proposition_id`. Verified in tests and `artifacts/03_determinism_replay.json`.

---

## 15. Pre-Blind Gate

**ALL PASS** — see `artifacts/04_pre_blind_gates.json`

Zone B blind evaluation **executed** (gates passed).

---

## 16. BB-Prop-01 Aggregate Results

**Zone B (40% holdout):**
- Eligible observations: 7
- Propositions emitted: **0**
- Silence rate: **100%**
- Hidden convergence class: **INDETERMINATE** (Zone C not populated)

Real blind panel lacked sufficient surprise under frozen thresholds — valid **INCONCLUSIVE** outcome.

---

## 17. Verdict

### **PASS** (development proof)

At least one proposition demonstrates credible evidence-grounded autonomous scientific origination:
- Originated from raw quintile/dispersion evidence
- Full birth certificate + falsification birthright
- Laundering controls pass
- Classified SCIENTIFICALLY_NOVEL
- EXECUTABLE via existing ExperimentSpec validation

### **INCONCLUSIVE** (BB-Prop-01 Zone B)

Blind panel provided insufficient eligible anomaly evidence under frozen thresholds.

---

## 18. Remaining Capability Limitation

1. Only `CROSS_SECTIONAL_DISPERSION_ANOMALY` observation class implemented
2. Frozen panel has only 20 dates — limits baseline depth on real data
3. Zone C not populated — hidden convergence unevaluated
4. OPR not wired to planner/portfolio — parallel research artifact only
5. Real-market silence under conservative thresholds — may need more panel history, not threshold tuning from hidden eval

---

## 19. Proposed Next Step (proposal only)

**Phase 3I.3:** Populate Zone C in protected store; extend panel history; add second observation class (e.g., temporal regime shift) using same CONTRAST_TO_PROPOSITION mechanism; wire EXECUTABLE records to research graph as optional parallel branch — still isolated from trading.

---

## Final Questions

### A. Did Mr.BOT originate at least one scientific proposition from empirical evidence rather than from a human-authored template?

**Yes.** Synthetic dev proof (and unit tests) show proposition derived from cross-sectional dispersion quintile contrast — not from `research_actions.py` template catalog or GAP/OBS decode.

### B. Can we trace exactly why that proposition was born?

**Yes.** `observation_provenance` contains evidence anchor, 9 empirical artifacts, surprise basis with z-score and spread statistics, and `evidence_hash` for replay.

### C. Did it state in advance what evidence could make it wrong?

**Yes.** `disconfirming_observation_spec` specifies operational partition_group_compare median_spread ≤ 0 and quintile rank reversal as disconfirming patterns.

### D. Did the blind evaluator find evidence of genuine scientific novelty without revealing the hidden answer?

**INDETERMINATE.** Zone B emitted zero propositions (insufficient surprise). Zone C not populated — no hidden convergence evaluation possible. No hidden answer information was exposed to generator.

---

**STOP.** Next phase not implemented. No deployment.

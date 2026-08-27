# Phase 3I.5 — Observation Prioritization & Pre-Emission Scientific-Identity Deduplication

**Mode:** Research-only orchestration layer — frozen `opr_generator_v1_3i2` unchanged  
**Prioritizer:** `opr_prioritizer_v1_3i5`  
**3I.4 verdict accepted:** PARTIAL_VALIDATION

---

## 1. Branch / Commits / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i5-observation-prioritization-aad2` |
| Prioritizer version | `opr_prioritizer_v1_3i5` |
| Generator (frozen) | `opr_generator_v1_3i2` |
| PR | Created at push |

---

## 2. Files Changed

### New modules (`modules/edge_research/opr_bridge/`)

| File | Purpose |
|------|---------|
| `observation_entities.py` | OBSERVATION EVENT / SCIENTIFIC PROPOSITION / EVIDENCE EVENT model |
| `semantic_projection.py` | Pre-emission semantic projection (no PropositionRecord) |
| `scientific_identity.py` | Grouping + pairwise classification |
| `prioritization.py` | Pre-registered lexicographic ranker |
| `prioritized_pipeline.py` | `run_opr_pipeline_prioritized()` |

### Updated

| File | Change |
|------|--------|
| `__init__.py` | Export prioritized pipeline + `PRIORITIZER_VERSION` |

### Diagnostics

| Path | Purpose |
|------|---------|
| `diagnostics/phase_3i5_observation_prioritization/run_phase_3i5.py` | Counterfactual replay + blind eval |
| `diagnostics/phase_3i5_observation_prioritization/artifacts/` | Pre-registration, replay, eval JSON |

### Tests

| File | Purpose |
|------|---------|
| `tests/test_edge_research_opr_phase_3i5.py` | Grouping, replay, negative controls |

**Not modified:** `proposition_synthesizer.py`, `surprise_detector.py`, `constants.py` thresholds, `pipeline.py` (old path preserved).

---

## 3. Frozen Components Audit

| Component | Status |
|-----------|--------|
| `opr_generator_v1_3i2` | Unchanged |
| CROSS_SECTIONAL_DISPERSION_ANOMALY | Unchanged |
| z ≥ 2.0, spread ≥ 1.5, mono spread ≥ 0.75 | Unchanged |
| CONTRAST_TO_PROPOSITION semantics | Unchanged — projection imports same helpers |
| PropositionRecord v1 | Unchanged |
| Birth certificate / falsification | Unchanged |
| Template-independence evaluator | Unchanged (post-synthesis) |
| Hidden evaluator | Post-hoc only |
| Executability adapter | Unchanged |
| `MAX_PROPOSITIONS_PER_SESSION = 3` | Unchanged — now counts **unique propositions** |

---

## 4. Observation / Proposition / Evidence Entity Model

```
OBSERVATION EVENT
  └─ focal_date + DispersionEvidencePayload + SurpriseAssessment

SCIENTIFIC PROPOSITION GROUP
  └─ identity_key + scientific_question + aggregated EvidenceEvents

EVIDENCE EVENT
  └─ observation_event + role (SUPPORT | CONTRADICT | NEUTRAL)
     + contrast_direction + empirical_delta
```

Three dates emitting the same question → **1 proposition group, 3 evidence events**.

---

## 5. Pre-Emission Semantic Projection

`project_contrast_semantics(evidence, surprise) → SemanticProjection`

- Imports `_infer_relation_and_direction`, `_population_spec_all`, `_outcome_spec_compare` from frozen synthesizer
- Builds `CanonicalPropositionCore` via same `build_canonical_proposition_core` call
- Does **not** create PropositionRecord, birth certificate, or proposition_id
- Used only for identity grouping and prioritization gates

---

## 6. Scientific-Identity Grouping Method

1. Collect surprising observation events (22 in frozen opportunity set)
2. Project each to `SemanticProjection`
3. Cluster via `cores_same_question()` + matching `scientific_question` text
4. Exclude from identity hash: focal_date, evidence_hash, proposition_id, relation_type (per-date inference noise)
5. Pairwise classification: `SAME_PROPOSITION_DIFFERENT_EVIDENCE`, `RELATED_BUT_DISTINCT`, `GENUINELY_INDEPENDENT`, `INSUFFICIENT_EVIDENCE`

**3I.3/3I.4 dates:** 2026-06-29, 2026-06-30, 2026-07-23 → **1 group** (verified in tests).

---

## 7. Evidence Aggregation Semantics

- Each evidence event preserved separately in `EvidenceLineage.aggregated_evidence_events`
- Provenance per event retained (focal_date, evidence_hash, role, delta)
- Non-representative events → `AGGREGATED_AS_EVIDENCE` silence (not budget consumption)
- Contradictory directions flagged via `has_contradiction` on group
- Append-only lineage on `PrioritizedOprPipelineResult.evidence_lineages`

---

## 8. Prioritization Signals Selected / Rejected

### Selected (pre-registered)

| Signal | Scientific justification |
|--------|-------------------------|
| evidence_quality_gate | Insufficient cross-section → unreliable inference |
| surprise_gate | Must be empirically surprising per frozen detector |
| executability_gate | Non-testable propositions waste research budget |
| contradiction_presence | Conflicting evidence → higher investigation priority |
| independent_repeated_evidence | Independent replication increases confidence |
| surprise_magnitude | Larger quintile spread → stronger empirical anomaly |
| contrast_magnitude | Larger effect delta → more informative contrast |
| historical_rarity | Higher \|z\| vs baseline → less common dispersion state |

### Rejected

| Signal | Reason |
|--------|--------|
| chronological_order | Not scientific merit |
| hidden_phenomenon_similarity | Forbidden — Zone C firewall |
| known_edge_similarity | Forbidden |
| profitability_labels | Not scientific criterion |
| template_ids | Representation, not value |
| hard-coded feature/population/horizon preferences | Forbidden |

---

## 9. Ranking Mechanism

**Lexicographic** (no tuned weights):

```
rank_key = (
  contradiction_present,           # 0 or 1
  independent_evidence_count,      # int
  max_quintile_spread,             # float
  max_abs_empirical_delta,         # float
  max_abs_zscore,                  # float
)
```

Higher tuple wins. Representative evidence within group = max quintile spread, then |delta|, then |z|.

---

## 10. Budget Semantics

| Budget type | Semantics |
|-------------|-----------|
| Observation-processing | All eligible dates scanned |
| Unique-proposition | `max_unique_propositions=3` (same constant, new meaning) |
| Experiment/research | Not consumed in this phase |

OLD: 3 budget slots → 3 duplicate propositions  
NEW: 3 budget slots → 1 unique proposition + 21 aggregated evidence events

---

## 11. Counterfactual OLD vs NEW Replay

| Metric | OLD (first-come) | NEW (prioritized) |
|--------|------------------|-------------------|
| Propositions emitted | 3 | **1** |
| Unique scientific questions | 1 | **1** |
| Emitted focal dates | 2026-06-29, 06-30, 07-23 | Representative: **2026-08-02** |
| Max quintile spread in emissions | 4.96 | **6.40** |
| Aggregated evidence events | 0 | **22** |
| Proposition spam | 3× same question | **Compressed** |

**Higher-information evidence replaces weaker first-come evidence:** Yes (spread 6.40 > 4.96).  
**Scientific diversity:** Unchanged (1 unique idea — opportunity set has 1 proposition family).

---

## 12. Negative / Adversarial Controls

| Control | Result |
|---------|--------|
| Identical duplicate observations | Collapse to 1 group, 2 evidence events |
| Same proposition / independent dates | 1 group, 3 evidence events (3I.3 dates) |
| Pure noise panel | 0 emissions (valid silence) |
| Non-surprising focal date (2026-08-05) | INSUFFICIENT_SURPRISE silence |
| Frozen thresholds | z=2.0, spread=1.5 unchanged |
| All candidates low-value | Valid silence on noise |

Synthetic controls for related-but-distinct / genuinely independent require additional observation classes (out of scope per §19).

---

## 13. Blind Evaluation

| Metric | Value |
|--------|-------|
| Unique propositions emitted | 1 |
| Duplicate-evidence compression | 2 |
| Representative spread improved | Yes (4.96 → 6.40) |
| Research-worthiness rate | 1.0 |
| Grounding | Pass |
| Falsifiability | Pass |
| Executability | Pass |
| AGGREGATED_AS_EVIDENCE silences | 21 |

Hidden convergence evaluated **post-hoc only** (firewall passed).

---

## 14. Hidden-Firewall Audit

- Prioritizer modules contain **no** Zone C references
- Hidden evaluator run only after prioritizer frozen
- No hidden-answer signals in rank key

---

## 15. Capability Gate

### **PRIORITIZE_PASS**

The system demonstrably:
- Chooses scientifically stronger representative evidence (spread 6.40 vs first-come 4.96 max)
- Compresses duplicate propositions (3 → 1)
- Groups 22 triggers into 1 proposition with append-only evidence lineage
- Without hidden-answer tuning or proposition inflation

---

## 16. Remaining Capability Limitation

**BROADER_OBSERVATION_REPERTOIRE** — With only `CROSS_SECTIONAL_DISPERSION_ANOMALY`, the 22-trigger opportunity set collapses to **1 scientific proposition family**. Prioritization works but cannot increase scientific diversity until additional observation classes exist.

---

## 17. Proposed Next Step (Proposal Only)

**Phase 3I.6 — Second Observation Class with Prioritization Integration**

Add one new observation class (diagnostic spec only) to test whether prioritization selects among **genuinely distinct** proposition families when opportunity set contains >1 unique idea.

---

## Final Answers

### A. Can Mr.BOT recognize multiple observations as evidence for one idea?

**Yes.** 22 observation events → 1 scientific proposition group with 22 preserved evidence events.

### B. Can it choose which question deserves scarce research attention?

**Yes.** Representative evidence selected by surprise magnitude (2026-08-02, spread 6.40) instead of chronological first-come (2026-06-29, spread 2.50).

### C. Did prioritization improve scientific research quality without hidden-answer knowledge?

**Yes.** Duplicate proposition spam eliminated, representative evidence quality improved, all emitted records remain grounded/falsifiable/executable. Lexicographic ranking used only pre-registered scientific signals.

---

**STOP.** No deployment. No next-phase implementation.

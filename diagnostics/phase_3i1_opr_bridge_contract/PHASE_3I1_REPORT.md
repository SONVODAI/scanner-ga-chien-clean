# Phase 3I.1 — OPR Bridge Contract & BB-Prop-01 Pre-Registration

**Branch:** `cursor/phase-3i1-opr-bridge-contract-aad2`  
**Mode:** DESIGN + CONTRACT + FROZEN EVALUATION PRE-REGISTRATION ONLY  
**Production changes:** None  
**Readiness gate:** **READY_FOR_MINIMAL_OPR**

---

## 1. Branch / HEAD / Git Status

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3i1-opr-bridge-contract-aad2` |
| Base | Phase 3I.0 accepted finding (PARTIALLY READY) |
| Artifacts | `diagnostics/phase_3i1_opr_bridge_contract/` |
| Benchmark stub | `benchmarks/bb_prop_01/` |
| Validator | `run_preregistration.py` |

---

## 2. Input Evidence Classification

All potential OPR bridge inputs classified into four buckets (`artifacts/00_input_evidence_classification.json`):

| Class | OPR Primary Input? | Examples |
|-------|-------------------|----------|
| **RAW / DERIVED MARKET EVIDENCE** | **Yes** | Distributions, trajectories, tool-result metrics (`median_spread`, `cohort_win_rate`), residuals, empirical contrasts |
| **HUMAN-DEFINED DESCRIPTIVE ONTOLOGY** | **No** (index only) | `OBS_*`, `GAP_*`, assessment flags, `ObservationKind` |
| **HUMAN SCIENTIFIC PRIOR** | **No** (audit only) | 24 template families, `ROOT_CONFIG`, `SEARCH_FEATURES`, frame transforms |
| **EXECUTION METADATA** | **Yes** (executability only) | Tool registry, grammar, horizons, `ExperimentSpec` schema |

**Critical rule:** The future generator must not mistake a human ontology label for independent observational creativity.

---

## 3. OPR Source-of-Truth Rule

Every autonomous proposition requires auditable `observation_provenance` (`artifacts/01_opr_source_of_truth_rule.json`):

**Minimum payload:**
1. **evidence_anchor** — experiment node, tool, version, data cutoff
2. **empirical_artifacts** — ≥1 numeric/structural trace (not label-only)
3. **structural_context** — population/outcome/horizon slice
4. **surprise_basis** — empirical comparison making evidence non-trivial

**Insufficient alone:** `OBS_*`, `GAP_*`, `question_template_id`, `ResearchNeedType`, gap membership.

**Reject if:** Provenance contains only ontology labels; surprise cites template name without empirical delta.

---

## 4. PropositionRecord Contract

Versioned schema `proposition_record_v1` (`artifacts/02_proposition_record_contract.json`):

| Field | Audit / Scientific Purpose |
|-------|---------------------------|
| `proposition_id` | Dedup + lineage |
| `observation_provenance` | Source-of-truth chain |
| `motivating_observation` | What was empirically seen |
| `surprise_or_uncertainty` | Why non-trivial |
| `scientific_question` | Evidence-derived question |
| `canonical_proposition_core` | Executable semantic identity |
| `population_context`, `explanatory_relation`, `outcome`, `horizon` | Falsifiable claim structure |
| `falsifiable_expectation`, `null_competing_explanation`, `disconfirming_observation_spec` | Falsification birthright |
| `evidence_required`, `execution_requirements` | Test design + executability |
| `epistemic_status`, `confidence` | Lifecycle without conflating market edge |
| `semantic_parent_id`, `generation_lineage` | Evidence-responsive forks |
| `template_independence_audit` | Novelty vs catalog |
| `leakage_audit` | Hidden-benchmark / prior-run contamination check |
| `executability_status` | Grammar validation outcome |
| `birth_certificate` | Eight-question autonomous qualification |

**Status:** Design only — not implemented in production.

---

## 5. Scientific Birth Certificate

Mandatory eight-question audit (`artifacts/03_scientific_birth_certificate.json`):

1. What exactly was observed?
2. Why surprising / unresolved / asymmetric / conflicting?
3. What scientific question arose?
4. What proposition is being tested?
5. What evidence would support it?
6. What evidence would weaken or falsify it?
7. Why not merely a template reformulation?
8. What executable experiment could test it?

**Autonomous qualification:** All eight pass AND classification ∉ {TEMPLATE_INSTANCE, INSUFFICIENT_EVIDENCE}.

If any answer cannot be derived from recorded evidence → **not autonomous**.

---

## 6. Template-Independence Evaluator

Frozen semantic isomorphism audit (`artifacts/04_template_independence_evaluator.json`):

| Classification | Counts Toward Autonomous Creativity? |
|----------------|--------------------------------------|
| TEMPLATE_INSTANCE | No |
| TEMPLATE_REFRAME | No |
| TEMPLATE_ADJACENT | Yes (report separately) |
| SCIENTIFICALLY_NOVEL | Yes |
| INSUFFICIENT_EVIDENCE | No — reject |

**Decision tree:** Structural match + semantic similarity + `new_observational_axis_documented` flag. Thresholds frozen from catalog structure analysis — **not** from BB-Prop-01 outcomes.

**Anti-optimization:** Generator must not read evaluator thresholds during candidate generation.

---

## 7. OBS/GAP Laundering Protection

Failure mode blocked (`artifacts/05_obs_gap_laundering_protection.json`):

```
RAW EVIDENCE → OBS/GAP code → generator decodes code → "new" question
```

**Six detection tests:** code-only provenance, decode-without-read, paraphrase-label, reverse-causality, statistically-equivalent paths (raw vs code-only A/B), GAP-family lock-in.

**Mandatory 3I.2 contract:**
- Primary inputs: raw evidence + execution metadata only
- Write order: raw → provenance → surprise → proposition → optional ontology tags
- `evidence_hash` (SHA256) stored for replay without reading labels

---

## 8. Executability Boundary

(`artifacts/06_executability_boundary.json`)

**Allowed (make testable, not interesting):** columns, legal population/outcome expressions, horizons, tool capabilities, `ExperimentSpec` schema, budget limits.

**Forbidden as generative priors:** GAP/OBS semantics, template question text, planner weights, novelty bonus, hidden phenomena, `ROOT_CONFIG`, horizons/populations tuned from prior BB runs.

**Separation:** Scientific synthesis first → executability adapter second. Never filter observations to match template tool paths before synthesis.

---

## 9. Generation-Budget Policy

Pre-registered limits (`artifacts/07_generation_budget_policy.json`):

| Limit | Frozen v1 Value | Rationale |
|-------|-----------------|-----------|
| max_propositions_per_observation | 3 | sqrt(contrast) cap; prevents combinatorial spam |
| max_propositions_per_research_step | 5 | Sparse autonomous layer |
| max_total_propositions_per_session | 50 | Hard ceiling |
| max_survivors_after_dedup | 15 | Quality over volume |
| semantic_duplicate_threshold | 0.90 embedding | Collapse near-duplicates |
| min_raw_statistic_citations | 1 | Grounding floor |

**Threshold selection rule (when exact values unknown):** Proportional to evidence surface (observation clusters), never to desired hit rate.

**Silence is valid:** Explicit `NO_PROPOSITION_EMITTED` with reason code.

**Pathological spam:** >50 propositions OR grounding rate <20% OR template_instance rate >60% (any two criteria).

---

## 10. BB-Prop-01 Frozen Design

Four-zone architecture (`artifacts/08_bb_prop_01_frozen_manifest.json`):

```
┌─────────────────────────────────────────────────────────────┐
│  A: Development Set (60% panel, answers visible)            │
│     → unit tests, grounding pipeline, laundering tests        │
├─────────────────────────────────────────────────────────────┤
│  B: Frozen Blind Panel (40% holdout, no hidden answers)     │
│     → generator runs once per frozen commit                   │
├─────────────────────────────────────────────────────────────┤
│  C: Hidden Phenomenon Set (8–15 independent phenomena)      │
│     → NEVER in generator scope                                │
├─────────────────────────────────────────────────────────────┤
│  D: Offline Evaluator                                       │
│     → compares B PropositionRecords vs C; abstract report only│
└─────────────────────────────────────────────────────────────┘
```

**Protocol:** Freeze commit SHA → run on B → seal artifacts → D evaluates → abstract report. One-shot blind eval per commit.

---

## 11. Hidden Benchmark Protection Policy

(`artifacts/09_hidden_benchmark_protection_policy.json`)

**Never in generator scope:** Zone C definitions, per-phenomenon match scores, near-miss proposition text, embedding neighbors of hidden phenomena.

**Allowed feedback:** Aggregate rates only — e.g. `observational_grounding_rate: 0.72`, `hidden_convergence_class: PARTIAL`.

**Forbidden feedback:** "Phenomenon PHEN_07 matched PROP_abc123" or "Try horizon 10d for phenomenon class X".

**Core invariant:** Failed blind benchmark must not teach the generator the hidden answer in the next iteration.

---

## 12. Creativity / Quality / Usefulness Metrics

Pre-registered (`artifacts/10_creativity_metrics_preregistration.json`):

**Primary rates (not counts):** observational grounding, falsifiability, executability, semantic duplicate, template-instance/reframe/adjacent/novel, propositions per useful survivor, abandoned-hypothesis, evidence-responsive redirection, hidden convergence class, research-budget efficiency.

**Evaluation separation:**

| Dimension | Question | Novel-but-false OK? |
|-----------|----------|---------------------|
| Scientific novelty | New relative to priors? | Yes |
| Scientific quality | Grounded, falsifiable, executable? | N/A |
| Empirical usefulness | Evidence supports? | False = not failure |
| Market edge | Predictive/actionable value? | Deferred |

---

## 13. Negative / Adversarial Controls

Ten pre-registered controls (`artifacts/11_negative_adversarial_controls.json`):

- Pure noise → zero propositions
- Weak random asymmetry → tentative or silence
- Duplicated evidence → dedup collapse
- Same evidence, different tools → one survivor
- Template-shaped observation → TEMPLATE_INSTANCE, not NOVEL
- Conflicting evidence → document conflict or silence
- Strong anomaly, no executable test → NOT_EXECUTABLE, no illegal spec
- Competing anomalies, limited budget → ranked selection
- Ontology-only input → zero autonomous propositions
- **Silence is valid** when birth certificate incomplete

---

## 14. Evidence-Responsive Lineage Design

(`artifacts/12_evidence_responsive_lineage.json`)

**Allowed transitions (evidence-triggered only):** SUPPORT, WEAKEN, FALSIFY, NARROW, BROADEN, CHANGE_POPULATION/OUTCOME/HORIZON, SEEK_COUNTEREXAMPLE, ABANDON, FORK_NEW_EXPLANATION.

**Forbidden:** Fixed catalog progression, planner-driven rotation, GAP change without new observation.

**Audit:** Append-only lineage graph; immutable prior versions; forks require fresh birth certificate.

**Not implemented in 3I.1 or initial 3I.2.**

---

## 15. Falsification Birthright

(`artifacts/13_falsification_birthright.json`)

Every autonomous proposition born with:
- `null_competing_explanation`
- `falsifiable_expectation` (direction, threshold, population)
- **`disconfirming_observation_spec`** — "What observation would make this less believable?"

**Future Challenger connection (design only):** `disconfirming_observation_spec` → `ChallengerSeed` adapter. OPR owns spec at birth; Challenger owns counterexperiment design later. Not integrated now.

---

## 16. Minimal 3I.2 Implementation Boundary

(`artifacts/14_minimal_3i2_implementation_boundary.json`)

**Smallest path:**

```
CROSS_SECTIONAL_DISPERSION_ANOMALY (raw tool metrics)
    → CONTRAST_TO_PROPOSITION (single synthesis mechanism)
    → PropositionRecord
    → existing ExperimentSpec validation
```

**Why dispersion class:** Generic observability via existing tools; falsifiable via existing grammar; **not** chosen because of hidden edge.

**Bounded relation slots:** predicts, modulates, interacts_with, regime_conditional, contrasts_with — **not** unconstrained open grammar.

**New modules (3I.2):** `opr_bridge/evidence_ingest`, `surprise_detector`, `proposition_synthesizer`, `proposition_record`, `executability_adapter`.

**No changes:** templates, OBS/GAP semantics, planner, novelty logic, Challenger, discovery engine.

---

## 17. Readiness Gate

**Verdict: READY_FOR_MINIMAL_OPR**

All 16 contract artifacts complete. Production systems unmodified. One prerequisite remains for first blind run (not blocking 3I.2 minimal implementation):

---

## 18. Remaining Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Zone C hidden phenomena not yet populated | Medium | Populate in protected store before first zone B run |
| Template-independence threshold miscalibration | Medium | 10% human adjudication; tune on zone A only |
| Dispersion class correlates with T8 template family | Low | Honest TEMPLATE_INSTANCE labeling acceptable in 3I.2 |
| Surprise detector calibration leakage | Low | Freeze thresholds in manifest hash pre-zone-B |
| Aggregate buckets correlate 1:1 with phenomena | Low | Coarse convergence class only; no per-phenomenon report |

---

## Final Questions

### A. Can a future PropositionRecord prove where its idea came from?

**Yes.** `observation_provenance` requires evidence anchor + empirical artifacts + structural context + surprise basis with `evidence_hash`. Birth certificate Q1–Q2 must cite concrete statistics. OBS/GAP alone is insufficient. Auditor can replay surprise from stored evidence without reading ontology labels.

### B. Can we distinguish a genuinely new scientific question from a sophisticated permutation of our own templates?

**Yes.** Frozen template-independence evaluator classifies INSTANCE / REFRAME / ADJACENT / NOVEL / INSUFFICIENT_EVIDENCE using structural match + semantic similarity + documented new observational axis. Laundering tests block ontology-decode paths. Only ADJACENT and NOVEL count toward autonomous creativity; ADJACENT reported separately.

### C. Can BB-Prop-01 evaluate hidden-edge convergence without teaching the generator what the hidden edge is?

**Yes.** Zone C isolated from generator code/prompts/configs. Zone D reports abstract capability buckets only (`hidden_convergence_class: PARTIAL`, grounding rates). Per-phenomenon mappings, near-miss text, and feature hints forbidden. One-shot eval per commit; log redaction on zone C matches. Failures diagnose capability gaps, not answers.

---

**STOP.** Phase 3I.2 not implemented.

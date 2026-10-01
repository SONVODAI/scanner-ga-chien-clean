# Phase 3I.6 — Autonomous Proposition Lifecycle & Evidence-Responsive Reasoning Readiness

**Mode:** AUDIT + DESIGN ONLY — no lifecycle implementation  
**3I.5 verdict accepted:** PRIORITIZE_PASS  
**Capability chain today:** OBSERVE → WONDER → PROPOSE → PRIORITIZE  
**Target chain:** → TEST → INTERPRET → UPDATE → DECIDE

---

## 1. Branch / HEAD / Git Status

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i6-lifecycle-design-aad2` |
| Base | `main` (merged research stack) |
| OPR/PRIORITIZE | On branches `cursor/phase-3i1-*` through `cursor/phase-3i5-*` (referenced, not merged) |
| This phase | Diagnostics-only under `diagnostics/phase_3i6_lifecycle_design/` |
| Production | Unchanged — no deployment |

---

## 2. Existing Lifecycle-Capability Audit

### Merged research stack (on `main`)

| Component | Path | Lifecycle role today |
|-----------|------|---------------------|
| `ExperimentSpec` | `research_state.py` | Defines bounded experiments; content-hash dedup |
| `execute_research_experiment` | `research_tools.py` | Runs tools (partition_group_compare, decompositions, sensitivity) |
| `ResearchGraph` | `research_graph.py` | Append-only nodes: OBSERVATION → QUESTION → EXPERIMENT → CONCLUSION |
| `interpret_tool_result` | `research_interpreter.py` | Produces `ResearchAssessment` from `ToolResult` + observation codes |
| `generate_action_candidates` | `research_actions.py` | GAP-code → frozen template → tool mapping (24+ templates) |
| `plan_next_action` | `research_planner.py` | Weighted scoring (gap 3.0, falsify 4.0, novelty 2.0, stop 5.0, abandon 4.5) |
| `run_experiment_and_plan` | `research_controller.py` | Execute → interpret → plan → spawn next experiment |
| `ResearchAssessment` | `research_assessment.py` | Branch findings, gaps, falsification targets; `validated=False` always |
| `run_challenger` | `challenger.py` | Phase 2 candidate robustness battery — fixed tests |
| `derive_scientific_status` | `hypothesis.py` | Discovery pipeline status — not proposition lifecycle |

### OPR stack (3I branches, PRIORITIZE_PASS)

| Component | Path | Lifecycle role today |
|-----------|------|---------------------|
| `PropositionRecord` | `opr_bridge/proposition_record.py` | Birth record; `epistemic_status=HYPOTHESIS` write-once |
| `DisconfirmingObservationSpec` | same | Falsification path at birth — never evaluated post-experiment |
| `executability_adapter` | `opr_bridge/executability_adapter.py` | Maps record → `ExperimentSpec` draft |
| `EvidenceLineage` | `prioritized_pipeline.py` | Pre-emission: 22 events → 1 proposition group |
| `scientific_identity` | `opr_bridge/scientific_identity.py` | Pre-emission grouping; fork boundary helper |
| `research_proposition_core` | `research_proposition_core.py` | `cores_same_question`, identity keys |

### Pre-existing design (3I.1 artifact 12)

`12_evidence_responsive_lineage.json` defines SUPPORT/WEAKEN/FALSIFY/NARROW/BROADEN/FORK/ABANDON transitions — **design only**, no engine.

---

## 3. Reusable vs Missing Components

### Reusable without modification

- **PropositionRecord v1** — complete birth certificate, falsification spec, provenance
- **ExperimentSpec + tool registry** — production-tested execution path
- **executability_adapter** — syntax bridge to first test
- **ResearchGraph** — append-only experiment lineage, ABANDON/RESOLVED node status
- **ResearchAssessment** — partial experiment reading (branch-scoped)
- **3I.5 EvidenceLineage** — pre-emission evidence aggregation model
- **scientific_identity / cores_same_question** — mutation vs rescue detection
- **3I.1 transition vocabulary** — design precedent for lifecycle actions

### Template-bound or disconnected

- **research_actions** — next actions come from GAP codes → frozen 24-template catalog, not proposition evidence state
- **research_planner** — scores template candidates with fixed weights; not evidence-class-driven
- **Challenger** — reads Phase 2 ledger; ignores `disconfirming_observation_spec`
- **derive_scientific_status** — separate enum for discovery, not `EpistemicStatus`
- **ResearchAssessment.validated/actionable** — placeholders never updated
- **OPR ↔ controller** — no wire from `experiment_spec_draft` to `ResearchGraph.add_experiment()`

### Missing (must build for lifecycle)

1. **PropositionExperimentInterpreter** — compare experiment result to `falsifiable_expectation` + `disconfirming_observation_spec`
2. **EpistemicUpdateRecord** — append-only state transition
3. **ResearchDecisionRecord** — auditable decision closure (contract artifact 04)
4. **LifecycleDecisionEngine** — evidence → next action without template menu
5. **proposition_id join key** on graph nodes
6. **Post-emission evidence lineage** — link experiment results to proposition ledger
7. **FORK_NEW_EXPLANATION path** — design complete, implementation deferred

---

## 4. Proposition Epistemic-State Design

**Minimum vocabulary** (artifact `01_proposition_epistemic_state_model.json`):

| State | Meaning |
|-------|---------|
| **PROPOSED** | Born with birth certificate; no lifecycle test yet |
| **UNDER_TEST** | Experiment spawned from proposition; result pending |
| **SUPPORTED** | Supporting evidence meets expectation; no unresolved contradiction |
| **WEAKENED** | Partial/quality-limited support |
| **CONFLICTED** | Valid evidence points both ways |
| **FALSIFIED** | Disconfirm threshold crossed |
| **UNRESOLVED** | Non-informative experiments; belief unchanged |
| **ABANDONED** | Explicit stop — successful when warranted |

**Excluded:** trading states, `READY_FOR_OOS`, template classifications.

**Principle:** Original `PropositionRecord` at birth remains **immutable**. State changes via append-only `EpistemicUpdateRecord`.

---

## 5. Evidence Semantics

| Class | Definition | Belief effect |
|-------|------------|---------------|
| **SUPPORTING_EVIDENCE** | Aligns with `falsifiable_expectation` within tolerance | → SUPPORTED (if quality sufficient) |
| **DISCONFIRMING_EVIDENCE** | Crosses `disconfirming_observation_spec` threshold | → WEAKENED or FALSIFIED |
| **CONTRADICTORY_EVIDENCE** | Multiple valid opposing directions | → CONFLICTED |
| **NON_INFORMATIVE_EVIDENCE** | Valid run, no resolution | → UNRESOLVED or no change |
| **INVALID_EVIDENCE** | Leakage, failure, bad sample | Excluded from update |

**Forbidden:** counting experiment execution alone as support; non-informative → support collapse.

Full spec: artifact `02_evidence_semantics.json`.

---

## 6. Belief Representation Recommendation

**Adopt: Categorical epistemic state + append-only evidence ledger + ordinal balance**

| Alternative | Verdict |
|-------------|---------|
| Categorical state | **Adopt** — primary, auditable |
| Ordinal evidence balance | **Adopt** — support/disconfirm counts, quality-weighted |
| Evidence ledger without scalar | **Adopt** — full audit trail |
| Bayesian probability | **Reject** — pseudo-precision, prior assumptions |
| Scalar confidence only | **Reject** — obscures contradiction |

No numeric probability at this stage. `PropositionRecord.confidence=LOW` at birth is not updated by a hidden scalar — explicit evidence classes drive transitions.

Artifact: `03_belief_representation.json`.

---

## 7. Evidence Aggregation Design

| Scenario | Rule |
|----------|------|
| Independent replication | Quality-weighted; same episode ≠ independent |
| Repeated same-episode evidence | Logged separately; counts once for independence |
| Contradictory episodes | → CONFLICTED; increases falsification priority |
| Sample-size differences | Quality tier (HIGH/MEDIUM/LOW) gates influence |
| Correlated evidence | Deduplicate by evidence_hash / experiment content_hash |
| Stale evidence | Flag regime/context change; may downgrade weight |
| Raw count | **Must not** become confidence |

Aggregation produces **ordinal balance** (supporting_independent_count, disconfirming_independent_count, contradiction_flag) — not a probability.

---

## 8. Falsification-First Design

### Current state

- **At birth:** `disconfirming_observation_spec` populated (3I.2/3I.3) — e.g. quintile ordering reversal, spread < 0.5
- **At execution:** `research_interpreter` emits `possible_falsification_targets` from OBS codes — **template-bound**, not proposition-scoped
- **Challenger:** fixed robustness battery — **does not read** `disconfirming_observation_spec`

### Future mechanism (design)

```
PropositionRecord.disconfirming_observation_spec
  → FalsificationCandidateGenerator (NOT Challenger integration yet)
    → ranked experiments that could cross disconfirm threshold
    → must differ from last supportive test (anti-confirmation-bias)
    → bounded to legal ExperimentSpec grammar
```

**Key question the Brain must ask:** *"What is the most informative feasible experiment that could prove my current explanation wrong?"*

Ranking signals (pre-register): proximity to disconfirm threshold, untested operational_test dimensions, quality/feasibility gates. **Not** rerunning identical partition test after support.

---

## 9. Alternative-Explanation Design (FORK_NEW_EXPLANATION)

When contradictory/disconfirming evidence rejects core relation but supports alternative mechanism:

```
Evidence C + unresolved contradiction X
  → new SemanticProjection (must differ on cores_materially_different)
  → new PropositionRecord with:
      - semantic_parent_id = original proposition_id
      - fresh birth certificate
      - fresh disconfirming_observation_spec
      - template_independence audit
      - observation/evidence provenance from motivating evidence C
```

**Not implemented.** Fork is a **new proposition**, not a silent edit. Original remains in lineage graph.

---

## 10. Redirection Semantics

### Genuine redirection (required causal chain)

```
specific evidence (experiment_id + metrics)
  → specific unresolved contradiction (named in interpretation)
  → specific change in scientific uncertainty (documented)
  → new research action (ResearchDecisionRecord.chosen_next_action)
```

### Mechanical progression (forbidden)

- Auto-advance to next template in GAP family
- Horizon rotation because planner weights favor `horizon_comparison`
- Population narrowing after failure without evidence slice citation
- Field change without experiment diagnostic motivation

**Test:** Remove the cited evidence from the decision record — if the same action would still fire, it is mechanical not evidence-responsive.

---

## 11. Abandonment Semantics

**ABANDON is a successful research outcome** when:

| Condition | Example |
|-----------|---------|
| Falsification succeeds | Disconfirm threshold crossed on high-quality experiment |
| Repeated contradiction unresolved | CONFLICTED after budget-limited falsification attempts |
| Untestable | Executability permanently blocked with no legal reformulation |
| Information value collapse | NON_INFORMATIVE streak; expected information gain below floor |
| Superseded | Fork with stronger evidence subsumes original |

Abandon requires: `reason_code`, `last_evidence_ref`, `ResearchDecisionRecord` with rejected continue/seek actions documented.

---

## 12. Anti-Confirmation-Bias Controls

| Risk | Control |
|------|---------|
| Repeated supportive tests | Track attempted operational_tests; penalize duplicates in falsification ranking |
| Ignoring contradictory episodes | CONFLICTED state mandatory when valid opposing evidence exists |
| Post-hoc population narrowing | NARROW requires pre-registered slice hypothesis + LEGITIMATE_SCIENTIFIC_MUTATION |
| Horizon change after failure | CHANGE_HORIZON requires temporal evidence artifact |
| Threshold movement | Frozen disconfirm thresholds in birth record — immutable |
| Outcome redefinition | Outcome change = FORK, not edit |
| Endless hypothesis rescue | Mutation vs rescue boundary (§13) |
| Non-significance as support | NON_INFORMATIVE must not increment supporting_count |
| Correlated evidence as replication | Independence gate on evidence_hash / episode |

BB-Life-01 adversarial sequences test each control.

---

## 13. Mutation vs Rescue Boundary

| | LEGITIMATE_SCIENTIFIC_MUTATION | HYPOTHESIS_RESCUE |
|--|-------------------------------|-------------------|
| **Trigger** | Evidence motivates new question | Disconfirming evidence followed by silent edit |
| **Identity** | New proposition_id; `semantic_parent_id` link | Same proposition_id; fields changed |
| **Audit** | New birth certificate + template audit | Original claim overwritten |
| **Detection** | `cores_materially_different` = True | Same `scientific_identity_key` after disconfirm |
| **History** | Both propositions preserved | Violates append-only lineage |

**Rule:** Original PropositionRecord is **immutable**. Any change to scientific question, population, outcome, or horizon after birth → **FORK** or explicit **ABANDON**, never in-place edit.

---

## 14. Append-Only Research Lineage Design

```
PropositionRecord (immutable birth)
  → ExperimentNode (ResearchGraph, proposition_id join)
    → ToolResult
      → EvidenceInterpretationRecord (evidence class)
        → EpistemicUpdateRecord (state transition)
          → ResearchDecisionRecord (next action + rationale)
            → optional child PropositionRecord (FORK)
```

**Nothing overwrites** the original scientific claim. Every change of mind is a new record with `parent_decision_id` / `semantic_parent_id` links.

Extends 3I.1 artifact 12 `lineage_record_schema` with `ResearchDecisionRecord` from artifact 04.

---

## 15. ResearchDecisionRecord Contract

Minimal auditable fields (artifact `04_research_decision_record_contract.json`):

- `proposition_id`, `prior_epistemic_state`, `resulting_epistemic_state`
- `evidence_considered[]` with evidence_class + quality_tier
- `evidence_excluded[]` with reasons
- `epistemic_interpretation` (falsification_status, contradiction_status)
- `candidate_next_actions[]`, `chosen_next_action`, `rejected_actions[]`
- `lineage.triggered_by_experiment_id`

**Forbidden fields:** expected_profit, hidden_phenomenon_match, template_progression_index.

---

## 16. Current Decision-Autonomy Audit

### What is hard-coded today

| Source | Hard-coding |
|--------|-------------|
| GAP codes | `TIME_DISTRIBUTION` → `date_decomposition` template |
| research_actions | 24+ `question_template_id` values with fixed tool + inputs |
| research_planner | Fixed weights; highest score wins among template candidates |
| Challenger | Fixed robustness suite (leave-one-date, concentration, etc.) |
| Branch rules | `NodeStatus.ABANDONED` on fragility observation codes |

### Architectural change required

Replace **template menu selection** with **evidence-state-driven decision**:

1. `PropositionExperimentInterpreter` → evidence class + epistemic interpretation
2. `LifecycleDecisionEngine` → maps (state, evidence_class, contradiction, falsification_status) → bounded action set
3. Action set still compiles to `ExperimentSpec` via legal grammar — **tools bound execution, not scientific intent**
4. `ResearchDecisionRecord` closes each step with rejected alternatives

The existing planner remains for **branch exploration** within template research; proposition lifecycle needs a **parallel decision path** joined by `proposition_id`.

---

## 17. BB-Life-01 Benchmark Design

**Purpose:** Blind test of lifecycle reasoning — not proposition generation breadth.

| Zone | Role |
|------|------|
| A | Public interpretation rules (frozen) |
| B | Frozen propositions + synthetic result sequences |
| C | Hidden adversarial trajectories (evaluator only) |
| D | Post-hoc capability scoring |

**10 adversarial sequences:** support-then-contradict, correlated weak support, single falsification, conflicting episodes, non-informative, invalid/leaky, post-hoc narrowing temptation, horizon-change temptation, stronger alternative fork, justified abandon.

Full design: artifact `05_bb_life_01_benchmark_design.json`.

**Hidden-answer protection:** Evaluator never imported by lifecycle engine; failure feedback is capability-level ("hypothesis_rescue_detected"), not "correct_action=LIFE-03-B".

---

## 18. Metrics

| Metric | Intent |
|--------|--------|
| evidence_interpretation_accuracy | Correct evidence class assignment |
| contradiction_recognition_rate | CONFLICTED when warranted |
| falsification_seeking_rate | Seek disconfirm when partial support |
| inappropriate_confirmation_seeking_rate | Re-test for support after falsify |
| hypothesis_rescue_rate | **Must be 0** |
| justified / unjustified abandonment | Abandon when warranted vs premature |
| evidence_responsive_redirection_rate | Redirect with evidence citation |
| lineage_completeness | All transitions have experiment + evidence refs |
| scientific_decision_quality | Rubric-based, not answer matching |
| research_budget_efficiency | Information gain per experiment |

**Anti-reward:** Do not reward keeping propositions alive or raw experiment count.

---

## 19. Adversarial Cases (BB-Life-01)

1. Strong initial support → high-quality contradiction  
2. Weak support repeated many times (correlated)  
3. One high-quality falsification event  
4. Conflicting market episodes  
5. Non-informative experiment  
6. Invalid/leaky experiment  
7. Tempting post-hoc population narrowing  
8. Tempting horizon change after failure  
9. Alternative explanation with stronger evidence  
10. Proposition that should simply be abandoned  

---

## 20. Readiness Gate

### **PARTIALLY_READY**

**Rationale:** Execution infrastructure (`ExperimentSpec`, tools, graph), proposition birth (`PropositionRecord`, falsification spec), pre-emission lineage (3I.5), and design contracts (3I.1 artifact 12, 3I.6 artifacts) are sufficient to specify one narrow lifecycle experiment.

**Exactly one prerequisite missing:**

### **PropositionExperimentInterpreter**

A read-only-then-auditable module that:
- Accepts `PropositionRecord` + `ToolResult` from `partition_group_compare`
- Compares metrics to `falsifiable_expectation` and `disconfirming_observation_spec`
- Emits evidence class (SUPPORTING / DISCONFIRMING / NON_INFORMATIVE / INVALID)
- Does **not** yet mutate state or choose next action

Without this bridge, the loop stops at experiment execution.

---

## 21. Minimal 3I.7 Boundary (Proposal Only)

**If PARTIALLY_READY → smallest 3I.7 experiment:**

```
Frozen proposition (3I.5 representative, 2026-08-02)
  → execute experiment_spec_draft (partition_group_compare)  [existing]
  → PropositionExperimentInterpreter v1  [NEW — single tool, single proposition family]
  → one EpistemicUpdateRecord  [NEW — append-only]
  → one ResearchDecisionRecord  [NEW — CONTINUE | SEEK_FALSIFICATION | ABANDON]
  → lineage JSON artifact  [NEW — no graph integration yet]
```

**Explicitly NOT in 3I.7:**
- General lifecycle engine
- Challenger integration
- Alternative-explanation generator
- Planner integration
- Second observation class
- Belief probability scalar

---

## 22. Remaining Risks

| Risk | Mitigation |
|------|------------|
| Template planner absorbs lifecycle | Parallel decision path with proposition_id join |
| Hypothesis rescue via silent edits | Immutable birth record + cores_materially_different gate |
| Confirmation bias in falsification ranking | Pre-register anti-duplicate operational_test rule |
| OPR not on main | Merge 3I.1–3I.5 before 3I.7 execution |
| NON_INFORMATIVE → SUPPORT collapse | Explicit evidence class gate in interpreter |
| Hidden benchmark tuning | BB-Life-01 Zone C firewall; capability-level feedback only |
| Over-engineering belief | Reject Bayesian; ledger + categorical state only |

---

## Final Answers

### A. Can Mr.BOT currently change its scientific mind because of evidence, or only generate and rank questions?

**Only generate and rank questions.**

Mr.BOT can OBSERVE, WONDER, PROPOSE, and PRIORITIZE. `PropositionRecord.epistemic_status` is set to `HYPOTHESIS` at birth and **never updated**. `ResearchAssessment.validated` is always `False`. The research controller plans next **template experiments** from GAP codes — not next **epistemic actions** from proposition evidence. No experiment result is compared to `disconfirming_observation_spec`.

### B. What is the smallest missing mechanism for genuine evidence-responsive reasoning?

**PropositionExperimentInterpreter** — a deterministic, auditable comparator that classifies one experiment's outcome against the proposition's own `falsifiable_expectation` and `disconfirming_observation_spec`, producing an evidence class and interpretation record. Everything else (execution, birth record, graph, decision contract) is design-ready or reusable.

### C. How will we distinguish a researcher changing its mind from a system walking a fixed decision tree?

| Fixed decision tree | Evidence-responsive reasoning |
|--------------------|------------------------------|
| Next action from GAP → template catalog | Next action from evidence class + epistemic state |
| Same template sequence regardless of result | `ResearchDecisionRecord` cites specific experiment metrics |
| Proposition fields edited in place | Immutable birth + append-only updates/forks |
| `validated=False` forever | `EpistemicUpdateRecord` chain visible |
| Removing evidence doesn't change decision | Counterfactual: remove cited evidence → decision must change |
| BB-Life-01 hypothesis_rescue_rate > 0 | hypothesis_rescue_rate = 0; lineage shows FORK not edit |

**Audit test:** Every `ResearchDecisionRecord.chosen_next_action.reason` must reference `evidence_considered[].experiment_node_id` and a proposition-specific threshold comparison — not `question_template_id` or GAP code alone.

---

## Artifacts

| File | Content |
|------|---------|
| `artifacts/01_proposition_epistemic_state_model.json` | Minimum state vocabulary |
| `artifacts/02_evidence_semantics.json` | Five evidence classes |
| `artifacts/03_belief_representation.json` | Ledger + categorical recommendation |
| `artifacts/04_research_decision_record_contract.json` | Decision audit contract |
| `artifacts/05_bb_life_01_benchmark_design.json` | Lifecycle blind benchmark |
| `run_audit.py` | Read-only infrastructure audit |
| `artifacts/06–09_*.json` | Generated audit outputs |

**STOP.** No lifecycle implementation. No deployment. No next phase execution.

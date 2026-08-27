# Phase 3I.8 — Autonomous Falsification Experiment Selection Readiness

**Mode:** AUDIT + DESIGN ONLY — no second real experiment executed  
**3I.7 verdict accepted:** LIFECYCLE_PASS  
**Phase 3I.8 verdict:** **PARTIALLY_READY**

---

## 1. Branch / HEAD / Git Status

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i8-falsification-selection-aad2` |
| Base | `cursor/phase-3i7-minimal-lifecycle-aad2` |
| Mode | Diagnostics-only under `diagnostics/phase_3i8_falsification_selection/` |
| Production | Unchanged — no deployment, no second ToolResult read |
| Second experiment executed | **No** |

---

## 2. 3I.7 Lineage Integrity Audit

Preserved frozen artifacts from `diagnostics/phase_3i7_minimal_lifecycle/artifacts/` without regeneration.

| Check | Result |
|-------|--------|
| proposition_id | `prop-efb650d9bd5c451f` |
| proposition_hash stored vs recomputed | **Match** (`c3aab7de80fdb9e56b7be68d517ec0e4792b711ec9772638143df3cfe4e39c9b`) |
| lineage proposition_hash | **Match** |
| epistemic_update_id | `epu-5a7bec6e47ec` |
| decision_id | `dec-c92fb28fdc13` |
| decision cites update | **Yes** |
| evidence_class | SUPPORTING |
| epistemic transition | HYPOTHESIS → **SUPPORTED** |
| chosen_next_action | **SEEK_FALSIFICATION** |
| proposition_immutable | true |
| lineage_hash | present |

**Chain intact:** PropositionRecord → ExperimentSpec → ToolResult → InterpretationContract → EpistemicUpdateRecord → ResearchDecisionRecord → SEEK_FALSIFICATION.

---

## 3. Contract-Hash Discrepancy Assessment

| Artifact | contract_hash |
|----------|---------------|
| `03_interpretation_contract.json` (pre-freeze) | `3474a096aa6ee9c57ee1120f4a41398b08307038b23220016fa6bc9fddff77e2` |
| `09_append_only_lineage.json` (runtime) | `6cde6297c37276cdc22b6f06975e7eff5c928223095ac63aa10e864e809ff9e7` |

**Root cause:** `build_interpretation_contract()` embeds `frozen_at = utc_now_iso()` in the hash body. `run_phase_3i7.py` freezes the contract once (artifact 03), then `run_minimal_lifecycle()` rebuilds it at execution with a new timestamp (~8s later).

**Scientific impact:** None — rule content is identical (supporting, disconfirming, transition, decision mappings all match).

**Provenance impact:** Lineage node does not hash-link to the pre-freeze artifact; `post_hoc_audit.contract_hash_matches = false`.

**Design recommendation (no production change this phase):**
- Lineage should reference artifact 03 `contract_hash` directly via `interpretation_contract_ref`
- OR pass pre-built `InterpretationContract` into `run_minimal_lifecycle()`
- OR exclude `frozen_at` from hash body (store separately)

Future falsification lineage must use the **original frozen contract hash**, not a regenerated one.

---

## 4. Scientific Falsification Target

**Proposition:** Does cross-sectional rs_spread dispersion tier predict differential forward t5_return across the market cross-section?

**Core empirical claim that must fail for disbelief:** High-rs_spread quintile mean t5_return exceeds low-rs_spread quintile (positive contrast direction).

**Pre-registered disconfirm test:** `partition_group_compare median_spread of t5_return across rs_spread quintiles <= 0` or group rank reversal.

**Null competing explanation:** Small-sample artifact or market-wide level effects on focal date **2026-08-02**.

| Vulnerability axis | Falsification strength | Notes |
|--------------------|------------------------|-------|
| Directional reversal | **STRONG** | Direct operationalization of disconfirming_observation_spec |
| Replication failure | MODERATE | Independent dates fail to reproduce spread |
| Episode instability | MODERATE | Effect disappears when focal date excluded |
| Population instability | MODERATE | Symbol dominance; robustness not reversal |
| Alternative explanation (date artifact) | MODERATE | Targets stated null |
| Context instability via narrowing | WEAK / **REJECT** | Rescue risk |
| Horizon instability | **INVALID** | Changes proposition meaning |
| Statistical non-resolution | NON-FALSIFICATION | Would not weaken SUPPORTED |

Not all axes are equally strong. Directional reversal via the pre-registered partition contrast is the strongest falsification target.

---

## 5. Existing Candidate-Generation Capability Audit

### Reusable without GAP/template priors

| Component | Reuse for falsification |
|-----------|-------------------------|
| `disconfirming_observation_spec` | Birth commitment — defines what disconfirms |
| `executability_adapter` | Confirmatory spec only (partition_group_compare) |
| `ExperimentSpec` + `compute_experiment_content_hash` | Dedup vs prior experiment |
| `research_grammar` PopulationSpec FILTER | Legal date exclusion (`trade_date != focal`) |
| `partition_group_compare` + quintile extraction | Same interpreter path as 3I.7 |
| `proposition_experiment_interpreter` | Classifies partition metrics only |
| `scientific_identity` / `cores_same_question` | Rescue detection |
| 3I.5 EvidenceLineage | 22 pre-emission events for independence context |

### Disconnected / template-bound (cannot reuse for OPR autonomy)

| Component | Issue |
|-----------|-------|
| `research_actions` FALSIFY_* | Triggered by GAP codes from `research_interpreter`, not proposition vulnerability |
| `research_planner` | Fixed weights on template candidates |
| `challenger.run_challenger` | Phase 2 ledger; ignores `disconfirming_observation_spec` |

### Missing

1. **`FalsificationCandidateGenerator`** — proposition-scoped; reads disconfirming_observation_spec + evidence state
2. **SEEK_FALSIFICATION → candidate set wire** in lifecycle_runner
3. **`FalsificationCandidateRecord`** append-only type
4. **`FalsificationSelector`** — lexicographic ranking without result knowledge
5. Pre-registered candidate-set hash before selection
6. `FalsificationInterpretationContract` for non-partition tools (deferred)
7. `proposition_id` post-emission lineage join

**Autonomous generation today:** **No**

---

## 6. FalsificationCandidateRecord Design

`falsification_candidate_record_v1_3i8` — minimum auditable fields:

| Field | Purpose |
|-------|---------|
| candidate_id | Stable identifier |
| proposition_id / proposition_hash | Immutable proposition reference |
| source_epistemic_update_id | 3I.7 update that triggered SEEK_FALSIFICATION |
| source_research_decision_id | Decision record reference |
| vulnerability_tested | e.g. directional_reversal, episode_instability |
| scientific_rationale | Why this could disconfirm |
| proposed_experiment_spec | Legal ExperimentSpec draft |
| possible_disconfirming_outcome | Pre-registered → DISCONFIRMING/FALSIFIED |
| possible_non_informative_outcome | Pre-registered → NON_INFORMATIVE |
| evidence_independence_class | INDEPENDENT / RELATED / NOT_FALSIFICATION |
| prior_experiment_content_hash | Dedup reference |
| executability_status | Grammar/tool/panel gates |
| leakage_cutoff_requirements | Cutoff integrity |
| lineage_refs | proposition_hash, contract_hash (artifact 03), prior tool_result_hash |
| record_hash | Append-only integrity |

**Explicitly excluded:** expected_profit, Zone C similarity, hidden phenomenon match, post-hoc thresholds.

Full schema: `artifacts/05_falsification_candidate_record_design.json`

---

## 7. Candidate Quality Criteria

**Mechanism:** `lexicographic_falsification_selector_v1_3i8` — no weighted score tuned to this proposition.

| Rank | Criterion | Rule |
|------|-----------|------|
| 1 | Validity gate | Executable, content_hash ≠ prior, anti-rescue pass, cutoff integrity |
| 2 | Counterfactual falsifiability | Strong opposing result → WEAKENED/FALSIFIED via interpreter |
| 3 | Directness | Operationalizes disconfirming_observation_spec first |
| 4 | Evidence independence | Prefer INDEPENDENT over RELATED; reject identical spec |
| 5 | Redundancy | Reject confirmatory retest |
| 6 | Rescue risk | Reject population narrowing, horizon mutation |
| 7 | Executability tiebreak | Sample margin; deterministic candidate_id |

**Outputs:** `SELECTED` | `NO_VALID_FALSIFICATION_CANDIDATE` | `AMBIGUOUS_TIE`

If multiple candidates remain scientifically equivalent after rank 3, report ambiguity — do not invent precision.

---

## 8. Candidate-Generation Results / Design

Eight candidate sketches evaluated (not executed):

| ID | Strategy | Relationship | Interpreter compatible | Falsifiable |
|----|----------|--------------|------------------------|-------------|
| FC-01 | Confirmatory retest | NOT_ACTUALLY_FALSIFICATION | Yes | **No** — identical hash |
| FC-02 | Exclude focal date partition | **INDEPENDENT_FALSIFICATION** | Yes | **Yes** |
| FC-03 | Leave-one-date sensitivity | RELATED_FALSIFICATION | No | No |
| FC-04 | Leave-one-symbol sensitivity | RELATED_FALSIFICATION | No | No |
| FC-05 | Supportive population narrow | NOT_ACTUALLY_FALSIFICATION | — | **REJECT** anti-rescue |
| FC-06 | Horizon mutation | NOT_ACTUALLY_FALSIFICATION | — | **REJECT** anti-rescue |
| FC-07 | Same question, different tool | NOT_ACTUALLY_FALSIFICATION | No | No |
| FC-08 | Neighborhood stability | SAME_FALSIFICATION_DIFF_INSTRUMENT | No | Lower rank |

**Viable under current interpreter:** FC-02 only (among genuine falsification strategies).

**Preferred design selection (if generator existed):** FC-02 — `partition_group_compare` on cohort excluding focal date 2026-08-02, testing episode instability against stated null explanation.

---

## 9. Candidate Semantic-Identity Audit

Using 3H/3I.5 principles (`cores_same_question`, `compute_experiment_content_hash`, instrument vs scientific identity):

| Candidate | Semantic relationship to 3I.7 confirmatory test |
|-----------|--------------------------------------------------|
| FC-01 | **IDENTICAL** experiment identity — confirmatory, not falsification |
| FC-02 | **GENUINELY_INDEPENDENT** episode — same scientific question, different evidence cohort |
| FC-03/04 | **RELATED** robustness — different measurement, same underlying claim |
| FC-05 | **NEAR_DUPLICATE with rescue** — population mutation forbidden |
| FC-06 | **NEW PROPOSITION** — horizon change alters scientific meaning |
| FC-07 | **INSTRUMENT_ONLY** — does not operationalize quintile contrast disconfirm test |
| FC-08 | **SAME_FALSIFICATION_DIFFERENT_INSTRUMENT** — needs new interpretation contract |

Changing tool alone (FC-07) does not create scientific independence. Changing population filter to exclude focal date (FC-02) creates episode independence without mutating proposition core.

---

## 10. Anti-Rescue Audit

| Rescue pattern | Detected in candidate set | Action |
|----------------|----------------------------|--------|
| Repeat original supportive comparison | FC-01 | REJECT |
| Narrow to supportive population | FC-05 | REJECT |
| Change horizon | FC-06 | REJECT |
| Change direction after support | None proposed | N/A |
| Change threshold after support | None proposed | N/A |
| Change outcome field | None proposed | N/A |
| Statistic substitution | None proposed | N/A |

Proposition hash remains immutable. No generator exists that could silently mutate proposition fields — but template `research_actions` REFRAME path could if wired incorrectly; **must not connect template reframing to OPR falsification path**.

---

## 11. Counterfactual Falsifiability Audit

For each viable candidate: *If this produced the strongest valid opposing result, would the lifecycle interpreter weaken/falsify the proposition?*

| Candidate | Strong opposing result | Interpreter outcome | Pass |
|-----------|------------------------|---------------------|------|
| FC-01 | Same as 3I.7 | SUPPORTING again | **FAIL** — not falsification |
| FC-02 | Direction reversal on holdout dates | DISCONFIRMING → WEAKENED | **PASS** |
| FC-03 | Effect vanishes when one date removed | Cannot classify (no quintile metrics) | **FAIL** |
| FC-04 | Symbol removal collapses spread | Cannot classify | **FAIL** |
| FC-05 | Narrow slice shows stronger effect | SUPPORTING (rescue) | **FAIL** |
| FC-06 | Different horizon shows no effect | Wrong proposition | **FAIL** |

Only FC-02 passes the counterfactual gate under the current 3I.7 interpreter scope.

---

## 12. Selection Mechanism

**Designed:** `lexicographic_falsification_selector_v1_3i8`

**Inputs (no future result knowledge):**
- Frozen PropositionRecord
- EpistemicUpdateRecord (SUPPORTED)
- ResearchDecisionRecord (SEEK_FALSIFICATION)
- Generated FalsificationCandidateRecord set
- Prior experiment content hash
- Frozen selector criteria (this document)

**Forbidden inputs:** future ToolResult, Zone C, hidden convergence, expected profit, human preferred candidate.

**Current state:** Selector not implemented. `decide_next_action()` in 3I.7 ends at action label — no candidate enumeration.

---

## 13. Human-Choice Audit

| Locus | Classification | Blocks readiness |
|-------|----------------|------------------|
| disconfirming_observation_spec at birth | SCIENTIFIC PRIOR (autonomous at proposition birth) | No |
| Interpretation spread floors (0.5) | REPRESENTATIONAL CHOICE (frozen pre-result) | No |
| FALSIFY_* template triggers | SCIENTIFIC PRIOR (human template catalog) | **Yes** for OPR path |
| Which falsification strategy after SEEK_FALSIFICATION | **MISSING AUTONOMY** | **Yes** |
| Grammar population filters | EXECUTION CONSTRAINT | No |
| Tool registry | EXECUTION CONSTRAINT | No |
| Lexicographic criteria ordering | REPRESENTATIONAL CHOICE (must freeze pre-selection) | No |
| Panel cutoff | SAFETY CONSTRAINT | No |

**Scientific intent for falsification experiment selection remains undetermined by Mr.BOT today.** The birth spec defines *what would disconfirm*; no module selects *which experiment to run* to test that vulnerability.

---

## 14. BB-Falsify-01 Design / Fixture Results

Minimal benchmark `BB-Falsify-01` — adversarial candidate classification (design-only, no real results):

| Case | Expected | Fixture result |
|------|----------|----------------|
| BF-01 obvious confirmatory retest | REJECT | PASS |
| BF-02 same question / different tool | REJECT | PASS |
| BF-03 independent episode test | ELIGIBLE | PASS |
| BF-04 supportive population narrowing | REJECT anti-rescue | PASS |
| BF-05 horizon mutation disguised | REJECT anti-rescue | PASS |
| BF-06 valid directional reversal | PREFERRED | PASS |
| BF-07 non-informative candidate | LOWER_RANK | PASS |
| BF-08 invalid/leaky candidate | REJECT validity | PASS |
| BF-09 two genuine strategies | FC-02 wins (directness + interpreter) | PASS |
| BF-10 no viable falsification | NO_VALID_FALSIFICATION_CANDIDATE | PASS |

System allowed to output `NO_VALID_FALSIFICATION_CANDIDATE`. Full spec: `artifacts/07_bb_falsify_01_design.json`

---

## 15. Hidden-Firewall Audit

| Check | Result |
|-------|--------|
| Zone C referenced in OPR lifecycle modules | **No** |
| Hidden phenomenon / profitability labels | **Not found** |
| Future ToolResult in design artifacts | **No** |
| Passed | **Yes** |

---

## 16. Readiness Decision

### **PARTIALLY_READY**

**Reason:** 3I.7 closed TEST → INTERPRET → UPDATE → DECIDE through the SEEK_FALSIFICATION label. Infrastructure exists to execute legal ExperimentSpecs and interpret partition-group results against frozen contracts. However, **no proposition-scoped module** transforms `disconfirming_observation_spec` + evidence state into ranked falsification candidates. The template FALSIFY_* path requires GAP codes from `research_interpreter` — not proposition vulnerability.

Mr.BOT can **decide** to seek falsification but cannot yet **design and select** the falsification experiment autonomously.

---

## 17. Frozen One-Shot Package

**Not frozen** — readiness is PARTIALLY_READY.

Design preview only (`artifacts/11_one_shot_package_preview.json`):

| Field | Would-be value |
|-------|----------------|
| Selected candidate | FC-02 exclude_focal_date_partition |
| Tool | partition_group_compare v1 |
| Population | filter `trade_date != 2026-08-02` |
| Interpretation | Reuse 3I.7 contract on quintile metrics |
| Execution | **NOT EXECUTED** — awaiting 3I.9 |

---

## 18. One Missing Capability

### **FalsificationCandidateGenerator**

Map frozen `PropositionRecord` + `EpistemicUpdateRecord` + `disconfirming_observation_spec` → bounded `FalsificationCandidateRecord` set using grammar and tools only.

Requirements:
- Must differ from prior experiment content hash
- Must pass anti-rescue gates
- Must not require GAP codes or `research_interpreter` assessment
- Must enable counterfactual falsifiability under existing or pre-registered interpretation contract

**Deferred secondary gaps:** FalsificationInterpretationContract for sensitivity tools; proposition_id post-emission join; contract hash provenance fix.

---

## 19. Proposed Next Phase

**Phase 3I.9 — Implement FalsificationCandidateGenerator + lexicographic selector**

1. Implement `FalsificationCandidateGenerator` and `FalsificationCandidateRecord`
2. Wire SEEK_FALSIFICATION → candidate generation → lexicographic selection
3. Fix contract hash provenance (reference artifact 03)
4. Freeze one-shot falsification package (FC-02 or selector winner)
5. Execute once — single ToolResult, single interpretation, append lineage

---

## Final Answers

### A. Can Mr.BOT determine for itself how to try to disprove a proposition it originated?

**Not yet.** It records *what would disconfirm* at birth (`disconfirming_observation_spec`) and *decides* to seek falsification after support (3I.7). It cannot yet derive and select a specific falsification experiment from that state without human/template intervention.

### B. Is the selected experiment genuinely capable of weakening/falsifying the original proposition?

**Design yes; execution not available.** FC-02 (partition test excluding focal date) would produce quintile metrics interpretable by the 3I.7 interpreter; a directional reversal would yield DISCONFIRMING → WEAKENED. Confirmatory retest (FC-01) would not qualify as falsification.

### C. Was the falsification strategy selected without knowing the future result or hidden benchmark answer?

**N/A for execution — no experiment selected or run.** The design selector uses only proposition vulnerability, evidence state, and pre-registered criteria. No Zone C or future ToolResult access in the audit/design path.

---

**STOP.** No falsification experiment executed. No next phase implemented.

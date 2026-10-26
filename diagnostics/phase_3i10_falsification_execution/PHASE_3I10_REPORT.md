# Phase 3I.10 — One-Shot Autonomous Falsification Execution

**Mode:** Single execution from frozen 3I.9 package  
**Execution version:** `falsification_one_shot_execution_v1_3i10`  
**Verdict:** **AUTONOMOUS_FALSIFICATION_PASS**

---

## 1. Branch / Commit / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3i10-falsification-execution-aad2` |
| Base | 3I.9 falsification selection |

---

## 2. Pre-Execution Package Integrity

All integrity checks **passed**:

| Check | Result |
|-------|--------|
| package_hash | `bdd77912...` matches expected |
| execution_status | NOT_EXECUTED (pre-run) |
| proposition_hash | match |
| prior_lineage_hash | match |
| interpretation_contract_hash | `3474a096...` match |
| selected candidate | `fc-independent_episode_holdout` match |
| ExperimentSpec content hash | match |
| generator/selector versions | match |
| prior epistemic state | SUPPORTED |

---

## 3. Exact Package Hash

`bdd77912ccdde41d2245ed36a95071335af68b06b1e005f41c153f86314bba46`

---

## 4. Frozen Proposition & Prior Epistemic State

| Field | Value |
|-------|-------|
| proposition_id | `prop-efb650d9bd5c451f` |
| proposition_hash | `c3aab7de80fdb9e56b7be68d517ec0e4792b711ec9772638143df3cfe4e39c9b` |
| prior epistemic state | **SUPPORTED** (from `epu-5a7bec6e47ec`) |
| prior decision | SEEK_FALSIFICATION (`dec-c92fb28fdc13`) |

---

## 5. Frozen Selected Falsification Candidate

**fc-independent_episode_holdout** — independent episode holdout excluding motivating date 2026-08-02

---

## 6. Exact ExperimentSpec Executed

- Tool: `partition_group_compare` v1
- Partition: `rs_spread`, 5 groups
- Population: `trade_date in [43 holdout dates]` (excluding 2026-08-02)
- Outcome: `t5_return`, horizon 0
- Cutoff: 2026-08-17
- Content hash: `624e91d23ea6ec56ee4f00d9346acc01475e999c6e891ece3e82b7a6c4396e6e`

---

## 7. One-Shot Execution Proof

| Field | Value |
|-------|--------|
| execution_id | `fex-e1a17fe73bb4` |
| execution_count | **1** |
| rerun_attempted | false |
| package modified | false |

---

## 8. Raw ToolResult

| Field | Value |
|-------|-------|
| status | OK |
| sample_size | 5964 |
| result_hash | stored in `02_raw_tool_result.json` |
| Stored before interpretation | **Yes** |

Quintile metrics (holdout cohort): low=-0.44, high=1.65, spread=2.09

---

## 9. Evidence-Independence Audit

Pre-execution: 43 holdout dates, zero overlap with motivating `2026-08-02`

Operational post-execution: population_spec applied; motivating date absent from executed cohort (n=5964 vs 6248 unfiltered)

---

## 10. Frozen Interpretation Contract Verification

Loaded artifact 03 directly via `interpretation_contract_from_dict()` — hash `3474a096...`, not rebuilt.

---

## 11. Matched Interpretation Rule

`high_quintile_mean > low_quintile_mean AND quintile_mean_spread >= 0.5`

---

## 12. Evidence Classification

**SUPPORTING** — holdout cohort still shows positive quintile spread above floor

---

## 13. Prior State + New Evidence Analysis

| Field | Value |
|-------|-------|
| prior_state | SUPPORTED |
| evidence_class | SUPPORTING |
| frozen transition | SUPPORTING → SUPPORTED |
| resulting_state | **SUPPORTED** |
| preregistered | Yes (artifact 03 transition_mapping) |

Note: Mapping is evidence-absolute, frozen before any falsification result.

---

## 14. Second EpistemicUpdateRecord

`epu-bf4583da5eda` — references package, candidate, prior update, execution_id, frozen contract

---

## 15. ResearchDecisionRecord

`dec-46321bc2078e` — **SEEK_FALSIFICATION** (frozen decision_mapping for SUPPORTING evidence)

---

## 16. Proposition Immutability Audit

proposition_hash unchanged; no rescue detected

---

## 17. Package Immutability Audit

package_hash unchanged; candidate and ExperimentSpec unchanged

---

## 18. Anti-Rescue Audit

No population/outcome/horizon/threshold/exclusion changes post-execution

---

## 19. Hidden / Future Firewall Audit

No Zone C, no pre-execution result inspection, no post-cutoff leakage

---

## 20. Scientific Proposition Outcome

**Proposition survived independent-episode falsification attempt.** Holdout evidence still SUPPORTING; epistemic state remains SUPPORTED. The rs_spread → t5_return contrast persists on episodes excluding the motivating focal date.

---

## 21. Researcher Capability Outcome

**Mr.BOT behaved correctly:** integrity gate → single execution → raw result stored → frozen contract interpretation → append-only epistemic update → pre-registered decision. No rescue, no rerun, no rule changes.

---

## 22. Final Capability Verdict

### **AUTONOMOUS_FALSIFICATION_PASS**

---

## 23. Remaining Limitation

Decision mapping after second SUPPORTING on holdout still yields SEEK_FALSIFICATION — no pre-registered "sufficient falsification attempts" stop rule. Multi-evidence transition mapping is evidence-absolute, not prior-state-conditioned.

---

## 24. Proposed Next Phase

**Phase 3I.11 — Multi-evidence epistemic transition preregistration:** define prior-state-conditioned transitions (SUPPORTED + DISCONFIRMING → WEAKENED explicitly) and falsification sufficiency criteria.

---

## Final Answers

### A. What happened when Mr.BOT executed its autonomously selected falsification experiment?

It ran `fc-independent_episode_holdout` once on 43 dates excluding the motivating episode. The holdout cohort (n=5964) still showed high-rs_spread quintile outperforming low quintile (spread 2.09).

### B. Did evidence support, weaken, contradict, falsify, or fail to inform under frozen rules?

**SUPPORTING** under frozen rules — direction matches, spread ≥ 0.5. Did not weaken or falsify.

### C. Did Mr.BOT respond without changing proposition, experiment, or interpretation rules?

**Yes.** Package, proposition, and contract unchanged; interpretation used artifact 03 only.

### D. Did Mr.BOT behave like an evidence-responsive researcher regardless of proposition survival?

**Yes.** AUTONOMOUS_FALSIFICATION_PASS — correct process independent of supportive outcome.

---

**STOP.** One execution only. No second experiment.

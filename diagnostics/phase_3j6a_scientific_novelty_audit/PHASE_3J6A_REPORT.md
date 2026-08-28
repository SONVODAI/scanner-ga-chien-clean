# Phase 3J.6A — High-Overlap Scientific Novelty Audit

## Verdict: **PASS_WITH_AUDIT_HARDENING**

Experiment #2 may proceed to execution design review, but generic novelty accounting must decompose **sample reuse** from **scientific question overlap** before an execution gate.

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j6a-scientific-novelty-audit-aad2` |
| Base 3J.6 | `fdf77eff5` |
| Audit artifact | `diagnostics/phase_3j6a_scientific_novelty_audit/artifacts/01_real_novelty_audit.json` |

---

## Side-by-side: Experiment #1 vs proposed Experiment #2

| Dimension | Experiment #1 (executed) | Experiment #2 (designed, NOT_EXECUTED) |
|-----------|---------------------------|----------------------------------------|
| **Scientific objective** | Does rs_spread quintile ordering survive **excluding motivating episode** (2026-08-02)? | Does directional rs_spread quintile commitment hold on the **full cross-section**? |
| **Targeted null** | `episode_artifact` | `directional_reversal` |
| **Target uncertainty** | `episode_robustness` | `directional_effect_full_universe` |
| **Population** | `filter trade_date not_in [2026-08-02]` | `all` (full panel) |
| **Cohort strategy** | `counterexample_period_search` | `full_panel_contrast` |
| **Cohort construction** | Holdout = all dates except birth/motivating date | Complete panel through cutoff |
| **Comparison / contrast** | `partition_quintile_contrast` on `rs_spread` | `partition_quintile_contrast` on `rs_spread` |
| **Outcome** | `t5_return compare > 0.0` | `t5_return compare > 0.0` |
| **Horizon** | 0 | 0 |
| **Grouping** | `partition_group_compare`, 5 quintiles on `rs_spread` | `partition_group_compare`, 5 quintiles on `rs_spread` |
| **Statistic evaluated** | Interpretation: `quintile_mean_spread`; tool: `incremental_success_rate` spread | Same binding path |
| **Falsifying observation** | Spread collapse/reversal on holdout excluding motivating date | Full-panel quintile spread collapse or directional reversal |
| **Supporting observation** | `high_quintile_mean > low_quintile_mean` with spread ≥ 0.5 on holdout | Same rule on **full panel** |
| **Contradicting observation** | Direction reversal or spread ≤ 0 on holdout | Direction reversal or spread ≤ 0 on full cross-section |
| **Row count** | 6,106 | 6,248 |
| **Row overlap (vs Exp #2)** | — | 0.977 (Exp #1 ⊂ Exp #2; 142 rows added) |
| **Scientific-action core hash** | `7c360636…` | `58ee7b6d…` (different) |
| **Experiment content hash** | `383e822e…` | `65a641ba…` (different) |

---

## What NEW information can Experiment #2 produce that Experiment #1 could not?

Mechanically supported answer:

1. **Different epistemic binding.** Experiment #1 interpretation maps evidence to `episode_artifact` / `episode_robustness`. Experiment #2 binds to `directional_reversal` / `directional_effect_full_universe` per frozen 3J.5 decision. These are distinct falsifiable commitments in the research grammar (`COHORT_INTENT` mapping).

2. **Full-universe population completion.** Experiment #1 rows are a **strict subset** of Experiment #2 (6,106 ⊂ 6,248). The 142 added rows are exactly the motivating-date observations excluded from Experiment #1. Experiment #2 computes quintile statistics over the complete cross-section including those rows.

3. **Discriminating observation not available from Exp #1.** A full-panel `quintile_mean_spread` that collapses or reverses would weaken `directional_reversal` even if holdout supported `episode_artifact`. Experiment #1 cannot emit this observation because it explicitly excluded the motivating date and targeted a different null.

4. **Not a relabelled repetition.** Although contrast mechanics (quintile partition on rs_spread) are identical, `scientific_action_core_hash` and `experiment_content_hash` differ, and `information_gain_type` / `expected_epistemic_consequence_type` differ (`falsify_episode_robustness` vs `falsify_directional_effect_full_universe`).

**Caveat:** Information novelty is **marginal at the row level** — 97.7% of Exp #2 rows were already observed in Exp #1. The novelty is primarily **scientific/contrast** (new null, new population semantics), not sample independence.

---

## Falsification geometry (pre-result)

```
Proposition commitment (directional):
  E[ t5_return | high rs_spread quintile ] > E[ t5_return | low rs_spread quintile ]
  across the FULL cross-section

Experiment #2 falsifies directional_reversal if:
  quintile_mean_spread <= 0  OR  high/low ordering reverses on FULL panel (6,248 rows)

Experiment #1 could NOT answer this because:
  - Population excluded 2026-08-02 (counterexample_period_search)
  - Target null was episode_artifact, not directional_reversal
  - Interpretation contract applied holdout result to episode robustness only
```

Experiment #1 holdout already showed supportive spread (2.35) on 97.7% of Exp #2 rows. Falsification remains **possible** if the 142 motivating-date rows shift quintile assignments or aggregate spread materially — but epistemic increment is constrained.

---

## Redundancy decomposition

| Dimension | Value | Interpretation |
|-----------|-------|----------------|
| **ROW_OVERLAP** | 0.977 | High sample reuse (Exp #1 ⊂ Exp #2) |
| **POPULATION_OVERLAP** | 0.977 | Holdout is subset of full panel |
| **CONTRAST_OVERLAP** | 1.0 | Same quintile partition mechanics |
| **OUTCOME_OVERLAP** | 1.0 | Identical outcome_spec |
| **NULL_TARGET_OVERLAP** | 0.0 | Different nulls |
| **SCIENTIFIC_QUESTION_OVERLAP** | 0.0 | Different target uncertainty + epistemic consequence |
| **INFORMATION_NOVELTY** | `MARGINAL_POPULATION_COMPLETION` | 142 new rows + new null binding |
| **SAMPLE_NOVELTY** | LOW | Expected given superset design |
| **SCIENTIFIC_CONTRAST_NOVELTY** | HIGH | New falsifiable question |

**Conclusion:** `HIGH_FIRST_EXPERIMENT_OVERLAP` is **high sample reuse**, not **scientific redundancy**. Coarse label alone is insufficient for execution gating.

---

## Outcome semantics audit

| Check | Result |
|-------|--------|
| Stated objective | "Full cross-section directional quintile test" |
| Bound outcome_spec | `t5_return compare > 0` |
| Tool primary metric | `incremental_success_rate` spread across groups |
| Interpretation primary metric | `quintile_mean_spread` via `extract_quintile_metrics` (executor) |
| Frozen contract rule | `high_quintile_mean > low_quintile_mean AND spread >= 0.5` |
| Blocker? | **No** — same binding in Exp #1 and Exp #2; pre-existing 3J.3/3J.4 pattern |

**Note:** The `t5_return > 0` outcome_spec is a grammar-level compare operator used by the tool for success-rate spread; interpretation correctly uses quintile means per frozen contract. This is **partial but consistent** — not introduced by Exp #2. Document for execution-phase clarity; do not silently reinterpret.

---

## Counterfactual A/B/C sanity checks

| Case | Description | Policy expectation | Audit result |
|------|-------------|-------------------|--------------|
| **A** | 97% same rows, new falsifiable contrast (different null) | May remain admissible | `A_HIGH_ROWS_NEW_CONTRAST_ADMISSIBLE` — matches real diagnostic |
| **B** | 97% same rows, same scientific question | Reject as redundant | `B_HIGH_ROWS_SAME_CONTRAST_REJECT` — decomposition marks `SCIENTIFIC_REDUNDANCY` |
| **C** | Low row overlap, wrong null | Reject despite sample novelty | `C_LOW_ROWS_WRONG_QUESTION_CONTEXT` — CF-SD1 already rejects wrong null in 3J.6 |

Tests: `tests/test_edge_research_opr_phase_3j6a.py` (3/3 pass)

---

## Code changes (audit hardening only)

| File | Purpose |
|------|---------|
| `modules/edge_research/opr_bridge/second_experiment_novelty_audit.py` | Decomposition helper (audit-only; does not alter 3J.6 selection) |
| `diagnostics/phase_3j6a_scientific_novelty_audit/run_phase_3j6a.py` | Real diagnostic audit runner |
| `tests/test_edge_research_opr_phase_3j6a.py` | A/B/C decomposition tests |

No change to 3J.6 selector, no Experiment #2 execution, no ToolResult #2.

---

## Regression

| Suite | Result |
|-------|--------|
| `test_edge_research_opr_phase_3j6a.py` | 3/3 |
| `test_edge_research_opr_phase_3j6.py` | 11/11 |

---

## Recommendation before execution (3J.7+)

1. Attach `NoveltyDecomposition` to second-experiment package audit trail (reporting only or pre-execution gate).
2. Do **not** reject designs solely on `first_experiment_overlap_fraction >= 0.85` when `NULL_TARGET_OVERLAP == 0`.
3. Require explicit `INFORMATION_NOVELTY` assessment when row overlap exceeds 0.85.

---

## Hard STOP

- No Experiment #2 execution
- No ToolResult #2
- No Phase 3J.7
- No deployment/reboot

# Phase 3H.14 — Semantic Value Attribution Audit (AUDIT ONLY)

**Branch:** `cursor/phase-3h14-semantic-value-attribution-audit-aad2`  
**HEAD:** `0bfa3825c` (BB14 frozen research commit — no production changes)  
**Verdict:** **NO DEFECT FOUND** (scoring)  
**Date:** 2026-08-22

---

## 1. Branch / HEAD / Git Status

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3h14-semantic-value-attribution-audit-aad2` |
| HEAD | `0bfa3825c01576652863a93723f5974b3ac6a40d` |
| Production code modified | **None** |
| Diagnostic artifacts | `diagnostics/phase_3h14_semantic_value_attribution/` |

---

## 2. BB14 Remaining-Value Decomposition (T4 / T8 / T9)

### T4 — `adaptive_partition_compare` on `rs10` (ERV = 5.49)

| Component | Value | Share of positive mass |
|-----------|-------|----------------------|
| Reconciled planner base | −1.60 | — |
| Exploration debt | **+2.00** | 24% |
| Exploitation value | +1.50 | 18% |
| MIG | **+3.00** | 36% (dominant) |
| Gated novelty | +1.50 | 18% |
| Complexity penalty | −0.91 | — |

- Semantic class at decision: **GENUINELY_INDEPENDENT** — novelty reconciliation **not applied**
- Ranking margin vs best alternative: **0.0** (exact tie with `rs_spread` partition at ERV 5.49; won on `action_id` tie-break)
- `prior_experiments_in_dimension`: 0 → full MIG for new feature dimension

### T8 — `adaptive_partition_compare` on `rs_spread` (ERV = −1.10)

| Component | Value |
|-----------|-------|
| Reconciled planner base | −6.32 |
| Exploration debt | +1.75 |
| Exploitation value | +1.50 |
| MIG | +1.80 |
| Gated novelty | +1.50 |
| Complexity penalty | −1.38 |

- Semantic class: **GENUINELY_INDEPENDENT** — novelty reconciliation **not applied**
- Wins as **least-negative** among all comparable candidates (all ERV ≤ −1.10)
- MECHANICAL_CYCLING label triggered by planner total < 0, not by semantic redundancy

### T9 — `threshold_exploration` on `rs_spread` (ERV = 5.78)

| Component | Value |
|-----------|-------|
| Reconciled planner base | −1.14 |
| Exploitation value | **+7.75** (dominant, 60% of positive mass) |
| MIG | +2.70 |
| Gated novelty | +1.50 |
| Exploration debt | 0.0 |
| Redundancy penalty | −2.50 |
| Complexity penalty | −1.51 |

- Semantic class: **GENUINELY_INDEPENDENT**
- Margin vs best alternative (`symbol_decomposition`): **+2.0 ERV**
- Exploitation driven by `threshold_explore` hint + `additional_investigation_warranted` + branch evidence — scientifically coherent partition follow-up

**Critical finding:** T4/T8/T9 winners were **not** classified `REPRESENTATION_NOVELTY_ONLY` at live decision points. The 29 rank reconciliations in BB14 applied to **other** candidates (mostly REFRAME/REPOPULATE near-duplicates), none of which won.

---

## 3. Semantic Ownership Map

| ERV Component | Scientific Owner | Storage / Accrual Level |
|---------------|------------------|-------------------------|
| Reconciled planner base | Candidate + branch-context assessment | Per-candidate at planning |
| Exploration debt | Under-examined **feature/outcome/pop/frame** dimensions | `session.explanatory_features_tested`, branch deferral |
| MIG | **dimension_key**(feature, outcome, pop, frame) + tool history | `portfolio.dimension_experiment_counts`, `tool_attempt_counts` |
| Exploitation value | **Branch evidence state** + assessment warrants | `branch.unresolved_research_value`, assessment flags |
| Gated novelty | Semantic line relationship (3H.11/3H.13) | Per-candidate at ERV build |
| Complexity / redundancy penalties | Candidate draft complexity | Planner components |

Code refs: `research_portfolio.py:405-760`, `research_novelty_valuation_bridge.py`, `research_novelty_rank_reconciliation.py`

---

## 4. Exploration Debt Findings

**Mathematical meaning:** Hybrid of (A) neglect of explanatory **feature** dimensions, (C) branch deferral, and (D) untested outcome/population specs — **not** canonical proposition neglect.

```410:460:modules/edge_research/research_portfolio.py
def compute_exploration_debt(...):
    # untested feature ratio → debt
    # untested outcome/pop/frame → debt
    # branch DEFERRED_PROMISING → debt from unresolved_research_value
```

**Classification: LEGITIMATE** at feature-dimension ownership level.

**Open question (INSUFFICIENT_EVIDENCE):** If `rs10` and `rs_spread` partitions share one canonical proposition, feature-level debt awards independent exploration credit to slices of one question. Live BB14 classifies these as `GENUINELY_INDEPENDENT`; 3H.12 synthetic counterfactual classified T4/T8 as `SAME_QUESTION_DIFFERENT_INSTRUMENT`. Cannot resolve without identity changes (frozen).

---

## 5. MIG Findings

**Production:** `dimension_key = feature|outcome|pop|frame` with dampening for repeated tool (`×0.15` if in `branch_tools_attempted`) and repeated dimension (`×0.35` per repeat).

**Classification: LEGITIMATE**

- New instrument on **new feature dimension** (`prior_experiments_in_dimension=0`) → full MIG factor (3.0 at T4)
- This is **not** inherited untried appearance alone — dimension key differs by feature slice
- At T8, MIG reduced to 1.8 (tool already on branch → dampening applies)

**Distinction preserved:** MIG does not blindly reward "new tool"; it keys on dimension + applies branch tool dampening.

---

## 6. Exploitation Findings

**Represents:** Branch-level evidence that prior experiments made continued investigation warranted — `additional_investigation_warranted`, `conditional_candidate`, `threshold_explore`/`shape_followup` hints, `branch.unresolved_research_value`.

**Classification: LEGITIMATE**

T9 exploitation (7.75) is the dominant win driver and is scientifically coherent: threshold exploration following adaptive partition on `rs_spread` is standard follow-up when partition structure was interesting but inconclusive.

Repeated work on a promising branch is **scientifically justified** when assessment flags warrant it — not automatically cycling.

---

## 7. Mechanical-Cycling Label Assessment

**Trigger rule** (benchmark orchestration, not research logic):

```429:445:benchmarks/blind_benchmark_14/run_benchmark.py
if tool in MECHANICAL_TOOLS and (sel_score or 0) < 0:
    return "MECHANICAL_CYCLING"
```

**Classification: MISOWNED** as a proxy for "scientifically wasteful repetition"

The label requires:
- Tool ∈ {`adaptive_partition_compare`, `threshold_exploration`}
- Planner total score < 0

It does **not** require:
- Semantic representation redundancy
- Same canonical proposition
- Low portfolio ERV (T8 wins at ERV = −1.10)

**After 3H.12/3H.13:** The label can fire on scientifically defensible follow-up experiments that happen to use mechanical tools with negative planner bases but positive portfolio ERV.

**Recommendation:** Future **diagnostic** refinement only — not a scoring change.

---

## 8. Negative-Control Findings

Audited non-cycling transitions T3, T5, T7, T10 (`JUSTIFIED_CONTINUE` / `DEFENSIBLE_CONTINUE`):

- Same ERV component structure: MIG + exploration debt dominate early; exploitation rises on branch follow-up
- Representation-only gating (29 instances) affects **REFRAME/REPOPULATE** candidates with ERV 3–6 — they remain **non-winners**
- No pattern of misownership specific to mechanical-cycling cases; feature-level accounting is **normal system behavior**

**10 competitive representation-only candidates** (ERV > 2 after gating) — **0 became winners**.

---

## 9. Per-Component Classification Summary

| Component | Classification |
|-----------|-------------|
| Exploration debt (feature dimension) | **LEGITIMATE** |
| MIG (dimension + tool dampening) | **LEGITIMATE** |
| Exploitation value (branch evidence) | **LEGITIMATE** |
| Gated novelty / rank reconciliation | **LEGITIMATE** |
| Exploration debt × same-proposition/different-feature | **INSUFFICIENT_EVIDENCE** |
| MECHANICAL_CYCLING diagnostic label | **MISOWNED** (label only) |

---

## 10. T4/T8/T9 Scientific Justification After Novelty Removal

| Transition | Rep-redundant at decision? | Reconciliation applied? | Justified? |
|------------|---------------------------|------------------------|------------|
| T4 | No (GENUINELY_INDEPENDENT) | No | **Yes** — MIG + exploration on new feature dimension |
| T8 | No | No | **Yes** — least-negative among exhausted candidate set |
| T9 | No | No | **Yes** — exploitation-driven partition follow-up (+2.0 margin) |

Novelty removal was **not applicable** to these winners. Their remaining value is from feature-dimension exploration, branch exploitation, and MIG — not from false representation novelty.

---

## 11. Decision: **NO DEFECT FOUND**

Remaining ERV components for competitive candidates measure value at **feature/dimension** and **branch/assessment** ownership levels that are scientifically coherent under current live semantic classification.

No demonstrable double-counting of proposition-level value at tool/representation level.

**Do not recommend a scoring change.**

---

## 12. Narrow Correction Proposal

**None.** Scoring should remain unchanged.

The only identified defect is **diagnostic label coarse-graining** (`MECHANICAL_CYCLING`), not portfolio/planner valuation.

---

## 13. Diagnostic Experiment Proposal

Not required for INCONCLUSIVE — decision is NO DEFECT FOUND.

If pursued optionally: observational study comparing live `GENUINELY_INDEPENDENT` vs synthetic `SAME_QUESTION_DIFFERENT_INSTRUMENT` classifications for partition/threshold pairs on identical outcome/pop — **identity observability only**, no scoring change.

---

## 14. Recommendation

**Leave scoring unchanged.**

Future work should refine **diagnostic taxonomy** (separate "mechanical tool + negative planner score" from "semantically redundant repetition") before any further valuation bridge.

---

## 15. Capability Gap Limiting Autonomous Untaught-Edge Discovery

The binding gap is **proposition-level vs feature-slice observability at live decision time**. When feature slices (`rs10`, `rs_spread`) on the same branch are classified as independent lines, the system correctly awards dimension-level exploration/MIG/exploitation — but this prevents semantic machinery from distinguishing "new explanatory slice of same question" from "genuinely independent scientific line" during ranking. Until that boundary is reliably observable live (without retuning weights), autonomous selection will continue to prefer locally coherent branch follow-up over globally diverse frontier exploration — even when accounting is internally consistent.

---

## Answer

**Are we observing genuinely wasteful repetition, or are we mistakenly calling scientifically justified repeated investigation "mechanical cycling"?**

**We are largely mistaking scientifically justified repeated investigation for "mechanical cycling."** The diagnostic label keys on mechanical tool + negative planner score, not semantic redundancy. T4/T8/T9 winners retained competitiveness from legitimate exploration debt, MIG, and branch exploitation — and were **not** representation-redundant at live classification. The 3 → 3 mechanical cycling count reflects **label coarse-graining**, not demonstrated misvaluation of remaining ERV components.

---

**STOP — Audit complete. No implementation. No deployment.**

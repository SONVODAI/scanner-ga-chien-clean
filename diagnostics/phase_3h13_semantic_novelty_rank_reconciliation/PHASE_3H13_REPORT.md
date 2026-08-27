# Phase 3H.13 — Semantic Novelty Rank Reconciliation

**Branch:** `cursor/phase-3h13-semantic-novelty-rank-reconciliation-aad2`  
**Verdict:** **PARTIAL**  
**Date:** 2026-08-22

---

## 1. Root Cause — Late Semantic Influence

3H.11 gated only the portfolio `novelty_component` (`novelty × WEIGHT_NOVELTY_PORTFOLIO/2`). Planner raw novelty from `_novelty_bonus()` (up to `WEIGHT_NOVELTY=2.0`) remained embedded in `base_score`. Since both `plan_next_action` and `select_global_research_opportunity` rank by `expected_research_value = base_score + portfolio_adjustments`, representation-only candidates retained up to 2.0 points of false novelty rank boost even when 29 portfolio gates fired in BB13.

**Artifact:** `diagnostics/phase_3h13_semantic_novelty_rank_reconciliation/artifacts/00_root_cause_audit.json`

---

## 2. Architecture — Option B (Minimal)

**Post-planner rank reconciliation at ERV computation** in `build_opportunity_from_candidate`:

```
reconciled_base = base_score - raw_planner_novelty + gate(raw_planner_novelty, valuation_class)
ERV = reconciled_base + exploration + exploitation + MIG + gated_portfolio_novelty - penalties
```

- Single semantic valuation from existing 3H.11 `valuation_class`
- No second classifier, no planner weight changes
- Feeds both planner `adjusted_scores` and global allocator ERV comparison

**New module:** `modules/edge_research/research_novelty_rank_reconciliation.py`  
**Integration:** `modules/edge_research/research_portfolio.py` → `build_opportunity_from_candidate()`

---

## 3. Files Changed

| File | Change |
|------|--------|
| `modules/edge_research/research_novelty_rank_reconciliation.py` | New — planner novelty reconciliation + audit |
| `modules/edge_research/research_portfolio.py` | Reconcile base_score before ERV |
| `tests/test_edge_research_novelty_rank_reconciliation.py` | Pre-registered scenarios A–I |
| `diagnostics/phase_3h13_semantic_novelty_rank_reconciliation/` | Audit, replay, artifacts |
| `benchmarks/blind_benchmark_14/` | Frozen blind session BB14 |

---

## 4. Pre-Registered Ranking Matrix

**Artifact:** `diagnostics/phase_3h13_semantic_novelty_rank_reconciliation/artifacts/01_pre_registered_ranking_matrix.json`

All scenarios A–I pass in `tests/test_edge_research_novelty_rank_reconciliation.py`.

---

## 5. Test Results

| Suite | Result |
|-------|--------|
| 3H.13 ranking tests A–I | 11/11 pass |
| 3H.12 proposition matrix | 16/16 pass |
| 3H.11 novelty bridge | pass |
| 3H.10 semantic tests | pass |
| Full edge_research regression | **701 passed**, 1 skipped |

---

## 6. Frozen-Invariant Audit

Unchanged: planner base weights, 3H.8 exit, 3H.6 IV bridge, 3H.11 gating policy, 3H.12 identity, dedup, grammar, templates, tools.

**Artifact:** `diagnostics/phase_3h13_semantic_novelty_rank_reconciliation/artifacts/04_invariant_audit.json`

---

## 7. Counterfactual Ranking Replay (BB11/12/13)

Offline replay applying planner-novelty reconciliation delta to frozen ERV:

| Metric | Value |
|--------|-------|
| Representation-only reconciliations | 58 |
| Decision winner changes | 0 |
| Unexplained broad shift | No |

T4/T8/T9 winners unchanged after reconciliation — remaining scientific value still highest.

**Artifact:** `diagnostics/phase_3h13_semantic_novelty_rank_reconciliation/artifacts/02_counterfactual_ranking_replay.json`

---

## 8. Ranking Perturbation Audit

Changes attributable solely to representation-only planner novelty removal. No unrelated candidate rank instability observed.

**Artifact:** `diagnostics/phase_3h13_semantic_novelty_rank_reconciliation/artifacts/03_ranking_perturbation_audit.json`

---

## 9. BB14 Results

| Metric | BB11 | BB12 | BB13 | BB14 |
|--------|------|------|------|------|
| Mechanical cycling | 3 | 3 | 3 | 3 |
| Novelty gating applied | 0 | 0 | 29 | 29 |
| Rank reconciliation applied | 0 | 0 | 0 | **29** |
| Tool distribution | identical | identical | identical | **identical** |
| Unexplored frontier at STOP | 36 | 36 | 36 | 36 |
| Terminal status | NO_EDGE | NO_EDGE | NO_EDGE | NO_EDGE |

**Selections changed due to false representation novelty removal:** 0 material path changes. BB14 vs BB13 shows 2 action_id tie-break differences at identical ERV (decisions 5, 9) — same tool/feature class, not attributable to representation novelty removal.

---

## 10. Verdict — PARTIAL

**PASS criteria partially met:**
- Rank reconciliation is live and active (29 applications in BB14)
- Representation-only planner novelty correctly zeroed in effective rank
- Scientific novelty preserved (zero delta for SCIENTIFIC_NOVELTY class)
- No broad ranking instability

**Not met:**
- Frozen BB14 autonomous path identical to BB11/12/13 (same mechanical cycling, same tools)
- Counterfactual replay shows winners unchanged at T4/T8/T9

---

## 11. Remaining Capability Gap

Rank integration is structurally correct but mechanical-cycling winners retain sufficient non-novelty scientific value (exploration debt, MIG, exploitation) to win even after losing false novelty. The system now *can* rank correctly but the frozen benchmark decision margins do not flip winners.

---

## 12. Next-Step Recommendation (Proposal Only)

**Phase 3H.14 proposal:** Portfolio-level exploration-debt / MIG interaction audit — verify whether representation-redundant candidates receive inflated non-novelty portfolio bonuses independent of semantic line classification. Do not implement in this phase.

---

## Answer

**Does Mr.BOT's actual autonomous experiment selection now respect the distinction between new scientific information and merely new experimental representation?**

**Partially yes.** The ranking comparison that determines autonomous selection now applies one semantic novelty valuation to both planner and portfolio layers (29 live reconciliations in BB14). Representation-only candidates no longer receive planner-level false novelty boost in effective ERV. However, the frozen BB14 session followed the same research path as BB11–BB13 because winners' remaining scientific value still dominated rank margins at the observed decision points.

---

**STOP — Phase 3H.13 complete. No deployment. No next phase implemented.**

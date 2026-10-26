# Phase 3H.12 — Proposition-Key Resolution for Same-Question Detection

## Verdict: **PARTIAL**

Canonical proposition core and branch-context enrichment successfully activate the 3H.11 novelty bridge (29 gating events vs 0 in BB12). Live autonomous decision sequence remained identical to BB11/BB12 (mechanical cycling 3, same tool distribution), indicating identity resolution improved but allocator ranking at selected decision points was insufficient to change outcomes in this single session.

---

## 1. Branch / Commits / PR

| Commit | Description |
|--------|-------------|
| `223080a0d` | Canonical proposition core + identity enrichment |
| `36469ad1e` | Over-collapse audit + BB13 orchestration + BB13 artifacts |

**Branch:** `cursor/phase-3h12-proposition-key-resolution-aad2`

---

## 2. Root Cause of 3H.11 Non-Activation

1. **Missing outcome_spec** on mechanical-tool candidates (scope incomplete vs branch parent)
2. **Feature slice in proposition key** (instrument conflated with scientific question)
3. **Uncertainty code mismatch** between candidate and branch context
4. **36/300 legacy path** entries when draft_spec unavailable early in session

See `diagnostics/phase_3h12_proposition_key_resolution/artifacts/00_root_cause_audit.json`

---

## 3. Files Changed

| File | Change |
|------|--------|
| `modules/edge_research/research_proposition_core.py` | **New** — canonical core + representation envelope |
| `modules/edge_research/research_line_identity.py` | v2 — core keys, branch enrichment |
| `modules/edge_research/research_line_relationship.py` | v2 — core-based classification |
| `modules/edge_research/research_novelty_valuation_bridge.py` | Pass graph/branch to identity |
| `tests/test_edge_research_proposition_key_resolution.py` | **New** — matrix A–L |

**Frozen:** 3H.11 gating policy, planner weights, exit formula, IV bridge, dedup, grammar

---

## 4. Canonical Proposition Model

**Core (scientific question key):** population + outcome + horizon + uncertainty family + conditioning  
**Representation envelope (excluded from key):** tool, action_id, frame, instrument_features

Branch-context enrichment propagates missing outcome/horizon/uncertainty from branch root experiment when auditable.

---

## 5. Pre-Registered Pair Matrix

Cases A–L in `artifacts/01_proposition_pair_matrix.json` — all synthetic tests pass.

---

## 6–7. Test Results

| Suite | Result |
|-------|--------|
| Proposition pair matrix A–L | **16/16 PASS** |
| 3H.10 semantic + 3H.11 bridge | **58/58 PASS** |
| Full edge_research regression | **690 passed, 1 skipped** |

---

## 8. Frozen-Invariant Audit

Unchanged: planner weights, exit formula, IV bridge, dedup, grammar, 3H.11 gating rules.

---

## 9. Legacy Path

36/300 BB12 legacy entries — occurs when `draft_spec is None`. Enrichment reduces but does not eliminate early-session legacy path; documented, not fabricated.

---

## 10. Counterfactual Replay (BB11/BB12 decision points)

| Transition | Old (BB12) | New | Gating |
|------------|------------|-----|--------|
| T4 | RELATED_BUT_DISTINCT | SAME_QUESTION_DIFFERENT_INSTRUMENT | REPRESENTATION_NOVELTY_ONLY (−1.5) |
| T8 | RELATED_BUT_DISTINCT | SAME_QUESTION_DIFFERENT_INSTRUMENT | REPRESENTATION_NOVELTY_ONLY (−1.5) |
| T9 | RELATED_BUT_DISTINCT | GENUINELY_INDEPENDENT | unchanged (evidence: distinct) |

T9 correctly remains distinct — not forced to match diagnostic examples.

---

## 11. Over-Collapse Audit

28 pairs sampled, 0 ambiguous merges, **PASS**. No legitimate independent lines collapsed.

---

## 12–13. BB11 / BB12 / BB13 Comparison

| Metric | BB11 | BB12 | BB13 |
|--------|------|------|------|
| Terminal status | NO_EDGE_FOUND | NO_EDGE_FOUND | NO_EDGE_FOUND |
| Experiments | 11 | 11 | 11 |
| Mechanical cycling | 3 | 3 | **3** |
| Late mechanical cycling | 2 | 2 | 2 |
| Premature STOP | 0 | 0 | 0 |
| Unexplored frontier | 36 | 36 | 36 |
| Novelty gating applied | 0 | 0 | **29** |
| Representation gated | 0 | 0 | **29** |
| Tool distribution | identical | identical | identical |

---

## 14. PASS / PARTIAL / FAIL

**PARTIAL** — Same-question detection and bridge activation improved on controls and live audit trail, but mechanical cycling and decision sequence unchanged in BB13.

---

## 15. Remaining Capability Gap

Planner-level tool-based `_novelty_bonus` still inflates candidate scores before portfolio gating; selected mechanical candidates may retain rank despite portfolio ERV adjustment on frontier rebuilds not affecting planner winner.

---

## 16. Recommended Next Step (proposal only)

**Phase 3H.13:** Propagate gated portfolio novelty into planner candidate scoring or global allocator rank reconciliation — without retuning base weights — so representation-only candidates lose planner-level preference when semantic evidence proves same-question status.

---

## Answer

**Can Mr.BOT now distinguish a genuinely new scientific question from the same question merely expressed through a different experimental representation?**

**Partially yes.** With branch-context enrichment and canonical proposition cores, the system now correctly classifies same-question/different-tool pairs (verified synthetically and in BB13 novelty audit with 29 representation-only gates). It preserves genuinely distinct questions (T9 counterfactual unchanged). However, the autonomous session still followed the same decision path as BB11/BB12 because gating activated on frontier opportunities without sufficient rank impact at planner selection points. The identity capability is substantially improved; full behavioral change awaits downstream rank integration.

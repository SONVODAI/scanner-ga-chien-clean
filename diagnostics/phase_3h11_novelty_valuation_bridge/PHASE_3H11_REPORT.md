# Phase 3H.11 — Evidence-Gated Novelty Valuation Bridge

## Verdict: **PARTIAL / INCONCLUSIVE**

The bridge is correctly implemented, tested, and wired into the portfolio valuation path with fail-closed semantics. Live BB12 behavior was **identical to BB11** because semantic relationship evidence did not classify any ranked candidate as representation-only (`gating_applied_count = 0`).

---

## 1. Branch / Commits

| Commit | Description |
|--------|-------------|
| `978315845` | Pre-registration (matrix, gates, test spec) |
| `fd6f7b44b` | Implementation + synthetic tests |
| `fec3d2ab7` | BB11 replay artifacts + BB12 orchestration |
| *(post-run)* | BB12 frozen blind session artifacts |

**Branch:** `cursor/phase-3h11-novelty-valuation-bridge-aad2`

---

## 2. Files Changed (research)

| File | Change |
|------|--------|
| `modules/edge_research/research_novelty_valuation_bridge.py` | **New** — classification + gating |
| `modules/edge_research/research_portfolio.py` | Bridge integration in `build_opportunity_from_candidate` |
| `modules/edge_research/research_state.py` | `research_novelty_gating_audit` session field |
| `modules/edge_research/research_global_allocator.py` | Pass `defer_evidence_snapshot` to frontier rebuild |
| `tests/test_edge_research_novelty_valuation_bridge.py` | **New** — synthetic tests A–G |

**Not changed:** planner weights, 3H.8 exit formula, 3H.6 IV bridge, dedup, grammar/templates.

---

## 3. Architecture Change

```
Planner novelty (unchanged)
  → portfolio build_opportunity_from_candidate()
      raw novelty_component = novelty × (WEIGHT_NOVELTY_PORTFOLIO / 2.0)
      apply_novelty_valuation_bridge()   ← 3H.11 NEW
          derive_identity_from_candidate (3H.10)
          build_semantic_marginal_evidence (3H.10)
          classify_novelty_valuation()
          gate_novelty_component()  → zero only for REPRESENTATION_NOVELTY_ONLY
      gated novelty → expected_research_value
      record_novelty_gating_audit()
```

Gating is portfolio-layer only. Zero means removal of novelty bonus, never a penalty.

---

## 4. Pre-Registered Semantic Matrix

| Class | Gating | Condition |
|-------|--------|-----------|
| REPRESENTATION_NOVELTY_ONLY | **0×** | IDENTICAL / NEAR_DUPLICATE / SAME_QUESTION_DIFFERENT_INSTRUMENT (unless evidence novelty) |
| EVIDENCE_NOVELTY | 1× | Fresh evidence available |
| SCIENTIFIC_NOVELTY | 1× | GENUINELY_INDEPENDENT / RELATED_BUT_DISTINCT / SAME_UNCERTAINTY_DIFFERENT_SLICE |
| INSUFFICIENT_EVIDENCE | 1× (fail closed) | Cannot prove representation sameness |
| LEGACY_NO_SEMANTIC_CONTEXT | 1× | No candidate identity |

---

## 5. Tests and Results

| Suite | Result |
|-------|--------|
| `test_edge_research_novelty_valuation_bridge.py` (A–G) | **11/11 PASS** |
| `test_edge_research_semantic_research_line.py` (3H.10) | **31/31 PASS** |
| Full edge_research regression | **674 passed, 1 skipped** |

Synthetic tests confirm: representation → 0, evidence/scientific preserved, fail-closed, no negative penalty, legacy path unchanged.

---

## 6. Frozen-Invariant Audit

```json
{
  "planner_weights_unchanged": true,
  "exit_formula_unchanged": true,
  "information_value_bridge_unchanged": true,
  "experiment_dedup_unchanged": true
}
```

BB12 capability gates A–L (frozen subsystems): **PASS**. Gate M (mechanical cycling vs BB11): **PARTIAL** (unchanged).

---

## 7. BB11 Counterfactual Replay (T4 / T8 / T9 / T11)

| Transition | Tool | Semantic Relationship | Valuation Class | Novelty Δ | ERV Rank Effect | STOP Change |
|------------|------|----------------------|-----------------|-----------|-----------------|-------------|
| T4 | adaptive_partition_compare | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | 0.0 | unchanged | no |
| T8 | adaptive_partition_compare | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | 0.0 | unchanged | no |
| T9 | threshold_exploration | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | 0.0 | unchanged | no |
| T11 | (STOP) | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | 0.0 | unchanged | no |

Offline replay could not establish representation-only relationships from BB11 diary/registry state. No independent opportunity became competitive in replay-only mode.

---

## 8. BB12 Results

- **Session:** `bb12-autonomous-001`
- **Frozen commit:** `fd6f7b44b`
- **Fingerprint:** `c4a6affaff536a12…` (same as BB11)
- **Budget:** 12 | **Used:** 11
- **Terminal:** `NO_EDGE_FOUND` (justified STOP at T11)
- **Novelty audit entries:** 300
- **Gating applied:** 0
- **Valuation classes:** SCIENTIFIC_NOVELTY=264, LEGACY=36, REPRESENTATION=0

---

## 9. BB11 vs BB12 Comparison

| Metric | BB11 | BB12 | Δ |
|--------|------|------|---|
| Experiments | 11 | 11 | 0 |
| Terminal status | NO_EDGE_FOUND | NO_EDGE_FOUND | — |
| Mechanical cycling (total) | 3 | 3 | 0 |
| Late mechanical cycling | 2 | 2 | 0 |
| Premature STOP | 0 | 0 | 0 |
| Unexplored frontier at STOP | 36 | 36 | 0 |
| Tool distribution | identical | identical | — |
| Novelty gating applied | 0 | 0 | 0 |
| Representation gated | 0 | 0 | 0 |

BB12 reproduced BB11 decision sequence exactly. The bridge audited all frontier rebuilds but never zeroed novelty because live semantic evidence classified candidates as `RELATED_BUT_DISTINCT` (scientific preserve) or legacy path—not `SAME_QUESTION_DIFFERENT_INSTRUMENT`.

---

## 10. Acceptance Criteria Assessment

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Representation-only novelty receives zero reward | **PASS** (synthetic); **NOT OBSERVED** (live) |
| 2 | Genuine scientific novelty retained | **PASS** |
| 3 | Fresh evidence remains researchable | **PASS** (synthetic) |
| 4 | Mechanical cycling decreases | **FAIL** (3 → 3) |
| 5 | No material premature STOP increase | **PASS** (0 → 0) |
| 6 | No regression in independent-line exploration | **PASS** (identical session) |
| 7 | No market-specific logic | **PASS** |
| 8 | Frozen subsystem invariants intact | **PASS** |

---

## 11. Remaining Failure Modes

1. **Proposition-key granularity:** Mechanical tool switches on the same uncertainty are classified `RELATED_BUT_DISTINCT` instead of `SAME_QUESTION_DIFFERENT_INSTRUMENT`, so gating never fires.
2. **Early-session legacy path:** 36/300 audit entries used `LEGACY_NO_SEMANTIC_CONTEXT` before identity registry is populated.
3. **Planner novelty bonus unchanged:** Tool-based planner `_novelty_bonus` still inflates candidate scores upstream; portfolio gating alone may be insufficient when semantic evidence is conservative.
4. **Single-session replication:** One BB12 run; identical BB11 replay could reflect deterministic allocator + same commit lineage rather than gating effect.

---

## 12. Recommendation for Next Capability

**Phase 3H.12 (proposed): Proposition-Key Resolution for Same-Question Detection**

Tighten `derive_identity_from_candidate` / relationship classifier so that auditable same-proposition pairs (shared proposition key, different instrument only) reliably map to `SAME_QUESTION_DIFFERENT_INSTRUMENT` before portfolio gating can act. This stays within semantic machinery—not planner retuning or market-specific logic.

---

## Answer

**Did Phase 3H.11 make Mr.BOT better at spending research budget on genuinely new scientific directions rather than merely new representations of old directions?**

**Not yet in live autonomous behavior.** The valuation bridge is correctly placed and fail-closed, and synthetic tests prove the gating logic works. However, BB12 showed zero live gating events because 3H.10 semantic evidence did not classify the mechanical-cycling candidates as representation-only. Research budget allocation was unchanged from BB11. The capability is **installed but not yet activated** by sufficient semantic sameness proof at the decision points that matter.

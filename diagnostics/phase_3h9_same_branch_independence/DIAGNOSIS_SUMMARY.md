# Phase 3H.9 — Same-Branch Independence Diagnosis Summary

**Status:** DIAGNOSIS ONLY | **BB12:** NOT RUN | **Research:** NOT MODIFIED

## Frozen Evidence
- Phase 3H.8 @ `5c62fc334`
- BB11 @ `84d689b0d`

## Key Findings

### Structural vs Semantic Branches
- **Structural branch roots (BB11):** 1
- **Semantic/scientific branches (BB11):** 6

### Mechanical Cycling (T4, T8, T9)
- **T4:** SAME_QUESTION_DIFFERENT_TOOL — adaptive_partition_compare (ERV 5.49), relationship=INSUFFICIENT_EVIDENCE, gain_after=MEDIUM
- **T8:** SAME_QUESTION_DIFFERENT_TOOL — adaptive_partition_compare (ERV -1.10), relationship=INSUFFICIENT_EVIDENCE, gain_after=MEDIUM
- **T9:** SAME_QUESTION_DIFFERENT_TOOL — threshold_exploration (ERV 5.78), relationship=INSUFFICIENT_EVIDENCE, gain_after=MEDIUM

### Revisit Freshness
- Fresh revisits: 2
- Stale/same-evidence revisits: 2

### Primary Bottleneck
**S1 — SCIENTIFIC IDENTITY NOT REPRESENTED**

### Secondary Bottleneck
**S3 — MARGINAL DECAY DOES NOT TRANSFER ACROSS SEMANTIC EQUIVALENTS**

### Recommended Next Treatment
Semantic research-line identity + decay transfer at scientific-question level (NOT branch_root_id alone)

### Must NOT Change
3H.8 exit valuation, STOP logic, 3H.6 IV, planner weights, ERV formulas, allocator ranking, dedup, budget lifecycle

---
*Generated 2026-08-21T16:11:48Z — diagnostic artifacts only*

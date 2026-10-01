# Phase 3H.7 Branch Saturation / Exit Diagnosis

## Primary Finding
B10-G STOP LOGIC PROBLEM + B10-B SATURATION NOT VALUED AS EXIT

## Secondary Finding
B10-H REVISIT SAME BRANCH + B10-J IV DECAY MISMATCH

## BB10 Branch Lifecycle
- 12/12 experiments on single branch root `obs-b08a47b141fd`
- Branch switches: 0
- Late mechanical cycling: 2/5 (improved from BB09 4/5)
- Marginal ERV deteriorates from T7; T8–T11 are least-bad continuations

## Key Mechanisms
1. **STOP not competitive** — STOP_SESSION hardcoded -100 planner penalty
2. **15.3** — global stop uses historical frontier score (8.7) not revalued ERV (-4 to -1)
3. **Saturation signals exist** but do not gate exit
4. **REVISIT/FRONTIER** return to same branch_root — not independent branches
5. **3H.6 IV redundancy** is uncertainty-topology level, not branch cumulative decay

## Recommended Next Treatment
Branch-exit valuation: make STOP/budget-preservation compete against negative-ERV continuations using revalued opportunity set; branch-level marginal decay signal (diagnostic flag first)

## Must NOT Change
- Phase 3H.6 Information Value scales and pathways
- Grammar / candidate generation
- Competence layer (audit-only)
- Global allocator semantics (without evidence-based exit treatment)
- Forced exploration / branch quotas
- BB01–BB10 frozen artifacts

Generated: 2026-08-21T15:46:23Z

# Research Panel Coverage Repair Report

**Branch:** `cursor/land-phase-3k5a-autonomous-stack-aad2` (PR #83)  
**Stop:** timer remains DISABLED — wait for explicit activation

## A. Root cause

Research panel defaulted to **`pattern_lifecycle.csv`**.

`modules/earning_learning._build_pattern_lifecycle` builds lifecycle by **pivoting `outcomes.csv` then left-merging observations**. Observations with **no outcomes yet never appear** in lifecycle.

App EOD path writes `observations.csv` + `t0_observation_freeze.csv` through **2026-08-24**, but lifecycle/`verified_decisions` stop at **2026-08-19** until T3+ outcomes exist.  
`build_research_panel(source="pattern_lifecycle")` therefore lagged the live app by design (outcome-gated membership), not missing snapshots.

## B. Source availability

| Date | Source | Rows / universe | Core T0 fields | Panel eligibility |
|------|--------|-----------------|----------------|-------------------|
| 2026-08-20 | observations + freeze | 142 / 142 | rsi14, rs5, rs10, price present | **SAFE** |
| 2026-08-21 | observations + freeze | 142 / 142 | same | **SAFE** |
| 2026-08-24 | observations + freeze | 142 / 142 | same | **SAFE** |

Outcomes for these entry dates: **0** (expected — horizons not mature). That is why lifecycle lagged; not why T0 panel must lag.

## C. Repair

| File | Change |
|------|--------|
| `modules/edge_research/adapters.py` | Default panel source → `production_t0` (observations + freeze overlay); legacy `pattern_lifecycle` retained |
| `modules/edge_research/research_capability_registry.py` | Wire observations/freeze as panel sources |
| `modules/edge_research/opr_bridge/production_readiness_audit.py` | Document production_t0 inputs |
| `modules/edge_research/opr_bridge/production_observation_cutoff.py` | Dataset identities include observations/freeze |
| `tests/test_edge_research_panel_production_t0_coverage.py` | Coverage regression |

No manual panel edits; no hard-coded dates.

## D. Future behavior

Each new EOD that lands in `observations.csv` / `t0_observation_freeze.csv` enters the research panel **the same day**, without waiting for outcome maturity. Forward labels still join from `outcomes.csv` only when present (no look-ahead fabrication).

## E. Catch-up decision (panel T0)

| Date | Classification | Why |
|------|----------------|-----|
| 2026-08-20 | **SAFE_TO_RECONSTRUCT** | Complete T0 obs+freeze; no future fields required for panel membership |
| 2026-08-21 | **SAFE_TO_RECONSTRUCT** | same |
| 2026-08-24 | **SAFE_TO_RECONSTRUCT** | same |

Autonomous *research session history* for those days is **not** fabricated (see F).

## F. Production baseline

**HONEST_START_NOW** at first safe current cutoff **`2026-08-24`**.

- Durable LIVE/BACKFILL autonomous observations remain **0** (smoke-only artifacts exist).
- Do **not** invent multi-day autonomous history for 08-20…08-24.
- Optional later: explicit `BACKFILL_NON_FORWARD` per date if operators choose — not default.

## G. Backup / Restore

| Gate | Result |
|------|--------|
| Restore verification | **PASS** (non-destructive `create_live_forward_backup` + integrity verify) |
| Backup | **PASS_WITH_OPERATOR_ACTION** (audit design: remains operator action even when integrity_ok) |

Operator action before production LIVE_FORWARD enable on VPS:

```bash
python -c "from modules.edge_research.opr_bridge.production_backup import create_live_forward_backup; print(create_live_forward_backup())"
```

(or equivalent scheduled backup once LIVE_FORWARD records exist)

## H. DAY_0_SMOKE (latest EOD 2026-08-24)

| Check | Result |
|-------|--------|
| Target in panel | YES (142 rows) |
| Readiness | READY |
| Lock | acquired |
| Run disposition | SUCCESS (`DAY_0_SMOKE`) |
| Idempotency path | supported (prior frozen runs replay) |
| Forward evidence | false |
| Calibration contamination | false |
| Promotable | false |
| UI available | true |
| Isolated namespace | day0_smoke_namespace |

## I. Scheduler

**DISABLED** — `activated: false`; timer not installed/enabled.

## J. Activation verdict

**`READY_TO_ACTIVATE`**

Panel coverage blocker cleared. Remaining non-code item: operator Backup acknowledgment on VPS when enabling LIVE_FORWARD later.  
**STOP — wait for explicit timer activation instruction.**

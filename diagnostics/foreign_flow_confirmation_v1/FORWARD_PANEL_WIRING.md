# Forward Panel Wiring Report

## Verdict

`FOREIGN_FLOW_FORWARD_PANEL_READY_TO_DEPLOY`  
`FORWARD_CONFIRMATION_CAN_START_AFTER_DEPLOY = YES`

## What was built

| Piece | Path |
|-------|------|
| Forward panel store | `data/foreign_flow_confirmation/forward_panel/by_symbol/` |
| Daily ingest + events + maturity | `modules/foreign_flow_confirmation/daily.py` |
| Exact-date HSX gate | `modules/foreign_flow_confirmation/exact_date.py` |
| Continuity join | `modules/foreign_flow_confirmation/continuity.py` |
| Cohort freeze | `modules/foreign_flow_confirmation/cohort.py` |
| Daily hook (no new timer) | `modules/forecast_research/production_daily_integration.py` → after P0, fail-safe |

## Symbol cohort

117 HOSE symbols = intersection of `ems142_hsx_eligibility.json` hose_eligible ∩ freeze coverage. HNX/UPCOM not fabricated.

## Tests

`tests/test_foreign_flow_confirmation_forward_panel.py` — **14 passed** (mocked provider; no live deploy).

## Operational note

At wiring time: **0** post-freeze T0 events in confirmation ledger; forward panel empty. No live HSX ingest executed in this task.

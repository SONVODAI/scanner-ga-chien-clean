# First Live Acceptance — Foreign Flow Confirmation

Infrastructure can be healthy **without** any candidate trigger.

## Checklist (after deploy + ≥1 timer cycle or manual gated stage)

1. **Correct HEAD** — `git merge-base --is-ancestor bc8152810554129e31a9f59437e0e3c6583462ca HEAD` succeeds (tip may be `fe613c7e2` with docs)
2. **Market/Forecast/Edge healthy** — daily research result not FAILED solely due to confirmation; Forecast Memory stage present; Edge disposition unchanged by ff hook errors
3. **Hook executes** — stage payload / status contains `ff_confirmation_forward` (not missing key). Acceptable: `ok=true`, or `partial_*`, or `WAITING` via MDT0 gate skip
4. **Exact-date rows** — if session `trade_date > 2026-08-24` ingested: `forward_panel/by_symbol/*.csv` rows have that exact date only
5. **Events frozen-definition only** — any `events.jsonl` lines use only  
   `FFC1_PRIMARY_ABN_ABS_Z20_T10` / `FFC1_SECONDARY_NET_HI_PCT90_T10` / `FFC1_OPTIONAL_STREAK_NEG_LE_M5_T10`
6. **Zero duplicate keys** — unique `event_id` set size == line count
7. **60/252 continuity** — freeze canonical present; joined series length sufficient for symbols with events (or DQ reject if incomplete — fail-closed OK)
8. **No performance metrics exposed** — `status/OPERATOR_COUNTS.json` has no mean/win/incremental/bps/leaderboard
9. **Only existing timer** — `systemctl list-timers` shows no new confirmation timer
10. **Rerun idempotent** — second same-day stage: `n_skipped_already` or zero new duplicate events

## Manual stage (only if MDT0 exists for target date)

```bash
TD=YYYY-MM-DD  # must be > 2026-08-24
/opt/mrbot-camera-venv/bin/python - <<PY
import json
from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
from pathlib import Path
repo=Path("/opt/mrbot-camera")
out=run_forecast_memory_daily_stage(
    "$TD",
    data_dir=repo/"data"/"forecast_research",
    ems_path=repo/"data"/"earning_money_snapshots.csv",
    md_path=repo/"data"/"earning_learning"/"market_daily_t0.csv",
)
print(json.dumps({
  "stage_disposition": out.get("stage_disposition"),
  "ff": {k: out.get("ff_confirmation_forward",{}).get(k)
         for k in ("ok","reason","written","latest_successfully_ingested_trade_date","events","maturity")}
}, indent=2, default=str))
PY
```

## Delayed operational ingest

If post-freeze dates already elapsed at deploy time, ingest with frozen definitions and label delayed operational ingestion via checkpoint `delayed_operational_ingest=true`.  
Do **not** peek matured performance to alter eligibility.

# Historical FC Recovery + MDRR V1 — Delivery Notes

**Verdict:** `HISTORICAL_RECOVERY_AND_MDRR_COMPLETE`

## Historical recovery (`data/forecast_research/historical_market_core.csv`)

| Metric | Value |
|---|---|
| Trading sessions recovered | **42** |
| Earliest → latest | **2026-06-25 → 2026-08-24** |
| With FC | 42 |
| With REAL | 33 |
| With LIVE | 8 |
| With breadth fields | 38 |
| Ambiguous FC (unresolved) | **0** (EL multi-FC dates fall back to EMS board recon) |
| Excluded weekends | 10 calendar dates in root PH |

### Quality tiers
- `PIT_SAFE_COMPLETE`: 8
- `PIT_RECONSTRUCTABLE`: 9
- `LEAKAGE_RISK_SOURCE`: 21 (root PH; T0-safe columns only; `t*_return` never copied)
- `NOT_PROVABLY_PIT_SAFE`: 4 (buy_elite-only early dates)

Forecast `forecast_t0_daily` contract **unchanged** — historical core is a separate layer.

## MDRR V1 (`data/forecast_research/mdrr_daily.csv`)

- Backfilled **17** EMS dates (8 COMPLETE, 9 PARTIAL)
- Forward-only registry: `forward_only_feature_registry.json`
- No outcome fields; `camera_coupled=false`
- Hooked after canonical `market_daily_t0` via existing fail-safe path

## CLI
```bash
python -m modules.forecast_research.daily_entrypoint --recover-historical
python -m modules.forecast_research.daily_entrypoint --mdrr-backfill
python -m modules.forecast_research.daily_entrypoint --all-research-memory
```

## Tests
`tests/test_historical_recovery_and_mdrr_v1.py` + `tests/test_forecast_data_contract_v1.py` — 25 passed.

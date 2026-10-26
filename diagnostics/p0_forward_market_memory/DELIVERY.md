# P0 Forward Market Memory — delivery

**Verdict:** `P0_FORWARD_MARKET_MEMORY_PARTIAL`

Foreign-flow **collector is implemented** but live SSI iBoard heatmap is Cloudflare-blocked in this environment (returns SOURCE_ERROR → NULL, never 0). Universe turnover + VNINDEX technicals collect successfully.

## Canonical store
`data/forecast_research/p0_market_daily.csv` (immutable first-write-wins; does not rewrite MDT0/MDRR/Forecast T0)

## Lifecycle
`providers (SSI / EMS / vnstock VNI) → p0_market_daily raw → derived ADV + VNI tech → registry; MDRR unchanged for past freezes`

## CLI
```bash
python -m modules.forecast_research.daily_entrypoint --p0-collect
python -m modules.forecast_research.daily_entrypoint --p0-collect --trade-date YYYY-MM-DD
```

Hooked fail-safe after canonical `market_daily_t0`.

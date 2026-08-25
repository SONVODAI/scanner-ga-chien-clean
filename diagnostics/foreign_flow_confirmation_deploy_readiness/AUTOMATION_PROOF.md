# Automation Proof — Unattended Path

## Exact path (no second timer)

```
mrbot-daily-research.timer
  (Mon–Fri 18:35 / 20:05 / 22:35 Asia/Ho_Chi_Minh)
    → mrbot-daily-research.service (Type=oneshot)
      → production_daily_run_entrypoint
        → run_production_daily_research
          → _finish_daily_run
            → attach_forecast_memory_to_daily_run_result
              → run_forecast_memory_daily_stage
                  MDT0 gate
                  → Forecast T0 freeze
                  → maturity / MDRR / historical_core
                  → P0 market memory
                  → ff_confirmation_forward   ★ NEW
                       → maybe_run_ff_confirmation_after_market_daily
                         → exact-date per-symbol HSX ingest
                         → frozen candidate event append
                         → mature due T10 outcomes
                         → counts-only status
```

## Confirmations

| Check | Result |
|-------|--------|
| Second confirmation timer | **NONE** (no `*foreign*confirm*.timer`) |
| Streamlit dependency | **NONE** — stage is orchestrator-driven |
| Retry on later timer cycles | **YES** — checkpoint + incomplete_symbols resume; WAITING_FOR_DATA retry already in daily research |
| Confirmation failure changes Edge/Forecast/P0 disposition | **NO** — isolated try/except; payload key only |
| Idempotent same-day replay | **YES** — first-write-wins panel; duplicate event/outcome keys rejected |
| P0 mutation by confirmation | **NO** — writes only under `data/foreign_flow_confirmation/` |

## Code anchors

- Timer: `deploy/systemd/mrbot-daily-research.timer`
- Service: `deploy/systemd/mrbot-daily-research.service`
- Finish hook: `production_daily_run_orchestrator._finish_daily_run`
- Stage: `production_daily_integration.run_forecast_memory_daily_stage`
- Confirmation: `foreign_flow_confirmation.daily.maybe_run_ff_confirmation_after_market_daily`

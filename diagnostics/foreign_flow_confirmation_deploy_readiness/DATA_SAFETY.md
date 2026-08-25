# Data Safety — Confirmation Deploy

## Paths touched by confirmation code

| Path | Deploy action |
|------|----------------|
| `data/foreign_flow_confirmation/**` | Create empty namespace OK (events/outcomes/forward_panel/status) |
| `data/foreign_flow_history/manifests/research_freeze.json` | Seed metadata only |
| `data/foreign_flow_history/canonical/by_symbol/*.csv` | **Separate rsync** for lookback; never `git checkout -- data/` |
| `modules/**` | Code only |

## Must NOT overwrite on VPS

- `data/foreign_flow_history/canonical/**` existing freeze (if already present) — merge/rsync carefully; no shrink
- `pattern_history.csv` / Pattern Memory stores
- `data/forecast_research/**` runtime CSVs
- `data/edge_research/**`
- Camera / intraday stores
- `data/earning_learning/**` including `market_daily_t0.csv`
- `data/forecast_research/p0_market_daily.csv`

## Repo seed vs production runtime

Confirmation seed files under `data/foreign_flow_confirmation/` are empty ledgers/status templates.  
They must **not** replace a newer production confirmation ledger if one already exists.

**Rule:** after `git checkout` of the integrate ref, **do not** run:

```bash
git checkout HEAD -- data/forecast_research data/earning_learning data/edge_research pattern_history.csv
git clean -fd data/foreign_flow_confirmation   # if live events already exist
```

If `data/foreign_flow_confirmation` already has events on VPS, keep them (first-write-wins / append-only semantics).

## Freeze history sync (mandatory for 60/252 continuity)

Without `canonical/by_symbol` history through `2026-08-24`, post-freeze triggers fail lookback DQ (fail-closed).  
Sync **only**:

```text
data/foreign_flow_history/canonical/by_symbol/*.csv
data/foreign_flow_history/manifests/research_freeze.json
```

from the accepted freeze artifact (`ff_hsx_symbol_daily_v1_20260825T045650Z`).  
Do **not** sync `raw/*.jsonl` unless needed for audit.  
Do **not** run Stage B backfill on VPS.

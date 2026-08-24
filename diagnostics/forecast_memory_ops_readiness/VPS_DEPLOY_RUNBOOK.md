# Forecast Memory — VPS Deploy Runbook

**Integration branch:** `cursor/forecast-memory-prod-integrate-aad2`  
**Base:** production `8514fd7b2` + 9 forecast commits + automation fix  
**Do not deploy until operator confirms.**

---

## Pre-deploy

```bash
cd /opt/mrbot-camera
git rev-parse HEAD | tee /tmp/mrbot-pre-forecast-memory.HEAD
git status -sb | tee /tmp/mrbot-pre-forecast-memory.status
git branch --show-current | tee /tmp/mrbot-pre-forecast-memory.branch
systemctl status mrbot-daily-research.timer --no-pager | tee /tmp/mrbot-pre-forecast-memory.timer
systemctl status mrbot-daily-research.service --no-pager | tee /tmp/mrbot-pre-forecast-memory.service
systemctl list-timers --all | grep -i mrbot | tee /tmp/mrbot-pre-forecast-memory.timers
df -h /opt /var | tee /tmp/mrbot-pre-forecast-memory.df

TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /var/backups/mrbot-forecast-memory-$TS
cp -a data/earning_learning /var/backups/mrbot-forecast-memory-$TS/ 2>/dev/null || true
cp -a data/forecast_research /var/backups/mrbot-forecast-memory-$TS/ 2>/dev/null || true
cp -a data/edge_research /var/backups/mrbot-forecast-memory-$TS/ 2>/dev/null || true
```

---

## Deploy

```bash
cd /opt/mrbot-camera
git fetch origin cursor/forecast-memory-prod-integrate-aad2
# Replace COMMIT with exact tip printed in FINAL_INTEGRATION_REF
git checkout cursor/forecast-memory-prod-integrate-aad2
git pull origin cursor/forecast-memory-prod-integrate-aad2

# No package upgrade unless import smoke fails
/opt/mrbot-camera-venv/bin/python -c "import vnstock; print('vnstock', vnstock.__version__)"
```

**Data safety:** do **not** run `git checkout -- data/forecast_research` or reset production CSVs.

---

## Test (on VPS if practical)

```bash
cd /opt/mrbot-camera
/opt/mrbot-camera-venv/bin/python -c "
from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
from modules.forecast_research.p0_universe_foreign import UniverseForeignFlowCascade
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import run_production_daily_research
print('import_ok')
"

# Optional focused gate (if pytest available):
# /opt/mrbot-camera-venv/bin/python -m pytest -q tests/test_forecast_memory_daily_integration.py

# Idempotent stage only when MDT0 exists for target date:
TD=$(date +%F)   # or prior session YYYY-MM-DD
/opt/mrbot-camera-venv/bin/python - <<'PY'
import json
from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
from pathlib import Path
repo = Path("/opt/mrbot-camera")
print(json.dumps(run_forecast_memory_daily_stage(
    "REPLACE_TD",
    data_dir=repo / "data" / "forecast_research",
    ems_path=repo / "data" / "earning_money_snapshots.csv",
    md_path=repo / "data" / "earning_learning" / "market_daily_t0.csv",
    require_mdt0=True,
), indent=2, default=str)[:4000])
PY
```

---

## Automation

```bash
systemctl is-enabled mrbot-daily-research.timer
systemctl status mrbot-daily-research.timer --no-pager
systemctl list-timers mrbot-daily-research.timer --no-pager
systemctl list-timers --all | grep -i forecast || echo "OK: no forecast timer"
# Expected: Mon–Fri 18:35 / 20:05 / 22:35 Asia/Ho_Chi_Minh
# Type=oneshot → inactive (dead) after SUCCESS is normal
```

Forecast Memory now runs as an isolated stage inside `run_production_daily_research` after Edge phases, gated on canonical MDT0.

---

## Post-deploy inspect

```bash
cd /opt/mrbot-camera
DATE=YYYY-MM-DD   # target session
grep "$DATE" data/forecast_research/forecast_t0_daily.csv
grep "$DATE" data/forecast_research/mdrr_daily.csv
grep "$DATE" data/forecast_research/p0_market_daily.csv
python3 - <<'PY'
import pandas as pd
d="YYYY-MM-DD"
p=pd.read_csv("data/forecast_research/p0_market_daily.csv")
r=p[p.trade_date.astype(str).str[:10]==d].iloc[-1]
print({k:r.get(k) for k in [
 "universe_foreign_completeness","universe_foreign_source",
 "universe_foreign_observed_count","universe_foreign_expected_count",
 "universe_foreign_net_value"]})
PY
journalctl -u mrbot-daily-research.service --since "yesterday" --no-pager | tail -80
```

---

## Rollback

```bash
cd /opt/mrbot-camera
PRE=$(cat /tmp/mrbot-pre-forecast-memory.HEAD)
git checkout -f "$PRE"
systemctl daemon-reload 2>/dev/null || true
systemctl status mrbot-daily-research.timer --no-pager
# Preserve data/forecast_research/ unless corrupted
```

---

## App smoke (after operational validation)

Restart Streamlit/app **only if** deploy changed code requiring it:

```bash
# operator-specific service name
systemctl restart mrbot-streamlit 2>/dev/null || true
```

Verify: Market First renders, Edge Research UI intact, no import errors in logs.

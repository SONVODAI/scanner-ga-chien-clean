# VPS Deploy Runbook — Foreign Flow Confirmation

**Deploy exact ref:** `bc8152810` (`cursor/foreign-flow-confirmation-prod-integrate-aad2`)  
**Do NOT deploy:** `origin/main`, PR #97 tip `df73282aa`, or any WIP backfill branch.  
**This task does not deploy.** Operator executes on `/opt/mrbot-camera`.

---

## Before

```bash
cd /opt/mrbot-camera

# 1) Record live production HEAD (authoritative)
git rev-parse HEAD | tee /tmp/mrbot-pre-ff-confirm.HEAD
git rev-parse --short HEAD | tee /tmp/mrbot-pre-ff-confirm.HEAD.short
git status -sb | tee /tmp/mrbot-pre-ff-confirm.status
git branch --show-current | tee /tmp/mrbot-pre-ff-confirm.branch

# 2) Resources
df -h /opt /var | tee /tmp/mrbot-pre-ff-confirm.df
free -h | tee /tmp/mrbot-pre-ff-confirm.mem

# 3) Timer / service (existing daily research only)
systemctl status mrbot-daily-research.timer --no-pager | tee /tmp/mrbot-pre-ff-confirm.timer
systemctl status mrbot-daily-research.service --no-pager | tee /tmp/mrbot-pre-ff-confirm.service
systemctl list-timers --all | grep -i mrbot | tee /tmp/mrbot-pre-ff-confirm.timers
systemctl list-timers --all | grep -iE 'foreign|confirm|forecast' || echo "OK: no extra confirmation/forecast timer"

# 4) Dependency / import proof (no upgrades)
/opt/mrbot-camera-venv/bin/python - <<'PY' | tee /tmp/mrbot-pre-ff-confirm.deps
import sys
print("python", sys.version)
for n in ("numpy","pandas","scipy","requests"):
    m=__import__(n); print(n, getattr(m,"__version__","?"))
import vnstock
print("vnstock", getattr(vnstock,"__version__", type(vnstock)))
from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
print("forecast_memory_stage_import_ok")
PY

# 5) Backups / hashes of touched runtime stores (do not modify)
TS=$(date -u +%Y%m%dT%H%M%SZ)
BK=/var/backups/mrbot-ff-confirm-$TS
mkdir -p "$BK"
cp -a data/forecast_research "$BK/" 2>/dev/null || true
cp -a data/earning_learning "$BK/" 2>/dev/null || true
cp -a data/edge_research "$BK/" 2>/dev/null || true
cp -a data/foreign_flow_history "$BK/" 2>/dev/null || true
cp -a data/foreign_flow_confirmation "$BK/" 2>/dev/null || true
test -f pattern_history.csv && cp -a pattern_history.csv "$BK/" || true
( cd "$BK" && find . -type f \( -name '*.csv' -o -name '*.json' \) -print0 | sort -z | xargs -0 sha256sum ) \
  > /tmp/mrbot-pre-ff-confirm.hashes || true
echo "BACKUP=$BK"
```

**Gate:** If `run_forecast_memory_daily_stage` import fails, live HEAD lacks Forecast Memory — still OK to checkout integrate ref `bc8152810` (includes FM tip ancestry), but treat as larger stack deploy and re-validate FM after checkout.

---

## Deploy

```bash
cd /opt/mrbot-camera
git fetch origin cursor/foreign-flow-confirmation-prod-integrate-aad2
git checkout bc8152810554129e31a9f59437e0e3c6583462ca
# optional named branch:
# git checkout -B cursor/foreign-flow-confirmation-prod-integrate-aad2 bc8152810554129e31a9f59437e0e3c6583462ca

git rev-parse HEAD | tee /tmp/mrbot-post-ff-confirm.HEAD
test "$(git rev-parse HEAD)" = "bc8152810554129e31a9f59437e0e3c6583462ca"

# NO package upgrades unless separately approved
# NO: git checkout -- data/...
# NO: Stage B historical backfill
```

### Mandatory freeze lookback sync (if not already present)

```bash
# From trusted freeze artifact host/path — EXAMPLE only; use your approved source
# rsync -a --dry-run .../data/foreign_flow_history/canonical/by_symbol/ \
#   /opt/mrbot-camera/data/foreign_flow_history/canonical/by_symbol/
# Then remove --dry-run after review.

test -f data/foreign_flow_history/manifests/research_freeze.json
python3 - <<'PY'
import json
from pathlib import Path
m=json.loads(Path("data/foreign_flow_history/manifests/research_freeze.json").read_text())
assert m.get("last_trade_date")=="2026-08-24"
canon=Path("data/foreign_flow_history/canonical/by_symbol")
n=len(list(canon.glob("*.csv"))) if canon.exists() else 0
print("freeze_last", m.get("last_trade_date"), "canonical_csv_count", n)
assert n>=100, "freeze canonical history missing — do not claim continuity ready"
PY
```

---

## Validate

```bash
cd /opt/mrbot-camera
/opt/mrbot-camera-venv/bin/python - <<'PY'
from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
from modules.foreign_flow_confirmation.daily import maybe_run_ff_confirmation_after_market_daily, counts_only_status
from modules.foreign_flow_confirmation.ledger import LAST_IN_SAMPLE, compute_pass_fail_guard
from modules.foreign_flow_confirmation.exact_date import fetch_exact_trade_date_row
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import run_production_daily_research
import inspect
assert LAST_IN_SAMPLE=="2026-08-24"
assert "ff_confirmation_forward" in inspect.getsource(run_forecast_memory_daily_stage)
assert compute_pass_fail_guard(10,5,10)[0] is False
print("SMOKE_OK")
print(counts_only_status())
PY

# Optional focused tests if pytest present:
# /opt/mrbot-camera-venv/bin/python -m pytest -q \
#   tests/test_foreign_flow_confirmation_forward_panel.py \
#   tests/test_foreign_flow_canonical_backfill.py \
#   tests/test_forecast_memory_daily_integration.py

mkdir -p data/foreign_flow_confirmation/{events,outcomes,baselines,status,forward_panel/by_symbol,manifests,dq_rejects}
systemctl list-timers --all | grep -i mrbot
# Expect: only existing daily-research (+ intraday if previously enabled) — no new confirmation timer
```

### Idempotency dry check (no need for live HSX if offline)

```bash
/opt/mrbot-camera-venv/bin/python - <<'PY'
# Ensures freeze boundary still rejects pre-freeze T0
from modules.foreign_flow_confirmation.daily import run_confirmation_daily
r=run_confirmation_daily("2026-08-24", skip_fetch=True)
assert r["reason"]=="freeze_boundary"
print("freeze_boundary_ok", r)
PY
```

---

## After first timer cycle

See `FIRST_LIVE_ACCEPTANCE.md`. Do not inspect candidate mean/win/incremental.

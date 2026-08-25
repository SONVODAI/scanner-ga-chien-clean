# VPS Copy/Paste Deploy — Verified Prod d5d46be08 → bc8152810

**Verified production HEAD:** `d5d46be086194088a0bca74f9a0a91ffc75c3c37`  
**Deploy code ref:** `bc8152810554129e31a9f59437e0e3c6583462ca` (`bc8152810`)  
**Preserve:** all runtime data (`forecast_pipeline_status.json`, `data/edge_research/`, `AGENTS.md`, Forecast/Edge/EL/P0/pattern stores).  
**Forbidden:** `git clean`, `git reset --hard`, `git checkout -- data/...`, package upgrades, new timers.

Run on VPS as a single block. Script **exits non-zero** on any failed safety gate.

```bash
#!/usr/bin/env bash
# FF Confirmation deploy — STOP on any failed gate
set -euo pipefail

REPO=/opt/mrbot-camera
PY=/opt/mrbot-camera-venv/bin/python
EXPECTED_PRE=d5d46be086194088a0bca74f9a0a91ffc75c3c37
DEPLOY_REF=bc8152810554129e31a9f59437e0e3c6583462ca
FREEZE_DATA_REF=df73282aa3690227e28fa56c8b7b195e892299f2   # used ONLY for archive-extract of freeze CSVs

cd "$REPO"

echo "========== 0) PRECHECK (verified prod base) =========="
test "$(git rev-parse HEAD)" = "$EXPECTED_PRE" \
  || { echo "STOP: HEAD is $(git rev-parse HEAD), expected $EXPECTED_PRE"; exit 1; }
git rev-parse HEAD | tee /tmp/mrbot-pre-ff-confirm.HEAD
git status -sb | tee /tmp/mrbot-pre-ff-confirm.status
git branch --show-current | tee /tmp/mrbot-pre-ff-confirm.branch || true

# Runtime dirt must remain (do not clean/reset)
grep -E 'forecast_pipeline_status\.json|data/edge_research|AGENTS\.md' /tmp/mrbot-pre-ff-confirm.status \
  && echo "OK: runtime dirt present — will preserve" || echo "NOTE: expected runtime dirt markers not all visible (continue if intentional)"

df -h /opt /var | tee /tmp/mrbot-pre-ff-confirm.df
free -h | tee /tmp/mrbot-pre-ff-confirm.mem

systemctl is-active mrbot-daily-research.timer | tee /tmp/mrbot-pre-ff-confirm.timer-active
test "$(systemctl is-active mrbot-daily-research.timer)" = "active" \
  || { echo "STOP: timer not active"; exit 1; }
systemctl status mrbot-daily-research.timer --no-pager | tee /tmp/mrbot-pre-ff-confirm.timer
systemctl status mrbot-daily-research.service --no-pager | tee /tmp/mrbot-pre-ff-confirm.service || true
systemctl list-timers --all | grep -i mrbot | tee /tmp/mrbot-pre-ff-confirm.timers
systemctl list-timers --all | grep -iE 'foreign|confirm' \
  && { echo "STOP: unexpected foreign/confirm timer present"; exit 1; } \
  || echo "OK: no extra confirmation timer"

"$PY" - <<'PY' | tee /tmp/mrbot-pre-ff-confirm.deps
import sys
assert sys.version_info[:2] == (3, 12), sys.version
import numpy, pandas, scipy, vnstock
print("python", sys.version.split()[0])
print("numpy", numpy.__version__)
print("pandas", pandas.__version__)
print("scipy", scipy.__version__)
print("vnstock", getattr(vnstock, "__version__", "?"))
assert numpy.__version__.startswith("2.")
assert pandas.__version__.startswith("2.")
assert str(getattr(vnstock, "__version__", "")).startswith("4.0")
from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
print("forecast_memory_pre_ok")
PY

echo "========== 1) BACKUP (copy only; no overwrite of live) =========="
TS=$(date -u +%Y%m%dT%H%M%SZ)
BK=/var/backups/mrbot-ff-confirm-$TS
mkdir -p "$BK"
cp -a data/forecast_research "$BK/" 2>/dev/null || true
cp -a data/earning_learning "$BK/" 2>/dev/null || true
cp -a data/edge_research "$BK/" 2>/dev/null || true
cp -a data/foreign_flow_history "$BK/" 2>/dev/null || true
cp -a data/foreign_flow_confirmation "$BK/" 2>/dev/null || true
test -f pattern_history.csv && cp -a pattern_history.csv "$BK/" || true
test -f AGENTS.md && cp -a AGENTS.md "$BK/" || true
( cd "$BK" && find . -type f \( -name '*.csv' -o -name '*.json' \) -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum ) \
  > /tmp/mrbot-pre-ff-confirm.hashes || true
echo "BACKUP=$BK" | tee /tmp/mrbot-pre-ff-confirm.backup

echo "========== 2) DEPLOY CODE ONLY (no data reset) =========="
# Explicit forbidden ops — do not uncomment:
# git reset --hard
# git clean -fd
# git checkout -- data/
# pip install / pip upgrade

git fetch origin cursor/foreign-flow-confirmation-prod-integrate-aad2
git cat-file -t "$DEPLOY_REF" >/dev/null \
  || { echo "STOP: missing $DEPLOY_REF after fetch"; exit 1; }

# Detach to exact tested code ancestor. Leaves untracked + non-conflicting local mods intact.
git checkout --detach "$DEPLOY_REF"

test "$(git rev-parse HEAD)" = "$DEPLOY_REF" \
  || { echo "STOP: post-checkout HEAD $(git rev-parse HEAD) != $DEPLOY_REF"; exit 1; }
git rev-parse HEAD | tee /tmp/mrbot-post-ff-confirm.HEAD
git merge-base --is-ancestor "$EXPECTED_PRE" HEAD \
  || { echo "STOP: verified prod base not ancestor of HEAD"; exit 1; }
echo "OK: HEAD=$DEPLOY_REF (ancestor of d5d46be08 preserved in history)"

# Confirm runtime dirt still present / not wiped
git status -sb | tee /tmp/mrbot-post-ff-confirm.status
test ! -f data/forecast_research/forecast_pipeline_status.json \
  || echo "OK: forecast_pipeline_status.json still present"
test -d data/edge_research && echo "OK: data/edge_research still present" || echo "NOTE: data/edge_research absent (ok if never created as dir yet)"

echo "========== 3) FREEZE LOOKBACK CONTINUITY (60/252) =========="
# research_freeze.json comes with deploy ref; canonical CSVs do NOT.
# Extract ONLY canonical/by_symbol from freeze data commit via archive (does not checkout #97 tip).
mkdir -p data/foreign_flow_history/canonical/by_symbol
CANON_N=$(find data/foreign_flow_history/canonical/by_symbol -name '*.csv' 2>/dev/null | wc -l | tr -d ' ')
if [ "$CANON_N" -lt 100 ]; then
  echo "Canonical CSV count=$CANON_N — extracting freeze CSVs from $FREEZE_DATA_REF (archive only)..."
  git fetch origin "$FREEZE_DATA_REF" 2>/dev/null || git fetch origin cursor/foreign-flow-forward-panel-wiring-aad2 || true
  git cat-file -t "$FREEZE_DATA_REF" >/dev/null \
    || { echo "STOP: cannot resolve freeze data ref $FREEZE_DATA_REF"; exit 1; }
  # Extract into a temp dir then rsync into place (never deletes newer files)
  TMP_FF=$(mktemp -d /tmp/ff-freeze-XXXX)
  git archive "$FREEZE_DATA_REF" data/foreign_flow_history/canonical/by_symbol \
    | tar -x -C "$TMP_FF"
  rsync -a --ignore-existing \
    "$TMP_FF/data/foreign_flow_history/canonical/by_symbol/" \
    "$REPO/data/foreign_flow_history/canonical/by_symbol/"
  rm -rf "$TMP_FF"
fi

test -f data/foreign_flow_history/manifests/research_freeze.json \
  || { echo "STOP: research_freeze.json missing"; exit 1; }

"$PY" - <<'PY' | tee /tmp/mrbot-post-ff-confirm.continuity
import json
from pathlib import Path
m = json.loads(Path("data/foreign_flow_history/manifests/research_freeze.json").read_text())
assert m.get("last_trade_date") == "2026-08-24", m.get("last_trade_date")
assert m.get("symbol_count") == 117, m.get("symbol_count")
canon = Path("data/foreign_flow_history/canonical/by_symbol")
files = sorted(canon.glob("*.csv"))
assert len(files) >= 100, f"canonical_csv_count={len(files)}"
# Spot-check one symbol has >= 252 sessions ending at freeze
import pandas as pd
sample = None
for pref in ("FPT", "VNM", "HPG", "VCB"):
    p = canon / f"{pref}.csv"
    if p.exists():
        sample = p
        break
assert sample is not None, "no sample symbol csv"
df = pd.read_csv(sample, usecols=["trade_date", "foreign_net_value"])
df["trade_date"] = df["trade_date"].astype(str).str[:10]
df = df[df["trade_date"] <= "2026-08-24"]
assert len(df) >= 252, f"{sample.name} rows={len(df)}"
assert df["foreign_net_value"].tail(60).notna().all()
assert df["foreign_net_value"].tail(252).notna().sum() >= 250
print("CONTINUITY_OK", "sample", sample.name, "rows", len(df), "freeze", m["dataset_version"])
PY

echo "========== 4) IMPORT / HOOK / ANTI-PEEK SMOKE =========="
"$PY" - <<'PY' | tee /tmp/mrbot-post-ff-confirm.smoke
import inspect, json, sys
import numpy, pandas, scipy, vnstock
print("python", sys.version.split()[0])
print("numpy", numpy.__version__)
print("pandas", pandas.__version__)
print("scipy", scipy.__version__)
print("vnstock", getattr(vnstock, "__version__", "?"))

from modules.forecast_research.production_daily_integration import run_forecast_memory_daily_stage
from modules.foreign_flow_confirmation.daily import (
    maybe_run_ff_confirmation_after_market_daily,
    counts_only_status,
    run_confirmation_daily,
)
from modules.foreign_flow_confirmation.ledger import LAST_IN_SAMPLE, compute_pass_fail_guard
from modules.foreign_flow_confirmation.continuity import join_history_and_forward, lookback_complete
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import run_production_daily_research

src = inspect.getsource(run_forecast_memory_daily_stage)
assert "ff_confirmation_forward" in src
assert "maybe_run_ff_confirmation_after_market_daily" in src
assert LAST_IN_SAMPLE == "2026-08-24"
assert compute_pass_fail_guard(unique_dates=10, unique_symbols=5, sessions_since_first_t0=10)[0] is False

# Continuity join on a live symbol (history only; asof freeze)
j = join_history_and_forward("FPT", asof_trade_date="2026-08-24")
assert lookback_complete(j, need=60)
assert lookback_complete(j, need=252)
print("JOIN_LOOKBACK_OK", len(j))

# Freeze boundary (no candidate trigger required)
r = run_confirmation_daily("2026-08-24", skip_fetch=True)
assert r.get("reason") == "freeze_boundary", r
print("FREEZE_BOUNDARY_OK")

status = counts_only_status()
blob = json.dumps(status).lower()
for banned in ("mean_ret", "incremental", "win_rate", "leaderboard", "bps"):
    assert banned not in blob, banned
assert status.get("operator_view") == "counts_only_until_final_judgment"
assert status.get("do_not_trade_from_interim") is True
print("ANTI_PEEK_OK")
print(json.dumps({
    "candidates": [
        {k: c.get(k) for k in (
            "candidate_id", "state", "triggers", "matured_t10",
            "unique_symbols", "unique_dates", "final_judgment_allowed"
        )}
        for c in status.get("candidates") or []
    ],
    "latest_successfully_ingested_trade_date": status.get("latest_successfully_ingested_trade_date"),
    "data_quality_errors": status.get("data_quality_errors"),
}, indent=2))
print("SMOKE_OK")
PY

# Ensure confirmation namespace dirs exist (empty OK; do not wipe existing)
mkdir -p data/foreign_flow_confirmation/{events,outcomes,baselines,status,forward_panel/by_symbol,manifests,dq_rejects}

echo "========== 5) IDEMPOTENCY =========="
"$PY" - <<'PY' | tee /tmp/mrbot-post-ff-confirm.idempotency
from modules.foreign_flow_confirmation.daily import run_confirmation_daily
a = run_confirmation_daily("2026-08-24", skip_fetch=True)
b = run_confirmation_daily("2026-08-24", skip_fetch=True)
assert a["reason"] == "freeze_boundary" and b["reason"] == "freeze_boundary"
print("IDEMPOTENT_FREEZE_BOUNDARY_OK")
PY

echo "========== 6) TIMER / SERVICE UNCHANGED =========="
test "$(systemctl is-active mrbot-daily-research.timer)" = "active" \
  || { echo "STOP: timer no longer active after deploy"; exit 1; }
systemctl list-timers --all | grep -i mrbot | tee /tmp/mrbot-post-ff-confirm.timers
systemctl list-timers --all | grep -iE 'foreign|confirm' \
  && { echo "STOP: new confirmation timer appeared"; exit 1; } \
  || echo "OK: still no confirmation timer"
systemctl status mrbot-daily-research.timer --no-pager | tee /tmp/mrbot-post-ff-confirm.timer
# oneshot idle after success is normal
systemctl is-active mrbot-daily-research.service | tee /tmp/mrbot-post-ff-confirm.service-active || true

echo "========== 7) FINAL ACCEPTANCE SUMMARY =========="
echo "PRE_HEAD=$(cat /tmp/mrbot-pre-ff-confirm.HEAD)"
echo "POST_HEAD=$(cat /tmp/mrbot-post-ff-confirm.HEAD)"
echo "BACKUP=$(cat /tmp/mrbot-pre-ff-confirm.backup)"
echo "FOREIGN_FLOW_CONFIRMATION_DEPLOY_ACCEPTED"
```

---

## Rollback (code only — keep confirmation data)

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/mrbot-camera
PRE=$(cat /tmp/mrbot-pre-ff-confirm.HEAD)
test -n "$PRE"
test "$PRE" = "d5d46be086194088a0bca74f9a0a91ffc75c3c37"

# Code only — DO NOT reset/clean runtime data
git checkout --detach "$PRE"
test "$(git rev-parse HEAD)" = "$PRE"

# KEEP:
#   data/foreign_flow_confirmation/**
#   data/foreign_flow_history/canonical/** (freeze lookback)
#   data/forecast_research/**, data/earning_learning/**, data/edge_research/**
#   forecast_pipeline_status.json, AGENTS.md, pattern_history.csv

systemctl is-active mrbot-daily-research.timer
echo "ROLLBACK_CODE_OK HEAD=$(git rev-parse --short HEAD)"
```

---

## Notes

1. Infrastructure acceptance does **not** require a candidate trigger.
2. After the next `mrbot-daily-research.timer` fire, confirm `ff_confirmation_forward` appears in Forecast Memory stage output / pipeline status — still counts-only; do not inspect mean/win/incremental.
3. If step 3 archive-extract fails (object missing), STOP and rsync freeze CSVs from your approved freeze artifact host instead — never `git checkout` the PR #97 tip onto production.

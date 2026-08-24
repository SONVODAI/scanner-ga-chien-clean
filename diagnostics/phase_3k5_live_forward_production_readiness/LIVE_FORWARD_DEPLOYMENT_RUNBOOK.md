# LIVE_FORWARD Deployment Runbook

**Status:** NOT EXECUTED — for human operator use after Phase 3K.5 audit approval  
**Stop boundary:** `STOP_LIVE_FORWARD_PRODUCTION_READINESS_AUDITED`  
**Important:** Rollback may stop infrastructure but must NEVER delete or rewrite legitimate LIVE_FORWARD scientific records.

---

## Prerequisites

- [ ] Phase 3K.5 audit `phase_pass: true`
- [ ] Phase 3K.5A prerequisite closure `phase_pass: true` (`STOP_PRODUCTION_PREREQUISITES_CLOSED`)
- [ ] Approved commit SHA recorded
- [ ] Production host access (SSH)
- [ ] Authoritative EOD complete for target session (`t0_observation_freeze.csv` rows + `market_t0_snapshot` AFTER_CLOSE)
- [ ] VN trading calendar loaded (`config/vn_trading_calendar.json`)
- [ ] Disk space sufficient for `data/edge_research/production_observations/`
- [ ] Backup destination configured (manual backup before genesis — see Step 5b)

---

## Step 1 — Deploy Approved Commit

```bash
cd /path/to/scanner-ga-chien-clean
git fetch origin
git checkout <approved-commit-sha>
# Install dependencies if changed
pip install -r requirements.txt  # if applicable
```

Record: commit SHA, deploy timestamp, operator identity.

---

## Step 2 — Verify Environment

```bash
python3 -m modules.edge_research.opr_bridge.production_daily_run_entrypoint --scheduling-contract
python3 -c "from modules.edge_research.opr_bridge.production_readiness_audit import run_full_production_readiness_audit; import json; print(json.dumps(run_full_production_readiness_audit(), indent=2))"
```

Verify:
- Python >= 3.10
- Timezone: `Asia/Ho_Chi_Minh` on host
- `EDGE_RESEARCH_DATA_DIR` or default `data/edge_research/` writable
- Streamlit (`app.py`) runs separately — runner NOT inside Streamlit

---

## Step 3 — Verify Production Data Source

```bash
python3 -c "
from modules.edge_research.opr_bridge.production_data_discovery import discover_production_data_sources
import json
d = discover_production_data_sources()
assert d['readiness']['primary_panel_available'], d
print('Latest panel date:', d['panel'].get('latest_trade_date'))
"
```

Manual checks:
- `data/earning_learning/pattern_lifecycle.csv` has target date rows
- `data/earning_learning/market_t0_snapshot.csv` has target date AFTER_CLOSE snapshot
- Universe coverage acceptable (operator judgment)

---

## Step 4 — Run DAY_0_SMOKE

```bash
export TARGET_DATE=$(python3 -c "from modules.edge_research.opr_bridge.production_timezone_audit import derive_vn_trade_date; print(derive_vn_trade_date())")

python3 -c "
from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.production_day0_smoke import run_day0_smoke
import json
panel = build_research_panel()
result = run_day0_smoke(panel, target_trade_date='$TARGET_DATE')
print(json.dumps(result, indent=2, default=str))
assert result['counts_as_forward_evidence'] is False
assert result['promotable'] is False
"
```

---

## Step 5 — Inspect Smoke Artifacts

Verify in isolated namespace `production_observations/day0_smoke_namespace/`:
- Readiness passed
- Lock acquired/released
- No contamination of main calibration ledger
- UI read model accessible

**If smoke fails:** STOP. Do not proceed to genesis.

---

## Step 6 — Create Irreversible LIVE_FORWARD Genesis

**This step is irreversible. Execute only after smoke passes.**

```bash
python3 << 'EOF'
from modules.edge_research.opr_bridge.blind_research_examination_runner import compute_research_policy_hashes
from modules.edge_research.opr_bridge.production_data_discovery import discover_production_data_sources
from modules.edge_research.opr_bridge.production_live_forward_genesis import (
    build_genesis_record, persist_genesis, reject_second_genesis_creation
)
from modules.edge_research.opr_bridge.production_timezone_audit import derive_vn_trade_date
import subprocess

ok, reason = reject_second_genesis_creation()
assert ok, reason

commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
policy = compute_research_policy_hashes(".")
discovery = discover_production_data_sources()
first_date = derive_vn_trade_date()  # or next eligible session

genesis = build_genesis_record(
    first_eligible_trade_date=first_date,
    code_commit=commit,
    policy_hashes=policy,
    dataset_identities={
        "panel": discovery["panel"].get("latest_trade_date", ""),
        "pattern_lifecycle": discovery["sources"]["pattern_lifecycle"]["path"],
    },
    deployment_identity="PRODUCTION_HOST_NAME",
)
path = persist_genesis(genesis)
print(f"Genesis persisted: {path}")
print(f"First eligible date: {first_date}")
EOF
```

Record genesis_id, genesis_hash, first_eligible_trade_date.

---

## Step 7 — Install Scheduler Artifacts (Do NOT Enable Until Ready)

Repository artifacts (3K.5A):

```bash
sudo bash deploy/systemd/install-daily-research.sh
sudo cp deploy/systemd/mrbot-daily-research.env.example /etc/mrbot/daily-research.env
# Edit /etc/mrbot/daily-research.env for production paths
sudo systemctl daemon-reload
# DO NOT enable timer yet:
# sudo systemctl enable --now mrbot-daily-research.timer
```

Timer uses `Asia/Ho_Chi_Minh`, post-EOD window, `--derive-vn-date --mode LIVE_FORWARD --use-lock`.

Verify: `activated` remains `false` in scheduling contract until operator explicitly enables.

---

## Step 8 — Execute/Observe First LIVE_FORWARD Day

```bash
python3 -m modules.edge_research.opr_bridge.production_daily_run_entrypoint \
  --trade-date $TARGET_DATE \
  --mode LIVE_FORWARD \
  --use-lock
```

Expected exit code: `0` (SUCCESS)

---

## Step 9 — Verify Persisted Records

```bash
python3 -c "
from modules.edge_research.opr_bridge.production_operational_health import build_operational_health_artifact
import json
h = build_operational_health_artifact()
print(json.dumps(h, indent=2))
assert h['genesis_exists']
assert h['latest_run_mode'] == 'LIVE_FORWARD'
"
```

Check:
- BirthRecord(s) immutable in `production_observations/`
- DailyResearchSummary persisted
- Manifest in `daily_manifests/`
- Calibration ledger updated only if outcomes legally released
- `counts_as_forward_evidence: true` on run record

---

## Step 10 — Verify UI

Open Streamlit app. Navigate to **MR.BOT — HÔM NAY TÔI ĐANG NGHĨ GÌ?**

Verify:
- Authority badge: RESEARCH ONLY
- Run mode: LIVE_FORWARD
- Latest successful date matches Day 1
- Forward evidence panel shows maturity label
- No BUY/SELL language

---

## Step 11 — Verify Trading Isolation

```bash
python3 -c "
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit
from pathlib import Path
r = run_trading_isolation_audit(Path('.'))
assert r['passed'], r
"
```

---

## Step 12 — Verify Backup

Ensure backup includes:
- `live_forward_genesis.json`
- All BirthRecords
- `daily_assessments/`, `forward_outcomes/`, `daily_summaries/`
- `daily_runs/`, `daily_manifests/`
- `forward_evidence_ledger/`, `calibration_snapshots/`

**Never reconstruct forward evidence from hindsight if lost.**

---

## Rollback / STOP Procedure

If infrastructure fails after Day 1:

1. **STOP scheduler** — disable cron/systemd timer
2. **DO NOT** delete or rewrite BirthRecords, assessments, outcomes, or calibration ledger
3. **DO NOT** move genesis backward
4. Investigate via `production_operational_health` artifact
5. Resume only after root cause fixed; use `resume_run_id` for partial runs

---

## Exit Codes Reference

| Code | Meaning |
|------|---------|
| 0 | SUCCESS or idempotent replay |
| 1 | FAILED_CLOSED |
| 2 | WAITING_FOR_DATA |
| 3 | SKIPPED_NON_TRADING_DAY |
| 4 | PARTIAL_RECOVERABLE |
| 10 | LOCK_HELD |

---

**END OF RUNBOOK — NOT EXECUTED IN PHASE 3K.5**

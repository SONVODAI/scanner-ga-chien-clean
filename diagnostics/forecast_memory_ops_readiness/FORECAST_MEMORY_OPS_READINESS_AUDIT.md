# Forecast Memory Foundation — Final Operational Readiness Audit

**Date:** 2026-08-24  
**Scope:** Audit + deployment plan only. **No production mutation.**  
**Stack tip audited:** `0585dbcee` (`origin/cursor/p0-foreign-flow-vps-verification-aad2`)  
**Production VPS HEAD (observed):** `8514fd7b2` on `cursor/phase-3k5b-waiting-data-retry-aad2`  
**GitHub `main` (observed):** `19cc913a7`

**Final verdict:** `READY_AFTER_INTEGRATION_CLEANUP`

---

## 1. GIT_GRAPH

### Exact relationship (do not use PR numbers as merge order)

```
71a0bd7c0  (merge-base of main ↔ phase-3K / forecast stack)
│
├── origin/main (19cc913a7) ……………………… +189 commits
│     • Market First / learning journals dominant
│     • edge_research ≈ 32 files (NO opr_bridge production daily run)
│     • NO deploy/systemd/mrbot-daily-research.*
│     • NO modules/forecast_research/
│
└── Phase 3K production lineage ………………… +105 commits to prod tip
      │
      ├── 83b89f12a  (common parent of #85 tip vs prod tip)
      │     ├── #85  46d9ef266  Forecast Data Contract V1
      │     │     └── #87 3666c9128  Historical core + MDRR
      │     │           └── #88 3dbc2a7c4  P0 forward memory
      │     │                 └── #89 (+6) → 0585dbcee  universe foreign HSX/VCI
      │     │
      │     └── prod/3k5b  8514fd7b2  WAITING_FOR_DATA same-day retry
      │
      └── (PR #86 is NOT on this spine)
```

### PR classification

| PR | Branch | Declared base | Actual role | Required for memory? |
|----|--------|---------------|-------------|----------------------|
| **#85** | `cursor/forecast-data-contract-v1-aad2` | `main` (unsafe) | Stack root: Forecast T0 + maturity + Streamlit/MDT0 hook | YES (commit `46d9ef266`) |
| **#86** | `cursor/fc-history-forensic-audit-aad2` | `main` | **Sibling** diagnostics-only (`ca8807f8f`) | **NO** — superseded by #87 recovery docs; not an ancestor of #89 |
| **#87** | `cursor/historical-fc-recovery-mdrr-v1-aad2` | #85 | Historical Market Core + MDRR | YES (`3666c9128`) |
| **#88** | `cursor/p0-forward-market-memory-aad2` | #87 | P0 turnover/ADV/VNI tech (+ legacy SSI path later replaced) | YES (`3dbc2a7c4`) |
| **#89** | `cursor/p0-foreign-flow-vps-verification-aad2` | #88 | VPS verify + alt-source audit + **universe-142 foreign** | YES (6 commits ending `0585dbcee`) |

**Stacked:** `#85 → #87 → #88 → #89` (linear).  
**Sibling:** `#86` vs `#85` (both claimed `main`; only #86 actually sits on current `main`).  
**Duplication hazard:** `#85…#89` tips each contain ~105 phase-3K commits that are **not** the same SHAs as current `main`. Diff `main...#89` ≈ **1231 files / 1.5M+ insertions**. Merging stacked PRs into `main` individually or as a chain would race Phase 3K content, systemd units, and Edge OPR code that production already runs from a different lineage.

### Commits required for desired production memory state

Relative to **production HEAD** `8514fd7b2`, exactly these **9** commits (clean additive set; merge-tree shows no content conflicts with prod):

1. `46d9ef266` — Forecast Data Contract V1 + `market_t0_capture` hook  
2. `3666c9128` — Historical Market Core + MDRR V1  
3. `3dbc2a7c4` — P0 forward market memory  
4. `fd53312a1` — P0 foreign VPS verification package  
5. `dce6de346` — standalone SSI probe (diagnostic; optional for runtime)  
6. `87c40010d` — probe operator docs (diagnostic)  
7. `31ad219e0` — foreign alternative-source audit (diagnostic)  
8. `b26eae778` — EMS-142 universe foreign (HSX + VCI)  
9. `0585dbcee` — HSX PARTIAL history + VCI COMPLETE forward closeout  

**Also required on the deploy branch:** keep prod’s `8514fd7b2` WAITING_FOR_DATA retry (already on prod; **missing from #89 tip**).

### #86 verdict

**Diagnostics-only / not required / not superseded by code.** Safe to leave open or close without merging into production.

---

## 2. DESIRED_PRODUCTION_STATE

Production code+data must include **only** the approved memory foundation:

### Forecast research
- Forecast Data Contract V1  
- `forecast_t0_daily` (immutable first-write-wins)  
- `forecast_outcomes` (T3/T5/T10 trading-session maturity, append-only)  
- Streamlit-independent CLI: `python -m modules.forecast_research.daily_entrypoint`

### Historical memory
- `historical_market_core` + quality tiers + provenance  

### MDRR
- immutable `mdrr_daily` with completeness/honesty gates, FC trajectory, breadth, VNINDEX, provenance  

### P0
- `p0_market_daily` (`p0_market_memory_v2`)  
- universe turnover/volume, PIT-safe ADV 5/10/20  
- VNINDEX RSI/MACD/BB derived  
- universe-142 foreign buy/sell/net **VALUE** (VND)  
- HSX historical PARTIAL; VCI forward COMPLETE cascade  
- `forward_only_feature_registry.json`  
- **No** `fr_trade_heatmap` / SSI as production path (legacy provider may remain in tree for probes only; default collector is `UniverseForeignFlowCascade`)

### Must NOT enter via these PRs unintentionally
- P1 sector work, Forecast Brain, model training, new Edge Research science, Camera changes, new indicators/providers beyond approved P0 foreign cascade  

**Important topology fact:** real production is **not** on GitHub `main`. It is on **`cursor/phase-3k5b-waiting-data-retry-aad2` @ `8514fd7b2`**. Desired *runtime* state = that HEAD + the 9 forecast commits (+ automation fix below). Desired *GitHub main* convergence is a separate, larger integration problem and is **out of scope** for this memory deploy.

---

## 3. PRODUCTION_COMPATIBILITY

| Surface | Risk | Finding |
|---------|------|---------|
| Edge Research daily timer/service | Low if isolated | `mrbot-daily-research.{timer,service}` runs `production_daily_run_entrypoint` only. Forecast code does not import into OPR today. |
| Camera services | None observed | No Camera coupling in `modules/forecast_research/` (MDRR marks `camera_coupled: false`). |
| Streamlit / Market First | Low | Single fail-safe hook in `market_t0_capture._persist_canonical_daily_t0` after MDT0 append; exceptions swallowed. |
| Python / vnstock 4.0.5 | Compatible for approved path | Universe foreign uses HSX/VCI; does **not** require `fr_trade_heatmap`. SSI probe remains diagnostic. |
| Import paths | OK on prod tree | Package is `modules.forecast_research.*`; deploy must land under `/opt/mrbot-camera`. |
| Data dirs | Careful | Writes under `data/forecast_research/` only (plus status JSON). Must not clobber `data/earning_learning/`, Edge observations, Camera stores. |
| systemd assumptions | OK | `Type=oneshot`, `SuccessExitStatus=2 3 10` (WAITING / non-trading / lock) — **inactive (dead) after SUCCESS is expected**. |
| `fr_trade_heatmap` | Retired for P0 collect | Default provider = HSX → VCI → honest PARTIAL/NULL. |
| Git base mismatch | **HIGH** | Do not deploy `#89` tip by merging into `main`. Deploy from **prod HEAD + cherry-picks**. |

---

## 4. DATA_DEPLOYMENT_POLICY

| Artifact | Class | Deploy? | Notes |
|----------|-------|---------|-------|
| `modules/forecast_research/**` | code | YES | Required |
| `modules/market_t0_capture.py` hook | code | YES | Fail-safe observer only |
| `tests/test_forecast*`, `test_historical*`, `test_p0*` | tests | YES (for pre-deploy gate) | |
| `scripts/backfill_universe_foreign_hsx.py` | ops/recovery | OPTIONAL | Manual backfill only |
| `scripts/standalone_ssi_*`, `verify_p0_foreign_*` | diagnostic | NO need on hot path | Keep in repo; do not schedule |
| `diagnostics/**` | diagnostic | OPTIONAL | Docs/evidence only |
| `forecast_t0_daily.csv` | seed / agent backfill | **DO NOT overwrite prod** | Regenerate or first-write on empty dir |
| `forecast_outcomes.csv` | generated | **DO NOT overwrite prod** | Maturity is append-only |
| `historical_market_core.csv` | recovery artifact | **DO NOT overwrite newer prod** | Safe to regenerate via CLI if empty |
| `mdrr_daily.csv` | generated / backfill | **DO NOT overwrite prod** | First-write-wins |
| `p0_market_daily.csv` | generated / backfill | **DO NOT overwrite prod** | Enrichment only for null/same-day PARTIAL foreign |
| `feature_availability_matrix.json` | generated | regenerate OK | |
| `forward_only_feature_registry.json` | registry | deploy template OK if missing; never replace newer prod | Updated by P0 collect |
| `*_pipeline_status.json`, `historical_recovery_status.json` | status | regenerate OK | Not source of truth |

### Safe first-production-run behavior
1. Backup existing `data/earning_learning/` and any existing `data/forecast_research/` if present.  
2. If `data/forecast_research/` **absent**: create empty dir; let first unattended/CLI run write rows.  
3. If **present with newer dates than repo seeds**: keep production files; do **not** `git checkout -- data/forecast_research`.  
4. Prefer `git pull` with sparse checkout / path checkout that does not force-reset data CSVs; or use `git restore` only on code paths.  
5. Optional one-time backfill only after confirming prod CSVs are empty/absent.

---

## 5. AUTOMATION_PATH

### What exists today (actual code path)

```
Streamlit app.py
  └─ capture_market_t0_snapshot(...)
       └─ _persist_canonical_daily_t0  (only when ≥18:00 VN + eligible)
            ├─ append market_daily_t0.csv  (MDT0 first-write-wins)
            └─ maybe_freeze_after_market_daily(trade_date)   # fail-safe
                 ├─ freeze Forecast T0
                 ├─ mature_all_outcomes (T3/T5/T10)
                 ├─ freeze MDRR
                 ├─ persist historical_market_core row
                 └─ maybe_collect_p0_after_market_daily
                      └─ UniverseForeignFlowCascade (HSX→VCI→PARTIAL/NULL)
```

### Parallel production path (does NOT run Forecast Memory)

```
mrbot-daily-research.timer  (Mon–Fri 18:35 / 20:05 / 22:35 Asia/Ho_Chi_Minh)
  └─ mrbot-daily-research.service  (Type=oneshot)
       └─ production_daily_run_entrypoint --derive-vn-date --mode LIVE_FORWARD --use-lock
            └─ Edge Research OPR only
```

### Answers

| Question | Answer |
|----------|--------|
| What starts Forecast Memory today? | Streamlit/Market First MDT0 capture path only (+ manual CLI). |
| Streamlit / systemd / both? | **Streamlit-triggered** for the integrated hook. systemd runs Edge Research only. |
| If Streamlit never opened? | **Research memory does not run** → `AUTOMATION_GAP`. |
| Responsible timer? | None for Forecast Memory today. Edge timer: `mrbot-daily-research.timer`. |
| VN times (Edge)? | 18:35, 20:05, 22:35 Asia/Ho_Chi_Minh. |
| Upstream EOD not ready? | Edge: `WAITING_FOR_DATA` (exit 2, success for systemd) → later timer cycles retry (prod fix `8514fd7b2`). Forecast: returns WAITING / no freeze if no EMS+MDT0. |
| Same-day retry? | Edge: yes (prod). Forecast: yes **if** MDT0 capture or CLI re-invoked; freeze/MDRR/P0 idempotent; foreign may enrich null/same-day PARTIAL. |
| After WAITING_FOR_DATA? | Edge retries next OnCalendar. Forecast unchanged until invoked. |
| Weekends/holidays? | Timer Mon–Fri only; Edge disposition SKIPPED_NON_TRADING (exit 3). Forecast builders skip non-weekday / empty board. |
| Can one failed P0 provider block T0/MDRR? | **No** — each hook is try/except isolated; foreign failure → NULL/SOURCE_ERROR/PARTIAL, not crash. |
| oneshot inactive after SUCCESS? | **Expected.** |

### Immutability / first-deploy safety (proven by code)

| Asset | Guard |
|-------|-------|
| Forecast T0 | `persist_t0_record` → `ALREADY_FROZEN` |
| Outcomes | keyed `(trade_date, horizon)` → `ALREADY_PRESENT` |
| MDRR | `ALREADY_PRESENT` |
| P0 row | first-write-wins; foreign enrichment only if null or **same-calendar-day** PARTIAL→COMPLETE |
| MDT0 / EMS | not rewritten by Forecast modules |
| Edge / Camera | not touched by Forecast writers |
| NULL≠0 | `_finite_or_none`; incomplete universe cannot be COMPLETE |
| Historical PARTIAL | not re-hammered on later days |

**Automation design hazard:** `build_forecast_t0_record` will **persist PARTIAL** if EMS(142) exists but MDT0 is missing. The Streamlit hook avoids this by running *after* MDT0 write. Any systemd integration **must gate on MDT0 row present** (or refuse to persist until COMPLETE) to avoid irreversible PARTIAL freezes.

---

## 6. AUTOMATION_GAPS

```
AUTOMATION_GAP
```

1. **No unattended Forecast Memory invocation** when Streamlit is not opened after close.  
2. **Edge daily timer does not call** `maybe_freeze_after_market_daily` / `daily_entrypoint`.  
3. MDT0 itself remains Streamlit-produced today (pre-existing Market First fact); Forecast COMPLETE quality depends on MDT0 existence.

### Smallest safe production integration (do not add a second timer)

**Prefer option A:** inside existing `run_production_daily_research` / post-EOD-ready path on the **integration branch**:

1. After Edge EOD readiness for `target_trade_date` (or on SUCCESS / late retry when data ready).  
2. **If** `market_daily_t0` contains that trade_date: call `maybe_freeze_after_market_daily(trade_date)` in an isolated try/except.  
3. **If** MDT0 missing: skip Forecast freeze (log `WAITING_FOR_MDT0`); do not persist PARTIAL.  
4. Never let Forecast exceptions change Edge `run_disposition`.  
5. Do **not** create `mrbot-forecast-memory.timer`.

Manual CLI remains recovery-only:
` /opt/mrbot-camera-venv/bin/python -m modules.forecast_research.daily_entrypoint --all-research-memory --trade-date YYYY-MM-DD`

---

## 7. PRE_DEPLOY_TEST_GATE

Run on the **integration commit** with production venv semantics where possible:

```bash
cd /opt/mrbot-camera   # or CI checkout of integration branch
/opt/mrbot-camera-venv/bin/python -m pytest -q \
  tests/test_forecast_data_contract_v1.py \
  tests/test_historical_recovery_and_mdrr_v1.py \
  tests/test_p0_forward_market_memory.py \
  tests/test_p0_universe_foreign_flow.py \
  tests/test_p0_foreign_flow_vps_verification.py \
  tests/test_market_t0_capture.py \
  tests/test_edge_research_waiting_data_same_day_retry.py
```

Must cover:
- Forecast contract + maturity idempotency  
- Historical core + MDRR immutability  
- P0 + universe foreign COMPLETE/PARTIAL/NULL honesty  
- Leakage / forward-only registry expectations in those tests  
- Market T0 capture still succeeds if forecast hook throws  
- Waiting-data retry still intact (`8514fd7b2` behavior)

Smoke (non-destructive):

```bash
/opt/mrbot-camera-venv/bin/python -c "from modules.forecast_research.daily_entrypoint import maybe_freeze_after_market_daily; print('ok')"
/opt/mrbot-camera-venv/bin/python -c "from modules.forecast_research.p0_universe_foreign import UniverseForeignFlowCascade; print('ok')"
# idempotent re-freeze of an ALREADY present date only after backup:
# /opt/mrbot-camera-venv/bin/python -m modules.forecast_research.daily_entrypoint --trade-date <existing> --no-mature
```

---

## 8. RECOMMENDED_DEPLOYMENT_STRATEGY

**ONE safest strategy:** create a **clean production integration branch from current VPS HEAD**, cherry-pick the forecast-only commit set, add the minimal automation hook, deploy **that** ref to the VPS. Do **not** merge #85–#89 into GitHub `main` as stacked PRs.

```bash
# planning only — not executed by this audit
git fetch origin
git checkout -b cursor/forecast-memory-prod-integrate-aad2 8514fd7b2
git cherry-pick 46d9ef266 3666c9128 3dbc2a7c4 \
  fd53312a1 dce6de346 87c40010d 31ad219e0 b26eae778 0585dbcee
# then commit automation fix (orchestrator fail-safe + MDT0 gate)
```

### Rationale
- `#89` tip is **1 commit behind** prod (missing WAITING retry) and **9 commits ahead** (forecast only) → near-perfect prod delta.  
- `#89` vs `main` is a **lineage collision** (113 vs 189 divergent commits; 1.5M-line diff).  
- `#86` is irrelevant to runtime.  
- Automation gap must be closed on the same integration branch before calling the system unattended-complete.

**Do not:** rebase/squash the entire stack onto `main` as the production deploy vehicle.  
**Do not:** deploy `#89` tip without the WAITING_FOR_DATA commit unless that fix is already present on the VPS (it is at `8514fd7b2`).

---

## 9. VPS_DEPLOY_RUNBOOK

**Only after** integration branch exists, tests pass, and automation fix is present.  
**This audit does not execute these steps.**

### Before
```bash
cd /opt/mrbot-camera
git rev-parse HEAD | tee /tmp/mrbot-pre-forecast-memory.HEAD
git status -sb | tee /tmp/mrbot-pre-forecast-memory.status
git branch --show-current | tee /tmp/mrbot-pre-forecast-memory.branch
systemctl status mrbot-daily-research.timer --no-pager | tee /tmp/mrbot-pre-forecast-memory.timer
systemctl status mrbot-daily-research.service --no-pager | tee /tmp/mrbot-pre-forecast-memory.service
systemctl list-timers --all | grep -i mrbot | tee /tmp/mrbot-pre-forecast-memory.timers
df -h /opt /var | tee /tmp/mrbot-pre-forecast-memory.df
# backup research data (preserve; do not delete)
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /var/backups/mrbot-forecast-memory-$TS
cp -a data/earning_learning /var/backups/mrbot-forecast-memory-$TS/ 2>/dev/null || true
cp -a data/forecast_research /var/backups/mrbot-forecast-memory-$TS/ 2>/dev/null || true
cp -a data/edge_research /var/backups/mrbot-forecast-memory-$TS/ 2>/dev/null || true
```

### Deploy
```bash
cd /opt/mrbot-camera
git fetch origin
# EXACT ref: integration branch tip (NOT origin/main, NOT raw #89 tip unless it contains 8514fd7b2 + automation)
git checkout cursor/forecast-memory-prod-integrate-aad2
git pull origin cursor/forecast-memory-prod-integrate-aad2
# dependencies: NONE expected if vnstock 4.0.5 already present — do not upgrade packages
/opt/mrbot-camera-venv/bin/python -c "import vnstock; print(vnstock.__version__)"
```

**Do not** `git checkout -- data/forecast_research` or reset production CSVs.

### Validate
```bash
/opt/mrbot-camera-venv/bin/python -c "from modules.forecast_research import contract; print(contract.CONTRACT_VERSION, contract.P0_SCHEMA_VERSION)"
# run PRE_DEPLOY_TEST_GATE pytest commands
# idempotent dry invoke for a date that already has MDT0 (expect ALREADY_* or WRITTEN once):
/opt/mrbot-camera-venv/bin/python -m modules.forecast_research.daily_entrypoint --all-research-memory --trade-date $(date +%F)
ls -la data/forecast_research/
# confirm trading gates / Edge entrypoint unchanged:
/opt/mrbot-camera-venv/bin/python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint --scheduling-contract | head
```

### Automation
```bash
systemctl is-enabled mrbot-daily-research.timer
systemctl status mrbot-daily-research.timer --no-pager
systemctl list-timers mrbot-daily-research.timer --no-pager
# confirm no new competing forecast timer exists
systemctl list-timers --all | grep -i forecast || echo "OK: no forecast timer"
```

### After validate
Operator opens Streamlit at least once **or** relies on new orchestrator hook once MDT0 exists — per automation fix design.

---

## 10. ROLLBACK_RUNBOOK

```bash
cd /opt/mrbot-camera
PRE=$(cat /tmp/mrbot-pre-forecast-memory.HEAD)
git checkout -f "$PRE"   # or: git switch --detach "$PRE" / previous branch name
# Preserve newly generated forecast_research data unless corrupted:
#   do NOT delete data/forecast_research after rollback unless instructed
systemctl daemon-reload   # only if unit files changed; usually no-op for code-only rollback
systemctl status mrbot-daily-research.timer --no-pager
/opt/mrbot-camera-venv/bin/python -c "import modules.market_t0_capture; print('rolled back')"
```

Rollback restores pre-deploy **code**. Leave `data/forecast_research/` in place when possible (append-only / first-write-wins history is valuable). Restore from `/var/backups/mrbot-forecast-memory-*` only if a bad write occurred to MDT0/EMS/Edge stores (should not happen if isolation held).

---

## 11. POST_DEPLOY_ACCEPTANCE

1. `git rev-parse HEAD` equals integration tip (contains `8514fd7b2` ancestry + forecast commits + automation fix).  
2. Market First / Streamlit still loads; MDT0 append still first-write-wins.  
3. `mrbot-daily-research.timer` still scheduled (18:35/20:05/22:35 VN).  
4. Camera services unchanged / still active as before.  
5. Forecast T0 freeze works (hook or CLI) when MDT0+EMS present.  
6. MDRR freeze works; rerun → `ALREADY_PRESENT`.  
7. P0 collect works; foreign cascade HSX→VCI.  
8. Universe foreign can reach COMPLETE when VCI supplies 142/142 (as on 2026-08-24 lab: net 208,515,123,800 VND).  
9. T3/T5/T10 maturity appends without mutating T0.  
10. Second run: no duplicate T0/MDRR/P0/outcome keys.  
11. Unattended path: Forecast Memory invoked from daily orchestrator when MDT0 exists (not Streamlit-only).  
12. P0/foreign failure does not fail Edge disposition; Edge failure does not wipe Forecast files.

---

## 12. FIRST_UNATTENDED_RUN_CHECK

After the first post-close timer cycle (next VN weekday morning):

```bash
# timer evidence
journalctl -u mrbot-daily-research.service --since "yesterday" --no-pager | tail -100
systemctl status mrbot-daily-research.service --no-pager

# artifacts
cd /opt/mrbot-camera
DATE=$(date -d "yesterday" +%F)  # or explicit prior session
grep -n "$DATE" data/forecast_research/forecast_t0_daily.csv
grep -n "$DATE" data/forecast_research/mdrr_daily.csv
grep -n "$DATE" data/forecast_research/p0_market_daily.csv
# foreign honesty
python3 - <<'PY'
import pandas as pd
d="YYYY-MM-DD"  # set
p=pd.read_csv("data/forecast_research/p0_market_daily.csv")
r=p[p.trade_date.astype(str).str[:10]==d].iloc[-1]
print({k:r.get(k) for k in [
 "universe_foreign_completeness","universe_foreign_source","universe_foreign_observed_count",
 "universe_foreign_expected_count","universe_foreign_net_value","universe_foreign_units"]})
PY
# duplicates
python3 - <<'PY'
import pandas as pd
for f in ["forecast_t0_daily.csv","mdrr_daily.csv","p0_market_daily.csv"]:
  df=pd.read_csv(f"data/forecast_research/{f}")
  print(f, "dup_dates", df.trade_date.astype(str).str[:10].duplicated().sum())
PY
# outcomes if eligible
wc -l data/forecast_research/forecast_outcomes.csv
# status files (errors must be visible, not silent success)
tail -n 40 data/forecast_research/p0_market_pipeline_status.json
tail -n 40 data/forecast_research/forecast_pipeline_status.json
```

Prove: yesterday T0 preserved; MDRR/P0 present; foreign collected or honestly PARTIAL/NULL; timer ran; no duplicate keys; no hidden SOURCE_ERROR.

---

## FINAL VERDICT

`READY_AFTER_INTEGRATION_CLEANUP`

**Blockers before safe production deploy**
1. Integrate from **prod HEAD `8514fd7b2`**, not from merging #85–#89 into `main`.  
2. Close `AUTOMATION_GAP` with a fail-safe, MDT0-gated step inside the existing daily research orchestration (no second timer).  
3. Keep data-deploy policy: never overwrite newer production research CSVs with repo seeds.

**STOP** — no merge, no VPS pull, no systemd change, no package install, no data mutation in this task.

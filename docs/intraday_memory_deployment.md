# Mr.BOT Intraday Memory — VPS Deployment (V1A)

This document describes the **smallest safe unattended deployment** for the
dedicated collector VPS. It does **not** change collector semantics validated
on the live VPS (`da52406bd` and later).

## What V1A Actually Does

V1A stores **completed 5-minute OHLCV bars per trading session**. The deployment
layer runs **once-per-session collection** (with idempotent retries) and a
**next-morning reconciliation** — **not** a whole-universe poll every 5 minutes.

### Runtime math (guest tier, 142 symbols)

| Metric | Value |
|---|---|
| Throttle floor | 142 ÷ 18 rpm ≈ **7.9 min** (requests only) |
| Live observed (5 symbols in 15.36 s) | ≈ **3.07 s/symbol** |
| Estimated full universe | 142 × 3.07 s ≈ **7.3–8.5 min** |
| Minimum safe timer spacing | **≥ 10 min** (1.25× safety factor) |

**Conclusion:** A true every-5-minute whole-universe camera is **not achievable**
at guest 18 rpm without violating throttle constraints. V1A honestly targets
**one full pass per session** after the cash close, with spaced retries for
KBS publication lag.

## Architecture

```
systemd timer (Mon–Fri, Asia/Ho_Chi_Minh)
        ↓
systemd oneshot service
        ↓
modules.intraday_memory.runner  (flock + weekend guard)
        ↓
modules.intraday_memory.cli/collector  (existing logic)
        ↓
manifest JSON + Parquet canonical store
```

Observability remains in **manifest JSON** under `{MRBOT_INTRADAY_DATA_ROOT}/manifests/`.
`journald` captures process stdout/stderr only.

## Schedule (Asia/Ho_Chi_Minh)

### Collect timer (`mrbot-intraday-collect.timer`)

| Local time | Purpose |
|---|---|
| **18:30** Mon–Fri | Primary post-close collect (session = today) |
| **20:00** Mon–Fri | Publication-lag retry (idempotent) |
| **22:30** Mon–Fri | Publication-lag retry (idempotent) |
| **06:00** Mon–Fri | Pre-open catch-up for prior session |

Spacing between fires: **90–780 minutes** — well above ~8 min runtime.

### Reconcile timer (`mrbot-intraday-reconcile.timer`)

| Local time | Purpose |
|---|---|
| **07:30** Mon–Fri | Reconcile most recently completed session |

## Weekend / holiday policy

| Case | Behavior |
|---|---|
| **Saturday / Sunday** | Runner skips; writes manifest `final_status=NO_TRADING_DAY` |
| **Exchange holidays** | No holiday calendar in V1A — collect runs; empty provider data surfaces as `NOT_READY` in manifest |
| **Missed timer (reboot)** | `Persistent=true` — systemd fires missed Mon–Fri timers once after boot |

## Non-overlap mechanism

1. **`fcntl.flock`** on `{MRBOT_INTRADAY_DATA_ROOT}/.collector.lock` for the entire run
2. If lock held → exit **75** (configured as `SuccessExitStatus` — observable, no alert storm)
3. Timer spacing prevents routine overlap (~8 min run vs ≥90 min between fires)

## Reboot / recovery

- **Idempotent storage** — reruns produce `bars_new=0` when data already canonical
- **Persistent timers** — catch up one missed invocation after downtime
- **No auto git pull** — operators update `/opt/mrbot-camera` deliberately
- **No Streamlit** — collector venv and service are isolated from production UI

## VPS paths (live validated)

| Path | Purpose |
|---|---|
| `/opt/mrbot-camera` | Git checkout (repo) |
| `/opt/mrbot-camera-venv` | Collector Python venv (`vnstock` 4.0.5) |
| `/var/lib/mrbot/intraday_memory` | Parquet + manifests (`MRBOT_INTRADAY_DATA_ROOT`) |
| `/etc/mrbot/intraday.env` | Environment (mode **600**, no secrets in git) |

## Installation

Run on the VPS as **root** after pulling the repo:

```bash
cd /opt/mrbot-camera
git pull origin main
sudo bash deploy/systemd/install.sh
sudo editor /etc/mrbot/intraday.env   # verify paths; add VNSTOCK_API_KEY if Community
sudo mkdir -p /var/lib/mrbot/intraday_memory
sudo chown -R "$(whoami):$(whoami)" /var/lib/mrbot/intraday_memory  # or dedicated user
```

## Enable / start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mrbot-intraday-collect.timer
sudo systemctl enable --now mrbot-intraday-reconcile.timer
```

## Status

```bash
systemctl status mrbot-intraday-collect.timer
systemctl status mrbot-intraday-reconcile.timer
systemctl list-timers mrbot-intraday-*
```

## Logs

```bash
journalctl -u mrbot-intraday-collect.service -n 100 --no-pager
journalctl -u mrbot-intraday-reconcile.service -n 100 --no-pager
journalctl -u mrbot-intraday-collect.service -f
```

Manifest files:

```bash
ls -lt /var/lib/mrbot/intraday_memory/manifests/ | head
```

## Manual run (same as systemd)

```bash
cd /opt/mrbot-camera
set -a && source /etc/mrbot/intraday.env && set +a
/opt/mrbot-camera-venv/bin/python -m modules.intraday_memory.runner collect
/opt/mrbot-camera-venv/bin/python -m modules.intraday_memory.runner reconcile
```

Single-symbol smoke test (existing CLI):

```bash
/opt/mrbot-camera-venv/bin/python -m modules.intraday_memory.cli collect \
  --session 2026-08-14 --symbols VCB
```

## Stop / disable

```bash
sudo systemctl disable --now mrbot-intraday-collect.timer
sudo systemctl disable --now mrbot-intraday-reconcile.timer
```

## Recovery procedure

1. Check last manifest: `final_status`, `duration_sec`, `per_symbol_summary`
2. If `NOT_READY` — wait for next scheduled retry (publication lag)
3. If `PARTIAL` / `FAILED` — inspect `per_symbol_summary` and journald
4. Manual idempotent rerun is safe: `runner collect` for the session date
5. After VPS reboot — verify timers: `systemctl list-timers mrbot-intraday-*`
6. Overlap skip (exit 75) — prior run still active; check lock file and process list

## Remaining limitations

- No authoritative VN holiday calendar — holidays may produce `NOT_READY` until manual review
- Guest tier (~8 min) — Community tier (55 rpm) reduces runtime but is optional
- Not a realtime intraday feed — post-close session archive only
- Operator must `git pull` to deploy code updates

## Repository artifacts

```
deploy/systemd/
  mrbot-intraday-collect.service
  mrbot-intraday-collect.timer
  mrbot-intraday-reconcile.service
  mrbot-intraday-reconcile.timer
  mrbot-intraday.env.example
  install.sh
modules/intraday_memory/
  runner.py      # unattended entrypoint
  scheduler.py   # session-date + runtime math
```

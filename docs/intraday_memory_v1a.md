# Mr.BOT Intraday Memory V1A

## Purpose

V1A establishes the **5-minute camera** — an independent, immutable OHLCV memory
foundation for Mr.BOT research. This layer collects, validates, and stores raw
5-minute bars. It does **not** interpret market behavior.

**V1A is DATA FOUNDATION ONLY.**

No absorption, distribution, smart money, Price–Volume scoring, or BUY/SELL logic
is performed in this layer.

## Architecture

```
scheduler / CLI
      ↓
collector core (IntradayCollector)
      ↓
provider adapter (vnstock 4.x / KBS)
      ↓
validation / QC
      ↓
immutable Parquet memory
      ↓
reconciliation
```

The collector is **independent of Streamlit**. It can run from cron, GitHub Actions,
or a VPS while `app.py` is closed.

## Data

| Field | Type | Notes |
|---|---|---|
| symbol | string | Uppercase ticker |
| timestamp | datetime | Timezone-aware, `Asia/Ho_Chi_Minh` |
| session_date | date | VN calendar date of bar |
| open/high/low/close | **integer VND** | Canonical unit (e.g. 22200) |
| volume | integer | Shares/contracts |
| source | string | `vnstock4_kbs` |
| collected_at | datetime | When collector received the bar |
| quality_flag | string | `ok`, `atypical_session`, `rejected` |

**Primary identity:** `(symbol, timestamp)`

## Provider

- **Package:** vnstock 4.x (NOT Legacy 0.2.9.2)
- **Source:** `KBS` only (do NOT use VCI)
- **Auth:** `VNSTOCK_API_KEY` environment variable (optional; Guest tier supported)
- **Price normalization:** KBS returns OHLC in thousands → multiply ×1000 to integer VND

## Timezone Policy

All timestamps are stored timezone-aware in `Asia/Ho_Chi_Minh`. Naive provider
timestamps are interpreted as VN local time. `session_date` is derived from the
VN-local calendar date of each bar.

## Storage

Parquet files under configurable root (`MRBOT_INTRADAY_DATA_ROOT`, default `intraday_memory/`):

```
intraday_memory/
  canonical/
    year=2026/month=08/session_date=2026-08-14/bars.parquet
  manifests/
    {run_id}.json
```

Writes are atomic (temp file + `os.replace`). Idempotent on `(symbol, timestamp)`.

## Collection Philosophy

1. **Post-close collection** — fetch completed session after market close
2. **Next-morning reconciliation** — refetch, fill gaps, detect provider corrections
3. **Bootstrap** — one-time historical backfill (~90 days) when authorized

## Reconciliation Policy (V1A)

- **New bars:** inserted
- **Identical existing bars:** kept unchanged
- **Changed bars:** new provider value quarantined; canonical NOT silently overwritten

## Configuration

| Variable | Purpose |
|---|---|
| `MRBOT_INTRADAY_DATA_ROOT` | Storage root path |
| `VNSTOCK_API_KEY` | Community tier API key |
| `MRBOT_INTRADAY_RPM` | Override requests/minute throttle |
| `MRBOT_APP_PY_PATH` | Override path to app.py for universe parsing |

## Dependency Isolation

Production `requirements.txt` keeps `vnstock==0.2.9.2` for `app.py`.
Collector uses `requirements-collector.txt` (`vnstock>=4.0.5`, `pyarrow`).

Install collector deps separately:
```bash
pip install -r requirements-collector.txt
```

## CLI

```bash
# Print production universe (142 symbols from app.py)
python -m modules.intraday_memory.cli universe

# Collect one session
python -m modules.intraday_memory.cli collect --session 2026-08-13

# Reconcile
python -m modules.intraday_memory.cli reconcile --session 2026-08-13

# Controlled bootstrap
python -m modules.intraday_memory.cli bootstrap --start 2026-08-10 --end 2026-08-13 --symbols HPG,VNM
```

## What V1A Does NOT Include

- Absorption / Distribution scores
- Smart money logic
- BUY/SELL / AI / Elite / Learning changes
- Streamlit UI panels
- Scheduler deployment (cron, GitHub Actions, VPS) — separate step

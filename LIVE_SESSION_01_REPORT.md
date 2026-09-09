# LIVE SESSION 01

Status: **NOT_STARTED**

Read-only validation of BOT Candidate → Dynamic Watchlist → live 5m Camera → P×V → UI.
STRENGTHEN/WEAKEN is **not** required. NEUTRAL-only and “No active BOT Candidate.” are valid.

## Verdict

| Key | Value |
|---|---|
| **A. CANDIDATE_LIVE_HANDOFF_WORKED** | **NO** |
| **B. CAMERA_5M_LIVE_WORKED** | **NO** |
| **C. PXV_LIVE_INTERPRETATION_WORKED** | **NO** |
| **D. UI_LIVE_REFRESH_WORKED** | **NO** |
| **E. CHRONOLOGY_CLEAN** | **NO** |
| **F. PRODUCTION_UNCHANGED** | **YES** |

Blocker: LIVE SESSION 01 was not started. Run the operator start command during a VN cash session, then re-run this validator. Do not start it from CI/agent automatically.

## Counts

- Candidates observed: **0**
- Legal completed bars: **0**
- Illegal evidence rows: **0**
- RAW: `{}`
- PUBLISHED: `{}`
- Transitions (not every 5m print): `{}`

## Latency

- After bar close median/max (s): None / None (n=0)
- After bar open median/max (s): None / None

## Failures / stale

- Provider/data-quality failures: `[]`
- Stale periods (>10 min between observed_at): `[]`
- Runner stale now: True
- alert_eligible all false: True

## Observation checklist (record during the session; do not change logic)

- Candidate first-seen
- eligible_from
- first legal completed 5m bar
- observed_at
- provider / observation latency
- RAW transitions
- PUBLISHED transitions
- stale / provider failures
- chronology_legal
- Candidate remains visible during NEUTRAL

## Operator commands

See the copy/paste block in this file under **Operator commands (copy/paste)**.

## Preflight

- repo: `/workspace`
- python: `/usr/bin/python3`
- vnstock: `{'check': 'vnstock_4x', 'ok': False, 'detail': "ModuleNotFoundError: No module named 'vnstock'"}`
- throttle: `{'check': 'throttle_18_rpm', 'ok': True, 'detail': 'KBSProvider default 18 rpm; min_interval=3.333s; source_has_default_18=True'}`
- watchlist: `/workspace/data/live_candidate/dynamic_watchlist.json`
- shadow: `/workspace/data/intraday_pxv_live_shadow`
- camera archive: `/workspace/intraday_memory`
- preflight all_ok: False
- preflight blocker: vnstock 4.x is not importable in this Python. Create isolated .venv-collector and pip install -r requirements-collector.txt. Do not install vnstock>=4 into the Streamlit/production env (app uses vnstock==0.2.9.2).

## Operator commands (copy/paste)

Do **not** run start from CI or this agent. Human operator only, during 09:15–14:45 Asia/Ho_Chi_Minh.

```bash
# 0) Repo root — this checkout is /workspace; change if your clone differs.
export MRBOT_REPO="/workspace"
cd "$MRBOT_REPO"
export MRBOT_LIVE_CANDIDATE_OUT="$MRBOT_REPO/data/live_candidate"
export MRBOT_LIVE_CAMERA_SHADOW_OUT="$MRBOT_REPO/data/intraday_pxv_live_shadow"
mkdir -p "$MRBOT_LIVE_CANDIDATE_OUT" "$MRBOT_LIVE_CAMERA_SHADOW_OUT"

# 1) Isolated collector venv (vnstock 4.x). NEVER use this venv for streamlit app.py
#    Production app.py requires vnstock==0.2.9.2 from requirements.txt.
python3 -m venv "$MRBOT_REPO/.venv-collector"
"$MRBOT_REPO/.venv-collector/bin/python" -m pip install -U pip
"$MRBOT_REPO/.venv-collector/bin/python" -m pip install -r "$MRBOT_REPO/requirements-collector.txt" pandas

# A) Start live-shadow runner (one sweep per ~60s; 18 rpm inside each sweep)
rm -f /tmp/mrbot_live_session_01.pid
nohup bash -c 'while true; do
  "$MRBOT_REPO/.venv-collector/bin/python" "$MRBOT_REPO/scripts/run_live_camera_shadow.py" --live \
    --watchlist "$MRBOT_LIVE_CANDIDATE_OUT/dynamic_watchlist.json" \
    --out "$MRBOT_LIVE_CAMERA_SHADOW_OUT"
  sleep 60
done' > "$MRBOT_LIVE_CAMERA_SHADOW_OUT/runner.log" 2>&1 & echo $! > /tmp/mrbot_live_session_01.pid
echo "PID=$(cat /tmp/mrbot_live_session_01.pid)"

# B) Existing app — different terminal, production Python (NOT .venv-collector)
cd "$MRBOT_REPO"
export MRBOT_LIVE_CANDIDATE_OUT="$MRBOT_REPO/data/live_candidate"
export MRBOT_LIVE_CAMERA_SHADOW_OUT="$MRBOT_REPO/data/intraday_pxv_live_shadow"
python3 -m streamlit run "$MRBOT_REPO/app.py"

# C) Runner health
"$MRBOT_REPO/.venv-collector/bin/python" "$MRBOT_REPO/scripts/preflight_live_session_01.py" --health
python3 -c "import json; p='$MRBOT_LIVE_CAMERA_SHADOW_OUT/live_shadow_status.json'; print(open(p).read())"

# D) Stop runner safely (does not touch Camera archive)
kill "$(cat /tmp/mrbot_live_session_01.pid)" && rm -f /tmp/mrbot_live_session_01.pid

# After the session: validator (read-only)
python3 "$MRBOT_REPO/scripts/validate_live_session_01.py"
```

Dry-run (no KBS): `python3 "$MRBOT_REPO/scripts/run_live_camera_shadow.py"`

## Safety

- No threshold / debounce / Candidate / Camera archive changes
- No Telegram, alerts, BUY/SELL, or production deploy
- UI is read-only


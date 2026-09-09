#!/usr/bin/env bash
# LIVE SESSION 01 operator helper. Does not start unless you pass "start".
# Usage:
#   export MRBOT_REPO=/workspace   # or your clone path
#   bash scripts/live_session_01_operator.sh preflight|start|health|stop|validate
set -euo pipefail

MRBOT_REPO="${MRBOT_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
export MRBOT_REPO
export MRBOT_LIVE_CANDIDATE_OUT="${MRBOT_LIVE_CANDIDATE_OUT:-$MRBOT_REPO/data/live_candidate}"
export MRBOT_LIVE_CAMERA_SHADOW_OUT="${MRBOT_LIVE_CAMERA_SHADOW_OUT:-$MRBOT_REPO/data/intraday_pxv_live_shadow}"
PIDFILE="${PIDFILE:-/tmp/mrbot_live_session_01.pid}"
PY_COLLECTOR="${MRBOT_REPO}/.venv-collector/bin/python"
CMD="${1:-}"

mkdir -p "$MRBOT_LIVE_CANDIDATE_OUT" "$MRBOT_LIVE_CAMERA_SHADOW_OUT"

case "$CMD" in
  preflight)
    python3 "$MRBOT_REPO/scripts/preflight_live_session_01.py"
    ;;
  start)
    if [[ ! -x "$PY_COLLECTOR" ]]; then
      echo "Missing $PY_COLLECTOR" >&2
      echo "Create it first (isolated vnstock 4.x; do not use for streamlit):" >&2
      echo "  python3 -m venv \"$MRBOT_REPO/.venv-collector\"" >&2
      echo "  \"$PY_COLLECTOR\" -m pip install -U pip" >&2
      echo "  \"$PY_COLLECTOR\" -m pip install -r \"$MRBOT_REPO/requirements-collector.txt\" pandas" >&2
      exit 1
    fi
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "Already running PID=$(cat "$PIDFILE")" >&2
      exit 1
    fi
    nohup bash -c "while true; do
      \"$PY_COLLECTOR\" \"$MRBOT_REPO/scripts/run_live_camera_shadow.py\" --live \\
        --watchlist \"$MRBOT_LIVE_CANDIDATE_OUT/dynamic_watchlist.json\" \\
        --out \"$MRBOT_LIVE_CAMERA_SHADOW_OUT\"
      sleep 60
    done" > "$MRBOT_LIVE_CAMERA_SHADOW_OUT/runner.log" 2>&1 &
    echo $! > "$PIDFILE"
    echo "started PID=$(cat "$PIDFILE") log=$MRBOT_LIVE_CAMERA_SHADOW_OUT/runner.log"
    ;;
  health)
    python3 "$MRBOT_REPO/scripts/preflight_live_session_01.py" --health
    if [[ -f "$MRBOT_LIVE_CAMERA_SHADOW_OUT/live_shadow_status.json" ]]; then
      echo "--- live_shadow_status.json ---"
      cat "$MRBOT_LIVE_CAMERA_SHADOW_OUT/live_shadow_status.json"
    fi
    if [[ -f "$PIDFILE" ]]; then
      echo "PIDFILE=$PIDFILE PID=$(cat "$PIDFILE") alive=$(kill -0 "$(cat "$PIDFILE")" 2>/dev/null && echo yes || echo no)"
    else
      echo "PIDFILE missing (runner not started via this script)"
    fi
    ;;
  stop)
    if [[ -f "$PIDFILE" ]]; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "stopped (Camera archive untouched)"
    else
      echo "not running"
    fi
    ;;
  validate)
    python3 "$MRBOT_REPO/scripts/validate_live_session_01.py"
    ;;
  *)
    echo "usage: $0 preflight|start|health|stop|validate" >&2
    exit 2
    ;;
esac

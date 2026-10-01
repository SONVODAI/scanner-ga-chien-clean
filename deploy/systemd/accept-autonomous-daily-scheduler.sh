#!/usr/bin/env bash
# Fail-closed autonomous daily scheduler acceptance.
# Verifies FINAL_PIN, genesis, unit ExecStart, enables existing timer, shows next triggers.
# Makes NO research run and NO historical recovery.
set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
cd "$REPO"

EXPECT_PIN="${EXPECT_PIN:-12e76a659eaf0b1ae15bfdd6baffdcce24072b05}"
# Optional newer installer tip (must be descendant of EXPECT_PIN). Empty = stay on EXPECT_PIN.
SCHEDULER_FIX_PIN="${SCHEDULER_FIX_PIN:-}"

PY="${MRBOT_PYTHON:-/opt/mrbot-research-venv/bin/python}"
SERVICE_UNIT=mrbot-daily-research.service
TIMER_UNIT=mrbot-daily-research.timer
REQUIRED_EXEC="/opt/mrbot-research-venv/bin/python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint --derive-vn-date --mode LIVE_FORWARD --use-lock"

abort() {
  echo "ABORT: $*"
  echo "AUTONOMOUS_SCHEDULER_ACCEPTANCE=FAIL"
  echo "NEXT_REAL_SESSION_READY=NO"
  exit 1
}

command -v systemctl >/dev/null 2>&1 || abort "systemctl unavailable"
command -v git >/dev/null 2>&1 || abort "git unavailable"
[[ -x "$PY" ]] || abort "python missing: $PY"

HEAD="$(git rev-parse HEAD)"
if [[ -n "$SCHEDULER_FIX_PIN" ]]; then
  git fetch origin --quiet || true
  git merge-base --is-ancestor "$EXPECT_PIN" "$SCHEDULER_FIX_PIN" \
    || abort "SCHEDULER_FIX_PIN is not a descendant of EXPECT_PIN"
  if [[ "$HEAD" != "$SCHEDULER_FIX_PIN" ]]; then
    # Preserve runtime dirt: detach only; never reset --hard / clean / main.
    git checkout --detach "$SCHEDULER_FIX_PIN" \
      || abort "failed checkout SCHEDULER_FIX_PIN=$SCHEDULER_FIX_PIN"
  fi
  HEAD="$(git rev-parse HEAD)"
  [[ "$HEAD" == "$SCHEDULER_FIX_PIN" ]] || abort "HEAD != SCHEDULER_FIX_PIN after checkout"
else
  [[ "$HEAD" == "$EXPECT_PIN" ]] || abort "LIVE HEAD ($HEAD) != EXPECT_PIN ($EXPECT_PIN)"
fi
echo "PIN_OK=$HEAD"

GENESIS="$REPO/data/edge_research/production_observations/live_forward_genesis.json"
[[ -f "$GENESIS" ]] || abort "live_forward_genesis missing at $GENESIS"
echo "GENESIS_OK=$GENESIS"

# Install units + daemon-reload + enable because genesis exists (no research run).
sudo bash "$REPO/deploy/systemd/install-daily-research.sh" \
  --repo-root "$REPO" \
  --enable-when-genesis \
  --require-active \
  || abort "install-daily-research.sh --enable-when-genesis --require-active failed"

# ExecStart contract from installed unit (not merely repo file).
EXEC_LINE="$(systemctl show -p ExecStart --value "$SERVICE_UNIT" 2>/dev/null || true)"
echo "$EXEC_LINE" | grep -F "$REQUIRED_EXEC" >/dev/null \
  || abort "ExecStart mismatch. got=[$EXEC_LINE] need=[$REQUIRED_EXEC]"

echo "$EXEC_LINE" | grep -F "/opt/mrbot-research-venv/bin/python" >/dev/null \
  || abort "ExecStart must use /opt/mrbot-research-venv/bin/python"
echo "$EXEC_LINE" | grep -F "LIVE_FORWARD" >/dev/null \
  || abort "ExecStart must use --mode LIVE_FORWARD"
echo "$EXEC_LINE" | grep -Fi streamlit >/dev/null && abort "Streamlit must not appear in ExecStart" || true
echo "EXECSTART_OK"

systemctl is-enabled --quiet "$TIMER_UNIT" || abort "timer not enabled"
systemctl is-active --quiet "$TIMER_UNIT" || abort "timer not active"
echo "TIMER_ENABLED_ACTIVE_OK"

echo "=== next scheduled triggers ==="
systemctl list-timers --all "$TIMER_UNIT" || abort "list-timers failed"
systemctl show -p NextElapseUSecRealtime -p LastTriggerUSec -p Triggers "$TIMER_UNIT" || true

# Static import smoke only — no pipeline execution.
"$PY" -c "from modules.edge_research.opr_bridge.production_daily_run_entrypoint import main; from modules.production_daily_receipt import write_receipt_from_run; print('IMPORT_OK')" \
  || abort "import smoke failed"

echo "AUTONOMOUS_SCHEDULER_ACCEPTANCE=PASS"
echo "NEXT_REAL_SESSION_READY=YES"

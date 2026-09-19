#!/usr/bin/env bash
# Update /opt/mrbot-live-shadow for SHADOW-ONLY V2 observe from collected parquet.
#
# Real VPS topology (do not invent mrbot-live-camera-shadow.service):
#   mrbot-intraday-collect.timer  → parquet in /var/lib/mrbot/intraday_memory
#   mrbot-v2-shadow-observe.timer → read parquet + Gate B sidecar → v2_action_state.json
#   mrbot-edge-artifacts.service  → GET /current/live_shadow/v2_action_state.json
#
# Does NOT checkout/reset /opt/mrbot-camera.
# Does NOT start Brain A. Does NOT poll KBS. Does NOT enable production BUY.
# Does NOT reboot the VPS.
# Does NOT modify collect/reconcile/rotation units.
#
# Usage:
#   $0 plan <rev>
#   INSTALL_CONFIRM=YES $0 apply <rev>
#   INSTALL_CONFIRM=YES RESTART_CONFIRM=YES $0 apply <rev>
#   ARTIFACT_RESTART=YES when the GET overlay exists but the service was not bounced.
set -euo pipefail

MODE="${1:-plan}"
REV="${2:-${UPDATE_REV:-}}"
CAMERA="/opt/mrbot-camera"
DEST="/opt/mrbot-live-shadow"
VENV="/opt/mrbot-camera-venv"
OBSERVE_SERVICE="mrbot-v2-shadow-observe.service"
OBSERVE_TIMER="mrbot-v2-shadow-observe.timer"
PHANTOM_SERVICE="mrbot-live-camera-shadow.service"
ARTIFACT_SERVICE="mrbot-edge-artifacts.service"
SERVER_PY="${CAMERA}/modules/edge_research/artifact_server.py"
STORE="/var/lib/mrbot/live_pxv_shadow"
CAMERA_STORE="/var/lib/mrbot/intraday_memory"
UNIT_DIR="/etc/systemd/system"
REPO_URL="https://github.com/SONVODAI/scanner-ga-chien-clean.git"
ISO="/tmp/mrbot-live-shadow-src-v2-${REV:0:12}"

print_plan() {
  cat <<EOF
=== VPS V2 SHADOW OBSERVE UPDATE (not executed unless MODE=apply) ===
REV=${REV:-MISSING}
CAMERA_TREE=$CAMERA  (DO NOT git checkout / reset / merge)
INSTALL_DEST=$DEST
CAMERA_STORE=$CAMERA_STORE  (READ ONLY)
SHADOW_STORE=$STORE
OBSERVE=$OBSERVE_SERVICE / $OBSERVE_TIMER
ARTIFACT_SERVICE=$ARTIFACT_SERVICE
V2_SIDECAR=GitHub Contents research/live_candidate_v2_camera_sidecar/camera_sidecar.json
FORBIDDEN:
  - $PHANTOM_SERVICE (never existed; do not create a second KBS collector)
  - Brain A / Gate A on VPS
  - production BUY / Telegram / NAV / orders
  - treating Elite watchlist as V2 nominations
  - VPS reboot
  - changes to mrbot-intraday-collect/reconcile or mrbot-rotation-watch
STEPS:
  1. Clone $REV and rsync the pinned consumer allowlist into $DEST
  2. Ensure $STORE exists; never write $CAMERA_STORE
  3. PYTHONPATH=$DEST import observe_from_collected_session
  4. Overlay artifact GET path if missing; restart $ARTIFACT_SERVICE when required
  5. Install $OBSERVE_SERVICE / $OBSERVE_TIMER from this rev
  6. Remove leftover $PHANTOM_SERVICE drop-in if the unit is absent
EOF
}

if [[ -z "$REV" ]]; then
  echo "REFUSE: need UPDATE_REV or: $0 plan <rev>" >&2
  exit 2
fi

if [[ "$(pwd)" == "$CAMERA" || "$(pwd)" == "$CAMERA"/* ]]; then
  echo "REFUSE: do not run this from $CAMERA" >&2
  exit 2
fi

if [[ "$MODE" != "apply" ]]; then
  print_plan
  echo "MODE=plan. Re-run with: INSTALL_CONFIRM=YES RESTART_CONFIRM=YES $0 apply $REV"
  exit 0
fi

if [[ "${INSTALL_CONFIRM:-}" != "YES" ]]; then
  echo "REFUSE: apply requires INSTALL_CONFIRM=YES" >&2
  exit 2
fi

rm -rf "$ISO"
git clone --filter=blob:none --no-checkout "$REPO_URL" "$ISO"
git -C "$ISO" checkout --detach "$REV"

if [[ ! -f "$ISO/scripts/vps_install_live_camera_consumer.sh" ]]; then
  echo "REFUSE: install script missing at $REV" >&2
  exit 2
fi

APPROVED_REV="$REV" INSTALL_CONFIRM=YES bash "$ISO/scripts/vps_install_live_camera_consumer.sh" install

mkdir -p "$STORE"
chmod 0755 "$STORE" || true
if id mrbot >/dev/null 2>&1; then
  chown mrbot:mrbot "$STORE" || true
fi

if [[ -x "$VENV/bin/python" ]]; then
  PYTHONPATH="$DEST" "$VENV/bin/python" - <<'PY'
import sys
from modules.live_candidate_v2_action.contract import ALERT_ELIGIBLE, CANDIDATE_IS_BUY, PXV_IMPLIES_BUY
from modules.live_candidate_v2_action.observe_store import observe_from_collected_session
from modules.live_candidate_v2_action.sidecar_source import resolve_published_v2_sidecar
from modules.live_candidate_v2_action.state import evaluate_shadow_action
from modules.live_candidate_v2_camera.contract import GITHUB_V2_SIDECAR_PATH
from modules.live_shadow_transport.shadow_store import publish_v2_action_state
assert CANDIDATE_IS_BUY is False
assert PXV_IMPLIES_BUY is False
assert ALERT_ELIGIBLE is False
assert GITHUB_V2_SIDECAR_PATH == "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
assert "modules.live_candidate_v2_action.replay" not in sys.modules
assert "modules.live_candidate_v2_camera.sidecar" not in sys.modules
assert "modules.intraday_memory.provider" not in sys.modules
assert "modules.intraday_memory.collector" not in sys.modules
print("IMPORT_OK", GITHUB_V2_SIDECAR_PATH, observe_from_collected_session, resolve_published_v2_sidecar, evaluate_shadow_action, publish_v2_action_state)
PY
fi

PATCHED_ARTIFACTS=NO
if [[ -f "$SERVER_PY" ]] && ! grep -q '/current/live_shadow/v2_action_state.json' "$SERVER_PY"; then
  python3 - "$SERVER_PY" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
legacy = """LIVE_SHADOW_GET_PATHS = {
    "/current/live_shadow/live_evidence.jsonl": "live_evidence.jsonl",
    "/current/live_shadow/live_shadow_status.json": "live_shadow_status.json",
}
"""
wanted = """LIVE_SHADOW_GET_PATHS = {
    "/current/live_shadow/live_evidence.jsonl": "live_evidence.jsonl",
    "/current/live_shadow/live_shadow_status.json": "live_shadow_status.json",
    "/current/live_shadow/v2_action_state.json": "v2_action_state.json",
}
"""
if wanted in text:
    raise SystemExit(0)
if legacy not in text:
    raise SystemExit("LIVE_SHADOW_GET_PATHS shape unexpected — refuse Camera overlay")
path.write_text(text.replace(legacy, wanted, 1), encoding="utf-8")
print("PATCHED_ARTIFACT_SERVER_GET")
PY
  PATCHED_ARTIFACTS=YES
fi

if [[ -f "$ISO/deploy/systemd/${OBSERVE_SERVICE}" ]]; then
  install -m 644 "$ISO/deploy/systemd/${OBSERVE_SERVICE}" "${UNIT_DIR}/${OBSERVE_SERVICE}"
  install -m 644 "$ISO/deploy/systemd/${OBSERVE_TIMER}" "${UNIT_DIR}/${OBSERVE_TIMER}"
fi

# Leftover #168/#169 drop-in for a unit that was never installed.
if [[ ! -f "${UNIT_DIR}/${PHANTOM_SERVICE}" ]]; then
  rm -rf "${UNIT_DIR}/${PHANTOM_SERVICE}.d"
fi

if [[ "${RESTART_CONFIRM:-}" != "YES" ]]; then
  echo "FILES_UPDATED=$DEST REV=$REV"
  echo "RESTART_SKIPPED (set RESTART_CONFIRM=YES)"
  exit 0
fi

systemctl daemon-reload
systemctl enable --now "$OBSERVE_TIMER"
# One fail-closed observe now (sidecar/parquet may be stale; do not invent bars).
systemctl start "$OBSERVE_SERVICE" || true
systemctl is-active "$OBSERVE_TIMER"

NEED_ARTIFACT_RESTART=NO
if [[ "$PATCHED_ARTIFACTS" == "YES" || "${ARTIFACT_RESTART:-}" == "YES" ]]; then
  NEED_ARTIFACT_RESTART=YES
fi
if [[ "$NEED_ARTIFACT_RESTART" == "YES" ]]; then
  echo "RESTARTING $ARTIFACT_SERVICE (GET allowlist / post-overlay bounce)"
  systemctl restart "$ARTIFACT_SERVICE"
  systemctl is-active "$ARTIFACT_SERVICE"
fi

echo "UPDATED_DEST=$DEST"
echo "UPDATED_REV=$REV"
echo "CAMERA_UNTOUCHED_GIT=YES"
echo "COLLECT_UNITS_UNTOUCHED=YES"
echo "ROTATION_WATCH_UNTOUCHED=YES"
echo "V2_SIDECAR_SOURCE=github"
echo "KBS_POLLED=NO"

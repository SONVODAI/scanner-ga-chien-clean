#!/usr/bin/env bash
# Update /opt/mrbot-live-shadow for SHADOW-ONLY V2 Camera observation.
#
# Does NOT checkout/reset /opt/mrbot-camera.
# Does NOT start Brain A. Does NOT enable production BUY.
# Does NOT reboot the VPS.
# Restarts only mrbot-live-camera-shadow (and mrbot-edge-artifacts when the
# GET allowlist must gain v2_action_state.json for Cloud Streamlit).
#
# Usage:
#   $0 plan <rev>
#   INSTALL_CONFIRM=YES $0 apply <rev>
#   INSTALL_CONFIRM=YES RESTART_CONFIRM=YES $0 apply <rev>
set -euo pipefail

MODE="${1:-plan}"
REV="${2:-${UPDATE_REV:-}}"
CAMERA="/opt/mrbot-camera"
DEST="/opt/mrbot-live-shadow"
VENV="/opt/mrbot-camera-venv"
SERVICE="mrbot-live-camera-shadow.service"
ARTIFACT_SERVICE="mrbot-edge-artifacts.service"
SERVER_PY="${CAMERA}/modules/edge_research/artifact_server.py"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN="${DROPIN_DIR}/v2-sidecar.conf"
STORE="/var/lib/mrbot/live_pxv_shadow"
REPO_URL="https://github.com/SONVODAI/scanner-ga-chien-clean.git"
ISO="/tmp/mrbot-live-shadow-src-v2-${REV:0:12}"

print_plan() {
  cat <<EOF
=== VPS V2 SHADOW OBSERVE UPDATE (not executed unless MODE=apply) ===
REV=${REV:-MISSING}
CAMERA_TREE=$CAMERA  (DO NOT git checkout / reset / merge)
INSTALL_DEST=$DEST
SHADOW_STORE=$STORE
SERVICE=$SERVICE
ARTIFACT_SERVICE=$ARTIFACT_SERVICE  (restart only if GET allowlist lacks v2_action_state.json)
V2_SIDECAR=GitHub Contents research/live_candidate_v2_camera_sidecar/camera_sidecar.json
ENV=MRBOT_V2_SIDECAR_SOURCE=github
FORBIDDEN:
  - Brain A / Gate A on VPS
  - production BUY / Telegram / NAV / orders
  - treating Elite watchlist as V2 nominations
  - VPS reboot
STEPS:
  1. Clone $REV and rsync the pinned consumer allowlist into $DEST
  2. Ensure $STORE exists (0755, leave existing Elite files)
  3. systemd drop-in $DROPIN
  4. PYTHONPATH=$DEST import LiveShadowFeed + sidecar_source
  5. Restart $SERVICE only
  6. If $SERVER_PY lacks v2_action_state.json GET, surgical overlay + $ARTIFACT_SERVICE restart
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
# Persistent SHADOW artifacts. Do not chown away from the camera-shadow user if set.
if id mrbot >/dev/null 2>&1; then
  chown mrbot:mrbot "$STORE" || true
fi

mkdir -p "$DROPIN_DIR"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=MRBOT_V2_SIDECAR_SOURCE=github
Environment=MRBOT_LIVE_PXV_SHADOW_STORE=/var/lib/mrbot/live_pxv_shadow
EOF

if [[ -x "$VENV/bin/python" ]]; then
  PYTHONPATH="$DEST" "$VENV/bin/python" - <<'PY'
import sys
from modules.live_camera_shadow.feed import LiveShadowFeed
from modules.live_candidate_v2_action.contract import ALERT_ELIGIBLE, CANDIDATE_IS_BUY, PXV_IMPLIES_BUY
from modules.live_candidate_v2_action.sidecar_source import resolve_published_v2_sidecar
from modules.live_candidate_v2_action.state import evaluate_shadow_action
from modules.live_candidate_v2_camera.contract import GITHUB_V2_SIDECAR_PATH
from modules.live_shadow_transport.shadow_store import publish_shadow_artifacts
assert CANDIDATE_IS_BUY is False
assert PXV_IMPLIES_BUY is False
assert ALERT_ELIGIBLE is False
assert GITHUB_V2_SIDECAR_PATH == "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
assert "modules.intraday_memory.storage" not in sys.modules
assert "modules.live_candidate_v2_action.replay" not in sys.modules
assert "modules.live_candidate_v2_camera.sidecar" not in sys.modules
print("IMPORT_OK", GITHUB_V2_SIDECAR_PATH, LiveShadowFeed, resolve_published_v2_sidecar, evaluate_shadow_action, publish_shadow_artifacts)
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

if [[ "${RESTART_CONFIRM:-}" != "YES" ]]; then
  echo "FILES_UPDATED=$DEST REV=$REV"
  echo "RESTART_SKIPPED (set RESTART_CONFIRM=YES)"
  exit 0
fi

systemctl daemon-reload
systemctl restart "$SERVICE"
systemctl is-active "$SERVICE"
if [[ "$PATCHED_ARTIFACTS" == "YES" && "${RESTART_ARTIFACTS:-YES}" == "YES" ]]; then
  echo "RESTARTING $ARTIFACT_SERVICE (new GET path required for Cloud Streamlit)"
  systemctl restart "$ARTIFACT_SERVICE"
  systemctl is-active "$ARTIFACT_SERVICE"
fi
echo "UPDATED_DEST=$DEST"
echo "UPDATED_REV=$REV"
echo "CAMERA_UNTOUCHED_GIT=YES"
echo "V2_SIDECAR_SOURCE=github"

#!/usr/bin/env bash
# Install the isolated Rotation Watch --live --loop systemd service.
#
# Run on host mrbot-camera as root. Never run from a Cloud Agent.
# Does not pull / reset /opt/mrbot-camera.
# Does not restart Camera timers, Edge artifacts, or Candidate services.
# Does not rewrite the human watchlist, engine, UI, or trading rules.
#
#   bash deploy/systemd/install-rotation-watch.sh            # plan + copy + unit
#   ROTATION_LOOP_CONFIRM=YES bash deploy/systemd/install-rotation-watch.sh
#
# ROTATION_SRC defaults to this repo root. Point it at an unpacked PR checkout
# that is NOT /opt/mrbot-camera.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${ROTATION_SRC:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
DEST="/opt/mrbot-rotation-watch"
CAMERA="/opt/mrbot-camera"
VENV="/opt/mrbot-camera-venv"
STORE="/var/lib/mrbot/rotation_watch"
UNIT_DIR="/etc/systemd/system"
ENV_FILE="/etc/mrbot/rotation-watch.env"
SERVICE="mrbot-rotation-watch.service"
CAMERA_SERVICE_HINTS="mrbot-intraday-collect.timer mrbot-intraday-reconcile.timer mrbot-edge-artifacts.service"

die() { echo "STOP: $*" >&2; exit 2; }
note() { echo "OK: $*"; }

[[ "$(id -u)" -eq 0 ]] || die "must run as root on mrbot-camera"
[[ -d "${DEST}" ]] || die "isolated sidecar missing: ${DEST} (run prior Rotation smoke C)"
[[ -x "${VENV}/bin/python" ]] || die "missing ${VENV}/bin/python"
[[ -f "${DEST}/scripts/run_rotation_watch.py" ]] || die "sidecar runner missing in ${DEST}"
[[ -d "${SRC}/modules/rotation_watch" ]] || die "ROTATION_SRC missing rotation module: ${SRC}"
[[ "${SRC}" != "${CAMERA}" ]] || die "ROTATION_SRC must not be ${CAMERA}"

# Refuse a second --loop that is not this systemd unit.
stray_pids="$(pgrep -f '/opt/mrbot-rotation-watch/scripts/run_rotation_watch.py --live --loop' || true)"
if [[ -n "${stray_pids}" ]]; then
  if systemctl is-active --quiet "${SERVICE}"; then
    note "existing ${SERVICE} holds the loop (pids: ${stray_pids//$'\n'/ })"
  else
    die "stray Rotation --loop process (pids: ${stray_pids//$'\n'/ }); stop it before install"
  fi
fi

note "SRC=${SRC}"
note "DEST=${DEST}"
note "STORE=${STORE}"

install -d "${STORE}"
install -d /etc/mrbot
install -m 644 "${SRC}/scripts/run_rotation_watch.py" "${DEST}/scripts/run_rotation_watch.py"
install -m 644 "${SRC}/modules/rotation_watch/runner.py" "${DEST}/modules/rotation_watch/runner.py"
install -m 644 "${SRC}/deploy/systemd/mrbot-rotation-watch.service" "${UNIT_DIR}/${SERVICE}"

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 "${SRC}/deploy/systemd/mrbot-rotation-watch.env.example" "${ENV_FILE}"
  note "created ${ENV_FILE}"
else
  note "keeping existing ${ENV_FILE}"
fi

grep -q '^MRBOT_ROTATION_WATCH_STORE=/var/lib/mrbot/rotation_watch$' "${ENV_FILE}" \
  || die "${ENV_FILE} must set isolated MRBOT_ROTATION_WATCH_STORE"
grep -q 'intraday_memory' "${ENV_FILE}" && die "${ENV_FILE} must not point at Camera archive"
grep -q 'live_pxv_shadow' "${ENV_FILE}" && die "${ENV_FILE} must not point at Candidate store"
grep -q 'edge_research_durable' "${ENV_FILE}" && die "${ENV_FILE} must not point at Edge store"

systemctl daemon-reload
note "installed ${SERVICE} (daemon-reload only — Camera/Edge units untouched)"

if [[ "${ROTATION_LOOP_CONFIRM:-}" != "YES" ]]; then
  echo "PLAN: set ROTATION_LOOP_CONFIRM=YES to enable --now or restart ${SERVICE}"
  echo "OTHER_SERVICES_NOT_TOUCHED=${CAMERA_SERVICE_HINTS}"
  exit 0
fi

if systemctl is-active --quiet "${SERVICE}"; then
  systemctl restart "${SERVICE}"
  note "restarted ${SERVICE} (single unit restart)"
else
  systemctl enable --now "${SERVICE}"
  note "enabled and started ${SERVICE}"
fi

systemctl is-active --quiet "${SERVICE}" || die "${SERVICE} is not active"
loop_n="$(pgrep -c -f '/opt/mrbot-rotation-watch/scripts/run_rotation_watch.py --live --loop' || true)"
[[ "${loop_n}" -eq 1 ]] || die "expected exactly 1 Rotation --loop process, got ${loop_n}"

for other in mrbot-intraday-collect.timer mrbot-intraday-reconcile.timer mrbot-edge-artifacts.service; do
  if systemctl list-unit-files "${other}" --no-legend 2>/dev/null | grep -q "${other}"; then
    note "left ${other} untouched (active=$(systemctl is-active "${other}" || true))"
  fi
done

echo "ROTATION_SERVICE=${SERVICE}"
echo "ROTATION_LOOP_PIDS=$(pgrep -d, -f '/opt/mrbot-rotation-watch/scripts/run_rotation_watch.py --live --loop' || true)"
echo "OTHER_SERVICES_NOT_TOUCHED=${CAMERA_SERVICE_HINTS}"

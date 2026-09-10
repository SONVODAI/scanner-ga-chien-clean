#!/usr/bin/env bash
# Reverse the surgical artifact overlay. Does not touch Camera archive.
# Does not start or stop the live Camera shadow runner except to refuse starting it.
set -euo pipefail

PROD_REPO="${MRBOT_PROD_REPO:-/opt/mrbot-camera}"
SERVICE="${MRBOT_ARTIFACT_SERVICE:-mrbot-edge-artifacts.service}"
BACKUP="${1:-}"

if [[ -z "$BACKUP" ]]; then
  echo "usage: $0 /var/lib/mrbot/live_pxv_shadow_overlay_backup/<stamp>" >&2
  exit 2
fi
if [[ ! -f "$BACKUP/artifact_server.py.bak" ]]; then
  echo "missing $BACKUP/artifact_server.py.bak" >&2
  exit 1
fi

cp -a "$BACKUP/artifact_server.py.bak" "$PROD_REPO/modules/edge_research/artifact_server.py"
if [[ -f "$BACKUP/edge-artifacts.env.bak" ]]; then
  cp -a "$BACKUP/edge-artifacts.env.bak" "${MRBOT_EDGE_ENV:-/etc/mrbot/edge-artifacts.env}"
fi
systemctl restart "$SERVICE"
echo "rolled back artifact_server.py and restarted $SERVICE"
echo "Camera archive was not written"
echo "LIVE RUNNER NOT STARTED"

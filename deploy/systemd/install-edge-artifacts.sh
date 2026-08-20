#!/usr/bin/env bash
# Install Edge Research artifact service (separate from Camera timers).
set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
UNIT_DIR="/etc/systemd/system"
ENV_FILE="/etc/mrbot/edge-artifacts.env"

install -d "${UNIT_DIR}"
install -d /etc/mrbot
install -d /var/lib/mrbot/edge_research_durable

install -m 644 "${REPO}/deploy/systemd/mrbot-edge-artifacts.service" "${UNIT_DIR}/"

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 "${REPO}/deploy/systemd/mrbot-edge-artifacts.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE} — set EDGE_RESEARCH_ARTIFACT_TOKEN before enabling service."
fi

systemctl daemon-reload
echo "Installed mrbot-edge-artifacts.service"
echo "Next:"
echo "  1. Edit ${ENV_FILE} and set EDGE_RESEARCH_ARTIFACT_TOKEN"
echo "  2. systemctl enable --now mrbot-edge-artifacts.service"
echo "  3. Configure HTTPS reverse proxy (see docs/edge_research_artifact_deployment.md)"

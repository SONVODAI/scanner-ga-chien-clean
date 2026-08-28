#!/usr/bin/env bash
# Install and enable headless Edge Research EOD cycle (Phase A → C → B). No Streamlit.
set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
UNIT_DIR="/etc/systemd/system"
ENV_FILE="/etc/mrbot/edge-research.env"

install -d "${UNIT_DIR}"
install -d /etc/mrbot
install -d /opt/mrbot-camera/data/edge_research

install -m 644 "${REPO}/deploy/systemd/mrbot-edge-research-eod.service" "${UNIT_DIR}/"
install -m 644 "${REPO}/deploy/systemd/mrbot-edge-research-eod.timer" "${UNIT_DIR}/"

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 "${REPO}/deploy/systemd/mrbot-edge-research-eod.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE}"
fi

systemctl daemon-reload
systemctl enable --now mrbot-edge-research-eod.timer
echo "Installed and enabled mrbot-edge-research-eod.timer"
echo "Headless entrypoint: /opt/mrbot-camera-venv/bin/python -m modules.edge_research.eod_cycle"
echo "Status: systemctl status mrbot-edge-research-eod.timer"
echo "Next: systemctl list-timers mrbot-edge-research-eod.timer"
echo "Logs: journalctl -u mrbot-edge-research-eod.service -n 100 --no-pager"

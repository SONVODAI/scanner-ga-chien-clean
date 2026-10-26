#!/usr/bin/env bash
# Install headless Edge Research EOD cycle (Phase A → C → B). No Streamlit.
set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
UNIT_DIR="/etc/systemd/system"
ENV_FILE="/etc/mrbot/edge-research.env"

install -d "${UNIT_DIR}"
install -d /etc/mrbot

install -m 644 "${REPO}/deploy/systemd/mrbot-edge-research-eod.service" "${UNIT_DIR}/"
install -m 644 "${REPO}/deploy/systemd/mrbot-edge-research-eod.timer" "${UNIT_DIR}/"

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 "${REPO}/deploy/systemd/mrbot-edge-research-eod.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE}"
fi

systemctl daemon-reload
echo "Installed mrbot-edge-research-eod.service + timer"
echo "This is the same scientific cycle as app.py (run_edge_research_eod_cycle)."
echo "Enable with:"
echo "  systemctl enable --now mrbot-edge-research-eod.timer"
echo "Manual run:"
echo "  python -m modules.edge_research.eod_cycle --trade-date YYYY-MM-DD"

#!/usr/bin/env bash
# Debug-only Edge Research CLI unit. Does NOT enable a second production timer.
# Authoritative production scheduler: mrbot-daily-research.timer
#   → python -m modules.edge_research.opr_bridge.production_daily_run_entrypoint
set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
UNIT_DIR="/etc/systemd/system"
ENV_FILE="/etc/mrbot/edge-research.env"

echo "NOTE: production EOD is mrbot-daily-research.timer (A→C→B runs inside that job)."
echo "This script will NOT enable mrbot-edge-research-eod.timer."

install -d /etc/mrbot
if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 "${REPO}/deploy/systemd/mrbot-edge-research-eod.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE}"
fi

# Install the oneshot service for optional manual debug. Never enable the retired timer.
install -d "${UNIT_DIR}"
install -m 644 "${REPO}/deploy/systemd/mrbot-edge-research-eod.service" "${UNIT_DIR}/"
# Explicitly do not install/enable the timer.
if [[ -f "${UNIT_DIR}/mrbot-edge-research-eod.timer" ]]; then
  echo "WARNING: ${UNIT_DIR}/mrbot-edge-research-eod.timer already exists."
  echo "Leave it disabled. Do not systemctl enable it. Production uses mrbot-daily-research.timer."
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  if systemctl is-enabled --quiet mrbot-edge-research-eod.timer 2>/dev/null; then
    echo "ABORT: mrbot-edge-research-eod.timer is enabled. Disable it to avoid scheduler competition:" >&2
    echo "  systemctl disable --now mrbot-edge-research-eod.timer" >&2
    exit 2
  fi
fi

echo "Installed debug service only (not enabled as a timer)."
echo "Manual debug: python -m modules.edge_research.eod_cycle --trade-date YYYY-MM-DD"
echo "Production: systemctl status mrbot-daily-research.timer"

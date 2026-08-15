#!/usr/bin/env bash
# Install Mr.BOT Intraday Memory systemd units (run on VPS as root).
set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
UNIT_DIR="/etc/systemd/system"
ENV_DIR="/etc/mrbot"
ENV_FILE="${ENV_DIR}/intraday.env"

echo "Installing systemd units from ${REPO}/deploy/systemd/ ..."
install -m 644 "${REPO}/deploy/systemd/mrbot-intraday-collect.service" "${UNIT_DIR}/"
install -m 644 "${REPO}/deploy/systemd/mrbot-intraday-collect.timer" "${UNIT_DIR}/"
install -m 644 "${REPO}/deploy/systemd/mrbot-intraday-reconcile.service" "${UNIT_DIR}/"
install -m 644 "${REPO}/deploy/systemd/mrbot-intraday-reconcile.timer" "${UNIT_DIR}/"

mkdir -p "${ENV_DIR}"
if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 "${REPO}/deploy/systemd/mrbot-intraday.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE} — review before enabling timers."
else
  echo "Keeping existing ${ENV_FILE}"
fi

mkdir -p /var/lib/mrbot/intraday_memory
systemctl daemon-reload
echo "Done. Enable with:"
echo "  systemctl enable --now mrbot-intraday-collect.timer"
echo "  systemctl enable --now mrbot-intraday-reconcile.timer"

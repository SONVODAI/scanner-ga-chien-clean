#!/usr/bin/env bash
# Install daily research systemd units WITHOUT enabling timers (3K.5A contract).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-/etc/systemd/system}"
cp "$SCRIPT_DIR/mrbot-daily-research.service" "$DEST/"
cp "$SCRIPT_DIR/mrbot-daily-research.timer" "$DEST/"
echo "Installed mrbot-daily-research.service and .timer to $DEST"
echo "Timer NOT enabled. Operator must run DAY_0_SMOKE and create genesis first."
echo "To enable later: systemctl enable --now mrbot-daily-research.timer"

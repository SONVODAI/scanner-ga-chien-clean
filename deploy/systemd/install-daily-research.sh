#!/usr/bin/env bash
# Install Mr.BOT autonomous daily research systemd units.
#
# Always installs units and runs daemon-reload (avoids "unit changed on disk" staleness).
# Does NOT enable the timer by default (safe before LIVE_FORWARD genesis).
# When genesis already exists, pass --enable-when-genesis to activate the existing timer.
# --require-active fails closed unless the timer is enabled and active after install.
#
# Does NOT: run research, recover history, create a second timer, touch runtime data,
# require Streamlit, or pip-install.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEST="/etc/systemd/system"
ENABLE_WHEN_GENESIS=0
REQUIRE_ACTIVE=0
DATA_DIR=""

usage() {
  cat <<'EOF'
Usage: install-daily-research.sh [options]

Options:
  --dest DIR              systemd unit destination (default: /etc/systemd/system)
  --repo-root DIR         repository root (default: inferred from script location)
  --data-dir DIR          edge research data dir override (default: <repo>/data/edge_research)
  --enable-when-genesis   enable+start timer iff live_forward_genesis.json exists
  --require-active        fail closed unless timer is enabled and active after install
  -h|--help               show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST="${2:?}"; shift 2 ;;
    --repo-root) REPO_ROOT="${2:?}"; shift 2 ;;
    --data-dir) DATA_DIR="${2:?}"; shift 2 ;;
    --enable-when-genesis) ENABLE_WHEN_GENESIS=1; shift ;;
    --require-active) REQUIRE_ACTIVE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      # Backward compatible: first positional arg = DEST
      if [[ "$1" == /* || "$1" == ./* || "$1" == ../* ]]; then
        DEST="$1"; shift
      else
        echo "ABORT: unknown argument: $1" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

SERVICE_SRC="$SCRIPT_DIR/mrbot-daily-research.service"
TIMER_SRC="$SCRIPT_DIR/mrbot-daily-research.timer"
[[ -f "$SERVICE_SRC" && -f "$TIMER_SRC" ]] || {
  echo "ABORT: missing unit sources under $SCRIPT_DIR" >&2
  exit 2
}

mkdir -p "$DEST"
install -m 644 "$SERVICE_SRC" "$DEST/mrbot-daily-research.service"
install -m 644 "$TIMER_SRC" "$DEST/mrbot-daily-research.timer"
echo "Installed mrbot-daily-research.service and .timer to $DEST"

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  echo "systemctl daemon-reload: OK"
else
  echo "WARN: systemctl not available; skipped daemon-reload"
fi

GENESIS_DIR="${DATA_DIR:-$REPO_ROOT/data/edge_research}"
GENESIS_PATH="$GENESIS_DIR/production_observations/live_forward_genesis.json"
GENESIS_PRESENT=0
if [[ -f "$GENESIS_PATH" ]]; then
  GENESIS_PRESENT=1
fi

if [[ "$ENABLE_WHEN_GENESIS" -eq 1 ]]; then
  if [[ "$GENESIS_PRESENT" -ne 1 ]]; then
    echo "ABORT: --enable-when-genesis set but genesis missing: $GENESIS_PATH" >&2
    exit 3
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "ABORT: systemctl required to enable timer" >&2
    exit 2
  fi
  systemctl enable --now mrbot-daily-research.timer
  echo "Timer enabled/active (genesis present at $GENESIS_PATH)"
else
  if [[ "$GENESIS_PRESENT" -eq 1 ]]; then
    echo "Genesis present ($GENESIS_PATH) but timer not enabled by this invocation."
    echo "Re-run with --enable-when-genesis [--require-active] to activate autonomous scheduling."
  else
    echo "Genesis missing — timer intentionally left disabled."
    echo "Create LIVE_FORWARD genesis, then re-run with --enable-when-genesis."
  fi
fi

if [[ "$REQUIRE_ACTIVE" -eq 1 ]]; then
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "ABORT: --require-active needs systemctl" >&2
    exit 2
  fi
  systemctl is-enabled --quiet mrbot-daily-research.timer || {
    echo "ABORT: mrbot-daily-research.timer is not enabled (--require-active)" >&2
    exit 4
  }
  # is-active for timers returns active when waiting for next trigger
  systemctl is-active --quiet mrbot-daily-research.timer || {
    echo "ABORT: mrbot-daily-research.timer is not active (--require-active)" >&2
    exit 4
  }
  echo "require-active: PASS (timer enabled and active)"
fi

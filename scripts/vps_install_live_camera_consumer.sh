#!/usr/bin/env bash
# MINIMUM operator-safe VPS live Camera consumer install (Phase 3A plan).
#
# DO NOT run until a human explicitly approves VPS install.
# Default MODE=plan prints steps only. Never starts the runner. Never uses --live.
# Never checkouts/resets/merges inside /opt/mrbot-camera.
#
# Auth: the GitHub repo is public. The consumer reads
#   data/live_candidate/dynamic_watchlist.json
# via GitHub Contents GET (Accept: application/vnd.github.raw).
# No token is required. Do not paste secrets into this shell.
# Optional later: if GITHUB_TOKEN already exists in a root-owned env file,
# the consumer will use it automatically (never echo it).
set -euo pipefail

MODE="${1:-plan}"
APPROVED_REV="fedc7d53cb9a902bb7aa73760f00d402f913ed22"
CAMERA="/opt/mrbot-camera"
DEST="/opt/mrbot-live-shadow"
ISO="/tmp/mrbot-live-shadow-src-${APPROVED_REV:0:12}"
VENV="/opt/mrbot-camera-venv"
REPO_URL="https://github.com/SONVODAI/scanner-ga-chien-clean.git"
WATCHLIST_URL="https://api.github.com/repos/SONVODAI/scanner-ga-chien-clean/contents/data/live_candidate/dynamic_watchlist.json"

FILES=(
  "scripts/run_live_camera_shadow.py"
  "modules/live_camera_shadow/__init__.py"
  "modules/live_camera_shadow/bars.py"
  "modules/live_camera_shadow/feed.py"
  "modules/live_camera_shadow/rate.py"
  "modules/live_camera_shadow/universe.py"
  "modules/live_shadow_transport/__init__.py"
  "modules/live_shadow_transport/artifact_get.py"
  "modules/live_shadow_transport/contract.py"
  "modules/live_shadow_transport/freshness.py"
  "modules/live_shadow_transport/shadow_store.py"
  "modules/live_shadow_transport/watchlist_bus.py"
  "modules/live_candidate/__init__.py"
  "modules/live_candidate/calendar.py"
  "modules/live_candidate/contract.py"
  "modules/live_candidate/persist.py"
  "modules/live_candidate/watchlist.py"
  "modules/intraday_pxv_v1/__init__.py"
  "modules/intraday_pxv_v1/archive.py"
  "modules/intraday_pxv_v1/candidates.py"
  "modules/intraday_pxv_v1/constants.py"
  "modules/intraday_pxv_v1/debounce.py"
  "modules/intraday_pxv_v1/evidence.py"
  "modules/intraday_pxv_v1/features.py"
  "modules/intraday_pxv_v1/gate.py"
  "modules/intraday_pxv_v1/interpret.py"
  "modules/intraday_pxv_v1/message.py"
  "modules/intraday_pxv_v1/paths.py"
  "modules/intraday_pxv_v1/time_contract.py"
  "modules/intraday_memory/__init__.py"
  "modules/intraday_memory/config.py"
  "modules/intraday_memory/normalize.py"
  "modules/intraday_memory/schema.py"
  "modules/intraday_memory/timezone_policy.py"
  "modules/intraday_memory/validate.py"
)

# provider.py is required only for a later --live session. Copy it into the
# isolated tree so the consumer is complete, but NEVER import/call it now.
LATER_LIVE_ONLY=(
  "modules/intraday_memory/provider.py"
)

print_plan() {
  cat <<EOF
=== VPS LIVE CONSUMER INSTALL PLAN (not executed) ===
CAMERA_TREE=$CAMERA  (DO NOT git checkout / reset / merge / cherry-pick)
ISOLATED_SRC=$ISO @ $APPROVED_REV
INSTALL_DEST=$DEST
PYTHON=$VENV/bin/python
WATCHLIST_PATH=data/live_candidate/dynamic_watchlist.json
VPS_AUTH_METHOD=public GitHub Contents GET (no token, no secret paste)

PRESERVE:
  - $CAMERA dirty working tree and artifact_server overlay
  - /var/lib/mrbot/intraday_memory
  - /var/lib/mrbot/live_pxv_shadow overlay from Phase 1

FORBIDDEN during this install/proof:
  - --live
  - KBS / provider import or call
  - live runner start
  - evidence writes
  - echoing or pasting GitHub tokens

STEPS (human, after approval):
  1. Confirm no live runner: systemctl is-active mrbot-live-camera-shadow.service || true
  2. git clone --filter=blob:none $REPO_URL $ISO && git -C $ISO checkout $APPROVED_REV
  3. mkdir -p $DEST && rsync listed files from $ISO -> $DEST
  4. Proof (no --live):
       PYTHONPATH=$DEST $VENV/bin/python -c 'from modules.live_shadow_transport.contract import GITHUB_WATCHLIST_PATH; print(GITHUB_WATCHLIST_PATH)'
       curl -sS -D- -o /tmp/wl.json -H 'Accept: application/vnd.github.raw' '$WATCHLIST_URL' | head
       PYTHONPATH=$DEST $VENV/bin/python scripts/run_live_camera_shadow.py
     Expected: path match, HTTP 200, payload parses, dry-run refuses KBS.
FILES:
$(printf '  %s\n' "${FILES[@]}")
LATER_LIVE_ONLY:
$(printf '  %s\n' "${LATER_LIVE_ONLY[@]}")
EOF
}

if [[ "$(pwd)" == "$CAMERA" || "$(pwd)" == "$CAMERA"/* ]]; then
  echo "REFUSE: do not run this from $CAMERA" >&2
  exit 2
fi

if [[ "$MODE" != "install" ]]; then
  print_plan
  echo "MODE=plan (default). Re-run with: $0 install   only after human approval."
  exit 0
fi

if [[ "${INSTALL_CONFIRM:-}" != "YES" ]]; then
  echo "REFUSE: install requires INSTALL_CONFIRM=YES (and still no --live)." >&2
  exit 2
fi

if [[ -d "$CAMERA/.git" ]]; then
  echo "CAMERA_HEAD=$(git -C "$CAMERA" rev-parse HEAD)"
  echo "CAMERA_DIRTY=$(git -C "$CAMERA" status --porcelain | wc -l) files (left untouched)"
fi

rm -rf "$ISO"
git clone --filter=blob:none --no-checkout "$REPO_URL" "$ISO"
git -C "$ISO" checkout --detach "$APPROVED_REV"

mkdir -p "$DEST"
for rel in "${FILES[@]}" "${LATER_LIVE_ONLY[@]}"; do
  mkdir -p "$DEST/$(dirname "$rel")"
  cp -a "$ISO/$rel" "$DEST/$rel"
done

echo "INSTALLED_DEST=$DEST"
echo "INSTALLED_REV=$APPROVED_REV"
echo "CAMERA_UNTOUCHED=YES"
echo "NEXT: PYTHONPATH=$DEST $VENV/bin/python $DEST/scripts/run_live_camera_shadow.py"
echo "DO NOT pass --live. DO NOT start a runner."

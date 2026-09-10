#!/usr/bin/env bash
# Surgical VPS overlay for live-shadow GET paths.
# Run ON the Camera VPS as an operator. This script:
#   - does NOT switch /opt/mrbot-camera onto a research PR
#   - does NOT start the live Camera shadow runner
#   - does NOT write /var/lib/mrbot/intraday_memory
#   - copies ONLY modules/edge_research/artifact_server.py from an isolated clone
#   - mkdir /var/lib/mrbot/live_pxv_shadow
#   - restarts only mrbot-edge-artifacts.service
set -euo pipefail

PROD_REPO="${MRBOT_PROD_REPO:-/opt/mrbot-camera}"
ISOLATED="${MRBOT_ISOLATED_CLONE:-}"
SHADOW_STORE="${MRBOT_LIVE_PXV_SHADOW_STORE:-/var/lib/mrbot/live_pxv_shadow}"
CAMERA="${MRBOT_CAMERA_ARCHIVE:-/var/lib/mrbot/intraday_memory}"
SERVICE="${MRBOT_ARTIFACT_SERVICE:-mrbot-edge-artifacts.service}"
ENV_FILE="${MRBOT_EDGE_ENV:-/etc/mrbot/edge-artifacts.env}"
LIVE_ENV="${MRBOT_LIVE_ENV:-/etc/mrbot/live-shadow.env}"
BACKUP_ROOT="${MRBOT_OVERLAY_BACKUP:-/var/lib/mrbot/live_pxv_shadow_overlay_backup}"
REQUIRED_REV="${MRBOT_REQUIRED_REV:-fedc7d53cb9a902bb7aa73760f00d402f913ed22}"

if [[ -z "$ISOLATED" ]]; then
  echo "Set MRBOT_ISOLATED_CLONE to an isolated git clone (NOT $PROD_REPO)." >&2
  echo "Example:" >&2
  echo "  git clone --branch cursor/live-e2e-transport-1dd0 https://github.com/SONVODAI/scanner-ga-chien-clean.git /tmp/scanner-live-session-01" >&2
  exit 1
fi

prod_real="$(readlink -f "$PROD_REPO")"
iso_real="$(readlink -f "$ISOLATED")"
if [[ "$iso_real" == "$prod_real" ]]; then
  echo "REFUSING: isolated clone must not be $PROD_REPO" >&2
  exit 1
fi
if [[ "$SHADOW_STORE" == "$CAMERA" || "$SHADOW_STORE" == "$CAMERA"/* ]]; then
  echo "REFUSING: shadow store must not be inside Camera archive $CAMERA" >&2
  exit 1
fi

SRC="$ISOLATED/modules/edge_research/artifact_server.py"
DST="$PROD_REPO/modules/edge_research/artifact_server.py"
if [[ ! -f "$SRC" ]]; then
  echo "missing $SRC" >&2
  exit 1
fi
if ! grep -q "LIVE_SHADOW_GET_PATHS" "$SRC"; then
  echo "isolated clone artifact_server.py lacks live-shadow GET paths" >&2
  exit 1
fi
if [[ -n "$REQUIRED_REV" ]] && command -v git >/dev/null; then
  iso_rev="$(git -C "$ISOLATED" rev-parse HEAD)"
  if [[ "$iso_rev" != "$REQUIRED_REV"* && "$iso_rev" != "$REQUIRED_REV" ]]; then
    echo "WARNING: isolated HEAD=$iso_rev expected $REQUIRED_REV (continuing only if MRBOT_ALLOW_REV_MISMATCH=1)" >&2
    if [[ "${MRBOT_ALLOW_REV_MISMATCH:-}" != "1" ]]; then
      exit 1
    fi
  fi
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_ROOT/$stamp"
mkdir -p "$BACKUP"
if [[ -f "$DST" ]]; then
  cp -a "$DST" "$BACKUP/artifact_server.py.bak"
fi
if [[ -f "$ENV_FILE" ]]; then
  cp -a "$ENV_FILE" "$BACKUP/edge-artifacts.env.bak"
fi

# Read-only Camera archive fingerprint. Never write into the archive.
if [[ -d "$CAMERA" ]]; then
  (cd "$CAMERA" && find . -type f | sort | xargs -r sha256sum) > "$BACKUP/camera_archive.sha256" || true
  echo "$CAMERA" > "$BACKUP/camera_archive.path"
else
  echo "camera archive missing at $CAMERA" > "$BACKUP/camera_archive.missing"
fi

mkdir -p "$SHADOW_STORE"
# Ensure store is empty of runner output until a human starts LIVE SESSION 01.
# Do not delete existing evidence if re-run; only create the directory.

# Overlay one file only.
cp -a "$SRC" "$DST"

# Configure store on the existing artifact env file without printing secrets.
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^MRBOT_LIVE_PXV_SHADOW_STORE=' "$ENV_FILE"; then
    sed -i "s|^MRBOT_LIVE_PXV_SHADOW_STORE=.*|MRBOT_LIVE_PXV_SHADOW_STORE=$SHADOW_STORE|" "$ENV_FILE"
  else
    printf '\nMRBOT_LIVE_PXV_SHADOW_STORE=%s\n' "$SHADOW_STORE" >> "$ENV_FILE"
  fi
else
  echo "WARNING: $ENV_FILE missing; service may not see MRBOT_LIVE_PXV_SHADOW_STORE" >&2
fi

umask 077
mkdir -p "$(dirname "$LIVE_ENV")"
cat > "$LIVE_ENV" <<EOF
# Live-shadow runner env (DO NOT start the runner from the overlay script)
MRBOT_WATCHLIST_SOURCE=github
MRBOT_LIVE_PXV_SHADOW_STORE=$SHADOW_STORE
EOF

echo "overlay backup=$BACKUP"
echo "restarting $SERVICE only"
systemctl restart "$SERVICE"
systemctl --no-pager --full status "$SERVICE" | head -n 20
echo "LIVE RUNNER NOT STARTED"
echo "rollback: cp $BACKUP/artifact_server.py.bak $DST && systemctl restart $SERVICE"

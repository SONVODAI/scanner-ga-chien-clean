#!/usr/bin/env bash
# HUMAN-ONLY Rotation Watch VPS smoke install (PR #142 transport, b230b1c90).
#
# Run on host mrbot-camera as root. Never run from a Cloud Agent.
# Default (no args) prints the plan. Each checkpoint is a separate invocation.
#
#   /tmp/vps_rotation_watch_smoke.sh A          # preflight (read-only)
#   /tmp/vps_rotation_watch_smoke.sh B          # backup
#   INSTALL_CONFIRM=YES ... C                   # isolated sidecar + overlay reconcile
#   /tmp/vps_rotation_watch_smoke.sh D          # validate BEFORE restart
#   RESTART_CONFIRM=YES ... E                   # restart artifact service only
#   SMOKE_CONFIRM=YES ... F                     # one TCH --live cycle
#   /tmp/vps_rotation_watch_smoke.sh G          # authenticated GET (token never printed)
#   ROLLBACK_CONFIRM=YES ... H                  # rollback overlay/env/isolated dest
#
# FORBIDDEN in /opt/mrbot-camera:
#   git reset / checkout . / clean / pull / merge / branch switch
# NEVER echo EDGE_RESEARCH_ARTIFACT_TOKEN or cat the env file.
set -euo pipefail

STEP="${1:-plan}"
CAMERA="/opt/mrbot-camera"
VENV="/opt/mrbot-camera-venv"
SERVER_PY="${CAMERA}/modules/edge_research/artifact_server.py"
ENV_FILE="/etc/mrbot/edge-artifacts.env"
DEST="/opt/mrbot-rotation-watch"
STORE="/var/lib/mrbot/rotation_watch"
SERVICE="mrbot-edge-artifacts.service"
READY_WAIT_SEC=15
ISO="/tmp/mrbot-rotation-src-b230b1c90"
STAMP_FILE="/tmp/mrbot-rotation-smoke.stamp"
EXPECTED_SERVER_SHA="ba5c17f4521c2a0b95fbf46d7cb0927da66a68682874e9efe77dee085ef867d1"
EXPECTED_CAMERA_HEAD="ed264c8d686249f668663090ad67b4beb9cbb858"
APPROVED_REV="b230b1c9000f6b6fd043b490c41159f5f4cfb53e"
REPO_URL="https://github.com/SONVODAI/scanner-ga-chien-clean.git"
HEALTH_URL="http://127.0.0.1:8765/health"
SHADOW_EV_URL="http://127.0.0.1:8765/current/live_shadow/live_evidence.jsonl"
ROT_BOARD_URL="http://127.0.0.1:8765/current/rotation_watch/board.json"
ROT_STATUS_URL="http://127.0.0.1:8765/current/rotation_watch/status.json"

ROTATION_OWNED=(
  "scripts/run_rotation_watch.py"
  "data/rotation_watch/watchlist.csv"
  "modules/rotation_watch/__init__.py"
  "modules/rotation_watch/artifact.py"
  "modules/rotation_watch/artifact_get.py"
  "modules/rotation_watch/config.py"
  "modules/rotation_watch/constants.py"
  "modules/rotation_watch/data.py"
  "modules/rotation_watch/engine.py"
  "modules/rotation_watch/html.py"
  "modules/rotation_watch/publish.py"
  "modules/rotation_watch/pxv.py"
  "modules/rotation_watch/read.py"
  "modules/rotation_watch/render.py"
  "modules/rotation_watch/runner.py"
  "modules/rotation_watch/session.py"
  "modules/rotation_watch/state.py"
  "modules/rotation_watch/view.py"
)

# Isolated dest only — never written into /opt/mrbot-camera.
ISO_DEPS=(
  "modules/intraday_pxv_v1/__init__.py"
  "modules/intraday_pxv_v1/constants.py"
  "modules/intraday_pxv_v1/debounce.py"
  "modules/intraday_pxv_v1/evidence.py"
  "modules/intraday_pxv_v1/features.py"
  "modules/intraday_pxv_v1/gate.py"
  "modules/live_camera_shadow/bars.py"
  "modules/live_candidate/calendar.py"
)

die() { echo "STOP: $*" >&2; exit 2; }
note() { echo "OK: $*"; }

sha256_file() { sha256sum "$1" | awk '{print $1}'; }

# vnstock 4.x has no __version__; use installed distribution metadata.
vnstock_installed_version() {
  "${VENV}/bin/python" - <<'PY'
try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:  # pragma: no cover — 3.12 has importlib.metadata
    from importlib_metadata import PackageNotFoundError, version
try:
    print(version("vnstock"), end="")
except PackageNotFoundError:
    raise SystemExit("not-installed")
except Exception as exc:
    raise SystemExit(f"lookup-failed:{type(exc).__name__}")
PY
}

http_code() {
  local url="$1"
  local tmo="${2:-10}"
  curl -sS -o /tmp/mrbot-rotation-http.body -w '%{http_code}' --max-time "${tmo}" "$url" || true
}

wait_artifact_ready() {
  local i hc state
  echo "WAIT_READY up to ${READY_WAIT_SEC}s for ${SERVICE} + /health=200"
  echo "WAIT_READY note: transient curl 000 during this window is not a regression"
  for ((i = 1; i <= READY_WAIT_SEC; i++)); do
    state="$(systemctl is-active "${SERVICE}" 2>/dev/null || echo inactive)"
    hc=000
    if [[ "${state}" == "failed" ]]; then
      echo "WAIT_READY i=${i} systemd=${state} health=skip"
      return 1
    fi
    if [[ "${state}" == "active" ]]; then
      hc="$(http_code "${HEALTH_URL}" 2)"
      [[ "${hc}" =~ ^[0-9]{3}$ ]] || hc=000
    fi
    echo "WAIT_READY i=${i} systemd=${state} health=${hc}"
    if [[ "${state}" == "active" && "${hc}" == "200" ]]; then
      echo "READY: artifact service bound and /health=200"
      return 0
    fi
    sleep 1
  done
  echo "WAIT_READY exhausted after ${READY_WAIT_SEC}s (last systemd=${state} health=${hc})"
  return 1
}

rollback_overlay_and_restart() {
  local reason="$1"
  echo "STOP: ${reason} — rolling back overlay" >&2
  cp -a "${BACKUP_SERVER}" "${SERVER_PY}"
  systemctl restart "${SERVICE}"
  if ! wait_artifact_ready; then
    die "rolled back artifact_server.py but service never became ready (${reason})"
  fi
  local hc sc
  hc="$(http_code "${HEALTH_URL}")"
  sc="$(http_code "${SHADOW_EV_URL}")"
  echo "ROLLBACK_HEALTH=${hc}"
  echo "ROLLBACK_CANDIDATE_UNAUTH=${sc}"
  die "rolled back artifact_server.py (${reason}; health=${hc} candidate=${sc})"
}

ensure_overlay_reconciled() {
  [[ -f "${DEST}/scripts/run_rotation_watch.py" ]] || die "isolated sidecar missing — run C once"
  [[ -d "${STORE}" ]] || die "Rotation store missing — run C once"
  grep -q '^MRBOT_ROTATION_WATCH_STORE=/var/lib/mrbot/rotation_watch$' "${ENV_FILE}" \
    || die "MRBOT_ROTATION_WATCH_STORE missing — run C once"
  if grep -q 'ROTATION_WATCH_GET_PATHS' "${SERVER_PY}" \
    && grep -q '/current/rotation_watch/board.json' "${SERVER_PY}"; then
    note "overlay already has Rotation GET map"
    return 0
  fi
  local sha
  sha="$(sha256_file "${SERVER_PY}")"
  [[ "${sha}" == "${EXPECTED_SERVER_SHA}" ]] \
    || die "overlay SHA ${sha} is neither baseline nor Rotation-reconciled — refusing"
  note "overlay is baseline SHA — re-applying Rotation reconcile only (no C clone)"
  local tmp
  tmp="${SERVER_PY}.rotation-reconcile.$$"
  reconcile_overlay "${SERVER_PY}" "${tmp}"
  "${VENV}/bin/python" -m py_compile "${tmp}"
  cp -a "${tmp}" "${SERVER_PY}"
  rm -f "${tmp}"
  grep -q 'LIVE_SHADOW_GET_PATHS' "${SERVER_PY}" || die "resume reconcile lost Candidate routes"
  grep -q 'ROTATION_WATCH_GET_PATHS' "${SERVER_PY}" || die "resume reconcile missing Rotation routes"
  echo "RECONCILED_SERVER_SHA256=$(sha256_file "${SERVER_PY}")"
}

refuse_camera_git_mutate() {
  if [[ "$(pwd)" == "${CAMERA}" || "$(pwd)" == "${CAMERA}"/* ]]; then
    die "refuse to run from ${CAMERA} (no git mutate of the production tree)"
  fi
}

load_stamp() {
  # shellcheck disable=SC1090
  [[ -f "${STAMP_FILE}" ]] || die "stamp missing — run A then B first"
  # shellcheck disable=SC1090
  source "${STAMP_FILE}"
}

print_plan() {
  cat <<EOF
=== Rotation Watch VPS smoke (HUMAN ONLY, not executed by Cloud Agent) ===
HOST=mrbot-camera
CAMERA=${CAMERA}   (do NOT git reset/pull/checkout/merge)
VENV=${VENV}
OVERLAY=${SERVER_PY}
EXPECTED_OVERLAY_SHA256=${EXPECTED_SERVER_SHA}
EXPECTED_CAMERA_HEAD=${EXPECTED_CAMERA_HEAD}
APPROVED_REV=${APPROVED_REV}
ISOLATED_SRC=${ISO}
ISOLATED_DEST=${DEST}
STORE=${STORE}
SERVICE=${SERVICE}  (only service that may restart)

Checkpoints:
  A  read-only preflight
  B  timestamped backup of overlay + env (env keys only in logs)
  C  isolated file copy + surgical Rotation reconcile of overlay
  D  compile/import/route validation — STOP before restart if fail
  E  restart ${SERVICE} only; wait ready; then health/401 checks
     (D re-reconciles overlay if a prior E rolled back to baseline SHA;
      do not rerun C when dest/store/env already exist)
  F  one --live TCH cycle (no --loop)
  G  authenticated localhost GET without printing the token
  H  rollback overlay / env line / isolated dest / store

PRESERVE: dirty Camera tree, Candidate LIVE_SHADOW_GET_PATHS, Edge bundle + production_observations.
EOF
}

step_A() {
  echo "=== A. PREFLIGHT (read-only) ==="
  hostname
  [[ "$(hostname)" == "mrbot-camera" ]] || echo "WARN: hostname is $(hostname), expected mrbot-camera"
  [[ -d "${CAMERA}" ]] || die "missing ${CAMERA}"
  [[ -x "${VENV}/bin/python" ]] || die "missing ${VENV}/bin/python"
  [[ -f "${SERVER_PY}" ]] || die "missing ${SERVER_PY}"
  [[ -f "${ENV_FILE}" ]] || die "missing ${ENV_FILE}"
  systemctl is-active "${SERVICE}" | grep -qx active || die "${SERVICE} is not active"
  local head
  head="$(git -C "${CAMERA}" rev-parse HEAD)"
  echo "CAMERA_HEAD=${head}"
  echo "CAMERA_DIRTY_FILES=$(git -C "${CAMERA}" status --porcelain | wc -l)"
  [[ "${head}" == "${EXPECTED_CAMERA_HEAD}" ]] || die "Camera HEAD ${head} != ${EXPECTED_CAMERA_HEAD}"
  local sha
  sha="$(sha256_file "${SERVER_PY}")"
  echo "ARTIFACT_SERVER_SHA256=${sha}"
  [[ "${sha}" == "${EXPECTED_SERVER_SHA}" ]] || die "artifact_server SHA256 mismatch — refusing (overlay is not the audited file)"
  grep -q 'LIVE_SHADOW_GET_PATHS' "${SERVER_PY}" || die "LIVE_SHADOW_GET_PATHS missing"
  grep -q '/current/live_shadow/live_evidence.jsonl' "${SERVER_PY}" || die "Candidate live-shadow path missing"
  grep -q '/current/live_shadow/live_shadow_status.json' "${SERVER_PY}" || die "Candidate live-shadow status path missing"
  grep -q 'ALLOWED_PATH' "${SERVER_PY}" || die "Edge bundle ALLOWED_PATH missing"
  grep -q 'ALLOWED_PRODUCTION_OBS_PATH' "${SERVER_PY}" || die "production_observations path missing"
  if grep -q 'ROTATION_WATCH_GET_PATHS' "${SERVER_PY}"; then
    echo "NOTE: Rotation GET map already present in overlay (reconcile will verify, not duplicate)"
  fi
  [[ ! -e "${STORE}" ]] && note "Rotation store does not exist yet (expected)" || echo "NOTE: ${STORE} already exists"
  local pyver vnver
  pyver="$("${VENV}/bin/python" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
  vnver="$(vnstock_installed_version)" || die "vnstock metadata lookup failed (${vnver:-empty})"
  echo "CAMERA_PYTHON=${pyver}"
  echo "CAMERA_VNSTOCK=${vnver}"
  [[ "${pyver}" == "3.12.3" ]] || die "Python ${pyver} != 3.12.3"
  [[ "${vnver}" == "4.0.5" ]] || die "vnstock ${vnver} != 4.0.5"
  local hc sc
  hc="$(http_code "${HEALTH_URL}")"
  echo "HEALTH=${hc}"
  [[ "${hc}" == "200" ]] || die "/health != 200"
  sc="$(http_code "${SHADOW_EV_URL}")"
  echo "CANDIDATE_UNAUTH_GET=${sc}"
  [[ "${sc}" == "401" ]] || die "Candidate live-shadow unauth GET is ${sc}, expected 401"
  echo "ENV_KEYS=$(grep -E '^[A-Za-z0-9_]+=' "${ENV_FILE}" | cut -d= -f1 | tr '\n' ' ')"
  grep -q '^MRBOT_LIVE_PXV_SHADOW_STORE=/var/lib/mrbot/live_pxv_shadow' "${ENV_FILE}" \
    || die "MRBOT_LIVE_PXV_SHADOW_STORE is not the audited value"
  command -v curl >/dev/null || die "curl missing"
  note "preflight passed — overlay SHA and Candidate 401 confirmed"
}

step_B() {
  echo "=== B. BACKUP ==="
  step_A
  local ts dest_dir
  ts="$(date +%Y%m%dT%H%M%S)"
  dest_dir="/root/mrbot-rotation-smoke-backup-${ts}"
  mkdir -p "${dest_dir}"
  cp -a "${SERVER_PY}" "${dest_dir}/artifact_server.py"
  cp -a "${ENV_FILE}" "${dest_dir}/edge-artifacts.env"
  [[ "$(sha256_file "${dest_dir}/artifact_server.py")" == "${EXPECTED_SERVER_SHA}" ]] \
    || die "backup SHA256 mismatch"
  grep -q 'LIVE_SHADOW_GET_PATHS' "${dest_dir}/artifact_server.py" || die "backup lost LIVE_SHADOW_GET_PATHS"
  cat > "${STAMP_FILE}" <<EOF
BACKUP_DIR=${dest_dir}
BACKUP_SERVER=${dest_dir}/artifact_server.py
BACKUP_ENV=${dest_dir}/edge-artifacts.env
BACKUP_SHA=${EXPECTED_SERVER_SHA}
EOF
  chmod 600 "${dest_dir}/edge-artifacts.env"
  echo "BACKUP_DIR=${dest_dir}"
  echo "BACKUP_SERVER_SHA256=$(sha256_file "${dest_dir}/artifact_server.py")"
  echo "BACKUP_ENV_KEYS=$(grep -E '^[A-Za-z0-9_]+=' "${dest_dir}/edge-artifacts.env" | cut -d= -f1 | tr '\n' ' ')"
  note "backup complete — env file copied, values not printed"
}

reconcile_overlay() {
  local src="$1" dest="$2"
  "${VENV}/bin/python" - "$src" "$dest" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1])
dest = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")

def die(msg):
    print("STOP:", msg, file=sys.stderr)
    raise SystemExit(2)

if "LIVE_SHADOW_GET_PATHS" not in text:
    die("LIVE_SHADOW_GET_PATHS missing")
if "/current/live_shadow/live_evidence.jsonl" not in text:
    die("Candidate evidence route missing")
if "/current/live_shadow/live_shadow_status.json" not in text:
    die("Candidate status route missing")
if "ALLOWED_PRODUCTION_OBS_PATH" not in text:
    die("production_observations missing")
if "ALLOWED_PATH" not in text:
    die("Edge bundle ALLOWED_PATH missing")

if "DEFAULT_ROTATION_WATCH_ROOT" not in text:
    needle = 'DEFAULT_LIVE_SHADOW_ROOT = Path("/var/lib/mrbot/live_pxv_shadow")\n'
    if needle not in text:
        die("DEFAULT_LIVE_SHADOW_ROOT line not found — overlay shape unexpected")
    text = text.replace(
        needle,
        needle + 'DEFAULT_ROTATION_WATCH_ROOT = Path("/var/lib/mrbot/rotation_watch")\n',
        1,
    )

if "ROTATION_WATCH_GET_PATHS" not in text:
    needle = """LIVE_SHADOW_GET_PATHS = {
    \"/current/live_shadow/live_evidence.jsonl\": \"live_evidence.jsonl\",
    \"/current/live_shadow/live_shadow_status.json\": \"live_shadow_status.json\",
}
"""
    if needle not in text:
        die("LIVE_SHADOW_GET_PATHS dict block not found — overlay shape unexpected")
    text = text.replace(
        needle,
        needle
        + """ROTATION_WATCH_GET_PATHS = {
    \"/current/rotation_watch/board.json\": \"board.json\",
    \"/current/rotation_watch/status.json\": \"status.json\",
}
""",
        1,
    )

if "rotation_watch_root" not in text:
    needle = "    live_shadow_root: Path = DEFAULT_LIVE_SHADOW_ROOT\n"
    if needle not in text:
        die("live_shadow_root dataclass field not found")
    text = text.replace(
        needle,
        needle + "    rotation_watch_root: Path = DEFAULT_ROTATION_WATCH_ROOT\n",
        1,
    )

if "MRBOT_ROTATION_WATCH_STORE" not in text:
    needle = '        shadow = os.environ.get("MRBOT_LIVE_PXV_SHADOW_STORE", str(DEFAULT_LIVE_SHADOW_ROOT))\n'
    if needle not in text:
        die("MRBOT_LIVE_PXV_SHADOW_STORE from_env line not found")
    text = text.replace(
        needle,
        needle
        + '        rotation = os.environ.get("MRBOT_ROTATION_WATCH_STORE", str(DEFAULT_ROTATION_WATCH_ROOT))\n',
        1,
    )
    needle = "            live_shadow_root=Path(shadow),\n"
    if needle not in text:
        die("live_shadow_root=Path(shadow) not found")
    text = text.replace(
        needle,
        needle + "            rotation_watch_root=Path(rotation),\n",
        1,
    )

rot_block = """        if path in ROTATION_WATCH_GET_PATHS:
            if not _authorize(environ, config.token):
                return _json_response(start_response, 401, {\"error\": \"unauthorized\"})
            if method != \"GET\":
                return _json_response(start_response, 405, {\"error\": \"method_not_allowed\"})
            filename = ROTATION_WATCH_GET_PATHS[path]
            src = Path(config.rotation_watch_root) / filename
            if not src.is_file():
                return _json_response(start_response, 404, {\"error\": \"rotation_watch_not_found\"})
            body = src.read_bytes()
            content_type = \"application/json\" if filename.endswith(\".json\") else \"application/x-ndjson\"
            return _bytes_response(start_response, 200, body, content_type)

"""
if "if path in ROTATION_WATCH_GET_PATHS" not in text:
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith("        if path in LIVE_SHADOW_GET_PATHS:"):
            start = i
            break
    if start is None:
        die("LIVE_SHADOW_GET_PATHS dispatch block not found")
    i = start + 1
    while i < len(lines):
        raw = lines[i]
        if raw.startswith("        if ") and i > start:
            break
        i += 1
    text = "".join(lines[:i] + [rot_block] + lines[i:])

for req in (
    "LIVE_SHADOW_GET_PATHS",
    "/current/live_shadow/live_evidence.jsonl",
    "ALLOWED_PRODUCTION_OBS_PATH",
    "ROTATION_WATCH_GET_PATHS",
    "/current/rotation_watch/board.json",
    "/current/rotation_watch/status.json",
    "rotation_watch_not_found",
    "live_shadow_not_found",
):
    if req not in text:
        die(f"reconciled file missing {req}")

dest.write_text(text, encoding="utf-8")
print("RECONCILED", dest)
PY
}

step_C() {
  echo "=== C. NARROW INSTALL / RECONCILE ==="
  [[ "${INSTALL_CONFIRM:-}" == "YES" ]] || die "C requires INSTALL_CONFIRM=YES"
  refuse_camera_git_mutate
  load_stamp
  if [[ -f "${DEST}/scripts/run_rotation_watch.py" && -d "${STORE}" ]] \
    && grep -q '^MRBOT_ROTATION_WATCH_STORE=/var/lib/mrbot/rotation_watch$' "${ENV_FILE}"; then
    die "C already applied (isolated dest, store, env key present). Resume with D then E — do not rerun C."
  fi
  [[ -f "${BACKUP_SERVER}" ]] || die "backup missing"
  [[ "$(sha256_file "${SERVER_PY}")" == "${EXPECTED_SERVER_SHA}" ]] \
    || die "live overlay SHA changed since backup — refusing"

  rm -rf "${ISO}"
  git clone --filter=blob:none --no-checkout "${REPO_URL}" "${ISO}"
  git -C "${ISO}" checkout --detach "${APPROVED_REV}"
  [[ "$(git -C "${ISO}" rev-parse HEAD)" == "${APPROVED_REV}" ]] || die "isolated clone rev mismatch"

  mkdir -p "${DEST}"
  local rel
  for rel in "${ROTATION_OWNED[@]}" "${ISO_DEPS[@]}"; do
    mkdir -p "${DEST}/$(dirname "${rel}")"
    cp -a "${ISO}/${rel}" "${DEST}/${rel}"
  done
  # Stub package inits so we do not pull live-shadow feed / Candidate watchlist / collector.
  printf '%s\n' '# Isolated Rotation smoke package. Do not import Camera collector or live-shadow feed.' \
    > "${DEST}/modules/live_camera_shadow/__init__.py"
  printf '%s\n' '# Isolated Rotation smoke package. Calendar only.' \
    > "${DEST}/modules/live_candidate/__init__.py"
  mkdir -p "${STORE}"
  chmod 755 "${STORE}"

  if grep -q '^MRBOT_ROTATION_WATCH_STORE=' "${ENV_FILE}"; then
    grep -q '^MRBOT_ROTATION_WATCH_STORE=/var/lib/mrbot/rotation_watch$' "${ENV_FILE}" \
      || die "MRBOT_ROTATION_WATCH_STORE exists but is not the approved path"
    note "env already has MRBOT_ROTATION_WATCH_STORE"
  else
    printf '\nMRBOT_ROTATION_WATCH_STORE=/var/lib/mrbot/rotation_watch\n' >> "${ENV_FILE}"
    note "appended MRBOT_ROTATION_WATCH_STORE (token untouched)"
  fi
  echo "ENV_KEYS_NOW=$(grep -E '^[A-Za-z0-9_]+=' "${ENV_FILE}" | cut -d= -f1 | tr '\n' ' ')"

  local tmp
  tmp="${SERVER_PY}.rotation-reconcile.$$"
  reconcile_overlay "${SERVER_PY}" "${tmp}"
  "${VENV}/bin/python" -m py_compile "${tmp}"
  cp -a "${tmp}" "${SERVER_PY}"
  rm -f "${tmp}"
  grep -q 'LIVE_SHADOW_GET_PATHS' "${SERVER_PY}" || die "post-reconcile lost Candidate routes"
  grep -q 'ROTATION_WATCH_GET_PATHS' "${SERVER_PY}" || die "post-reconcile missing Rotation routes"
  echo "RECONCILED_SERVER_SHA256=$(sha256_file "${SERVER_PY}")"
  echo "WATCHLIST=$("${VENV}/bin/python" -c "from pathlib import Path; print(Path('${DEST}/data/rotation_watch/watchlist.csv').read_text())")"
  note "isolated dest + overlay reconcile written — service still on old process until E"
}

step_D() {
  echo "=== D. VALIDATE BEFORE RESTART ==="
  load_stamp
  ensure_overlay_reconciled
  "${VENV}/bin/python" -m py_compile "${SERVER_PY}"
  grep -q 'LIVE_SHADOW_GET_PATHS' "${SERVER_PY}" || die "Candidate LIVE_SHADOW_GET_PATHS missing"
  grep -q '/current/live_shadow/live_evidence.jsonl' "${SERVER_PY}" || die "Candidate evidence path missing"
  grep -q '/current/live_shadow/live_shadow_status.json' "${SERVER_PY}" || die "Candidate status path missing"
  grep -q 'ALLOWED_PATH' "${SERVER_PY}" || die "bundle path missing"
  grep -q 'ALLOWED_PRODUCTION_OBS_PATH' "${SERVER_PY}" || die "production_observations missing"
  grep -q 'ROTATION_WATCH_GET_PATHS' "${SERVER_PY}" || die "Rotation map missing"
  grep -q '/current/rotation_watch/board.json' "${SERVER_PY}" || die "Rotation board path missing"
  grep -q '/current/rotation_watch/status.json' "${SERVER_PY}" || die "Rotation status path missing"
  grep -q 'method != "GET"' "${SERVER_PY}" || die "GET-only guard missing"
  grep -q 'rotation_watch_not_found' "${SERVER_PY}" || die "Rotation 404 marker missing"
  grep -q 'live_shadow_not_found' "${SERVER_PY}" || die "Candidate 404 marker missing"
  # Still on old process — Candidate unauth must still be 401.
  local sc hc
  hc="$(http_code "${HEALTH_URL}")"
  [[ "${hc}" == "200" ]] || die "pre-restart /health ${hc}"
  sc="$(http_code "${SHADOW_EV_URL}")"
  [[ "${sc}" == "401" ]] || die "pre-restart Candidate unauth ${sc}"

  PYTHONPATH="${DEST}:${CAMERA}" "${VENV}/bin/python" - <<'PY'
import importlib
from pathlib import Path
mod = importlib.import_module("modules.rotation_watch.runner")
print("RUNNER_OK", mod.run_cycle)
from modules.intraday_memory.provider import KBSProvider
print("KBSPROVIDER_OK", KBSProvider)
from modules.rotation_watch.publish import ALLOWED_ROTATION_FILES
assert ALLOWED_ROTATION_FILES == ("board.json", "status.json")
print("PUBLISH_ALLOWLIST_OK", ALLOWED_ROTATION_FILES)
wl = Path("/opt/mrbot-rotation-watch/data/rotation_watch/watchlist.csv").read_text()
assert "TCH" in wl
assert wl.count("\n") <= 3
print("WATCHLIST_TCH_ONLY_OK")
PY
  local vnver
  vnver="$(vnstock_installed_version)" || die "vnstock metadata lookup failed (${vnver:-empty})"
  echo "CAMERA_VNSTOCK=${vnver}"
  [[ "${vnver}" == "4.0.5" ]] || die "vnstock changed to ${vnver}"
  [[ ! -d /opt/mrbot-streamlit-venv ]] || echo "NOTE: streamlit venv present — not modified"
  note "pre-restart validation passed — safe to run E"
}

step_E() {
  echo "=== E. RESTART ARTIFACT SERVICE ONLY ==="
  [[ "${RESTART_CONFIRM:-}" == "YES" ]] || die "E requires RESTART_CONFIRM=YES"
  load_stamp
  step_D
  systemctl restart "${SERVICE}"
  if ! wait_artifact_ready; then
    rollback_overlay_and_restart "service never became ready after restart"
  fi
  local hc sc rc
  hc="$(http_code "${HEALTH_URL}")"
  echo "HEALTH=${hc}"
  sc="$(http_code "${SHADOW_EV_URL}")"
  echo "CANDIDATE_UNAUTH_GET=${sc}"
  rc="$(http_code "${ROT_BOARD_URL}")"
  echo "ROTATION_UNAUTH_GET=${rc}"
  if [[ "${hc}" != "200" || "${sc}" != "401" ]]; then
    rollback_overlay_and_restart "Candidate/health regression health=${hc} candidate=${sc}"
  fi
  if [[ "${rc}" == "500" ]]; then
    rollback_overlay_and_restart "Rotation unauth GET 500"
  fi
  [[ "${rc}" == "401" ]] || die "Rotation unauth GET is ${rc}, expected 401. Candidate still 401 — overlay NOT auto-rolled back. Inspect, then H if needed."
  note "service active; /health 200; Candidate 401; Rotation 401"
}

step_F() {
  echo "=== F. ONE TCH LIVE CYCLE (no --loop) ==="
  [[ "${SMOKE_CONFIRM:-}" == "YES" ]] || die "F requires SMOKE_CONFIRM=YES"
  load_stamp
  [[ -x "${DEST}/scripts/run_rotation_watch.py" ]] || die "sidecar missing — run C"
  export MRBOT_ROTATION_WATCH_STORE="${STORE}"
  export MRBOT_ROTATION_WATCH_DIR="${DEST}/data/rotation_watch"
  export PYTHONPATH="${DEST}:${CAMERA}"
  cd "${DEST}"
  set +e
  "${VENV}/bin/python" scripts/run_rotation_watch.py --live
  local rc=$?
  set -e
  echo "LIVE_EXIT=${rc}"
  echo "=== working artifacts ==="
  ls -l "${DEST}/data/rotation_watch" || true
  echo "=== store copies ==="
  ls -l "${STORE}" || true
  if [[ -f "${STORE}/board.json" ]]; then
    "${VENV}/bin/python" - <<'PY'
import json
from pathlib import Path
board = json.loads(Path("/var/lib/mrbot/rotation_watch/board.json").read_text())
status = json.loads(Path("/var/lib/mrbot/rotation_watch/status.json").read_text()) if Path("/var/lib/mrbot/rotation_watch/status.json").exists() else {}
print("BOARD_SCHEMA", board.get("schema"))
print("SESSION_PHASE", board.get("session_phase"))
print("OBSERVED_AT", board.get("observed_at"))
print("SOURCE", board.get("source"))
for row in board.get("rows") or []:
    print("ROW", json.dumps({
        "symbol": row.get("symbol"),
        "last_session_state": row.get("last_session_state"),
        "suggested_action": row.get("suggested_action"),
        "session_phase": row.get("session_phase"),
        "published_pxv": row.get("published_pxv"),
        "freshness": row.get("freshness"),
        "data_source": row.get("data_source") or row.get("source"),
        "last_bar_ts": row.get("last_bar_ts"),
        "actionable": row.get("actionable"),
    }, ensure_ascii=False))
print("STATUS", json.dumps(status, ensure_ascii=False, default=str)[:4000])
PY
  else
    echo "NOTE: store board.json missing — report actual provider/sidecar output above. Do not fake success."
  fi
  [[ "${rc}" -eq 0 ]] || echo "NOTE: --live exited ${rc} — report as-is"
}

step_G() {
  echo "=== G. AUTHENTICATED GET (token never printed) ==="
  "${VENV}/bin/python" - <<'PY'
import json
import urllib.error
import urllib.request
from pathlib import Path

def load_token() -> str:
    token = ""
    for raw in Path("/etc/mrbot/edge-artifacts.env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        if key.strip() == "EDGE_RESEARCH_ARTIFACT_TOKEN":
            token = val.strip().strip('"').strip("'")
            break
    if not token:
        raise SystemExit("STOP: EDGE_RESEARCH_ARTIFACT_TOKEN missing")
    return token

def get(url: str, token: str | None) -> tuple[int, bytes]:
    headers = {"User-Agent": "mrbot-rotation-smoke"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()

token = load_token()
pairs = [
    ("ROTATION_BOARD", "http://127.0.0.1:8765/current/rotation_watch/board.json"),
    ("ROTATION_STATUS", "http://127.0.0.1:8765/current/rotation_watch/status.json"),
    ("CANDIDATE_EVIDENCE", "http://127.0.0.1:8765/current/live_shadow/live_evidence.jsonl"),
    ("CANDIDATE_STATUS", "http://127.0.0.1:8765/current/live_shadow/live_shadow_status.json"),
]
for name, url in pairs:
    code, body = get(url, token)
    print(f"{name}_HTTP={code}")
    if name.startswith("ROTATION") and code == 200:
        try:
            print(body.decode("utf-8"))
        except UnicodeDecodeError:
            print(f"{name}_BYTES={len(body)}")
    elif name.startswith("CANDIDATE"):
        print(f"{name}_NOTE=200 means artifact present; 404 is legitimate if store empty")
        if code == 200:
            print(f"{name}_BYTES={len(body)}")
        else:
            print(body.decode("utf-8", errors="replace")[:300])
del token
PY
}

step_H() {
  echo "=== H. ROLLBACK ==="
  [[ "${ROLLBACK_CONFIRM:-}" == "YES" ]] || die "H requires ROLLBACK_CONFIRM=YES"
  load_stamp
  [[ -f "${BACKUP_SERVER}" ]] || die "backup server missing"
  cp -a "${BACKUP_SERVER}" "${SERVER_PY}"
  [[ "$(sha256_file "${SERVER_PY}")" == "${BACKUP_SHA}" ]] || die "rollback SHA mismatch"
  if [[ -f "${BACKUP_ENV}" ]]; then
    cp -a "${BACKUP_ENV}" "${ENV_FILE}"
  fi
  systemctl restart "${SERVICE}"
  if ! wait_artifact_ready; then
    die "rollback restart: service never became ready"
  fi
  local hc sc
  hc="$(http_code "${HEALTH_URL}")"
  sc="$(http_code "${SHADOW_EV_URL}")"
  echo "HEALTH=${hc} CANDIDATE_UNAUTH=${sc}"
  echo "Optional leftover cleanup (not run automatically):"
  echo "  rm -rf ${DEST} ${ISO} ${STORE}"
  note "overlay + env restored; Candidate routes should match the audited overlay"
}

refuse_camera_git_mutate
case "${STEP}" in
  plan|"") print_plan ;;
  A|a) step_A ;;
  B|b) step_B ;;
  C|c) step_C ;;
  D|d) step_D ;;
  E|e) step_E ;;
  F|f) step_F ;;
  G|g) step_G ;;
  H|h) step_H ;;
  *) die "unknown step ${STEP} (use plan|A|B|C|D|E|F|G|H)" ;;
esac

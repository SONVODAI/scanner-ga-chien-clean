#!/usr/bin/env bash
# HUMAN-ONLY: expand isolated Rotation watchlist TCH → Top 10, then ONE --live cycle.
# Does not restart services, pull Camera git, start --loop, or print tokens.
#
#   TOP10_CONFIRM=YES /tmp/vps_rotation_watch_top10.sh
set -euo pipefail

[[ "${TOP10_CONFIRM:-}" == "YES" ]] || {
  echo "STOP: TOP10_CONFIRM=YES required" >&2
  exit 2
}

CAMERA="/opt/mrbot-camera"
VENV="/opt/mrbot-camera-venv"
DEST="/opt/mrbot-rotation-watch"
STORE="/var/lib/mrbot/rotation_watch"
WL="${DEST}/data/rotation_watch/watchlist.csv"
TS="$(date +%Y%m%dT%H%M%S)"
BACKUP="/root/mrbot-rotation-watchlist-tch-only-${TS}.csv"
EXPECTED='CII TCH DXG PHR NLG TCB TVS DGW DRI MSR'

die() { echo "STOP: $*" >&2; exit 2; }

[[ "$(hostname)" == "mrbot-camera" ]] || echo "WARN: hostname is $(hostname), expected mrbot-camera"
[[ -f "${WL}" ]] || die "isolated watchlist missing: ${WL}"
[[ -x "${VENV}/bin/python" ]] || die "missing ${VENV}/bin/python"
[[ -f "${DEST}/scripts/run_rotation_watch.py" ]] || die "sidecar runner missing"

cp -a "${WL}" "${BACKUP}"
chmod 600 "${BACKUP}"
echo "BACKUP_WATCHLIST=${BACKUP}"
echo "BACKUP_SHA256=$(sha256sum "${BACKUP}" | awk '{print $1}')"
echo "BACKUP_BYTES=$(wc -c < "${BACKUP}")"

HAVE="$("${VENV}/bin/python" - "${WL}" <<'PY'
import sys
from pathlib import Path
import pandas as pd
df = pd.read_csv(Path(sys.argv[1]), dtype=str, keep_default_na=False)
print(" ".join(str(s).strip().upper() for s in df["symbol"] if str(s).strip()))
PY
)"
echo "WATCHLIST_HAVE=${HAVE}"
if [[ "${HAVE}" == "${EXPECTED}" ]]; then
  echo "WATCHLIST_REWRITE=skipped"
else
  echo "WATCHLIST_REWRITE=write"
  cat > "${WL}" <<'CSV'
symbol,enabled,lower_min,lower_max,upper_min,upper_max,entry_price,entry_date,note
CII,true,13.8,14.2,14.3,15.0,,,"original human Rotation Top-10 zone"
TCH,true,11.6,11.9,12.2,12.4,,,"original human Rotation Top-10 zone"
DXG,true,10.85,11.0,11.5,12.1,,,"original human Rotation Top-10 zone"
PHR,true,58.7,59.8,61.7,62.0,,,"original human Rotation Top-10 zone"
NLG,true,23.5,24.0,24.5,25.7,,,"original human Rotation Top-10 zone"
TCB,true,30.8,31.3,32.0,34.1,,,"original human Rotation Top-10 zone"
TVS,true,13.45,13.8,14.0,14.5,,,"original human Rotation Top-10 zone"
DGW,true,40.05,41.3,42.7,43.15,,,"original human Rotation Top-10 zone"
DRI,true,13.0,13.3,13.7,14.2,,,"original human Rotation Top-10 zone"
MSR,true,38.3,39.3,39.9,40.0,,,"original human Rotation Top-10 zone"
CSV
fi
echo "WATCHLIST_NOW_SHA256=$(sha256sum "${WL}" | awk '{print $1}')"

export MRBOT_ROTATION_WATCH_STORE="${STORE}"
export MRBOT_ROTATION_WATCH_DIR="${DEST}/data/rotation_watch"
export PYTHONPATH="${DEST}:${CAMERA}"
cd "${DEST}"
set +e
"${VENV}/bin/python" scripts/run_rotation_watch.py --live
rc=$?
set -e
echo "LIVE_EXIT=${rc}"

"${VENV}/bin/python" - "${WL}" "${STORE}" "${EXPECTED}" <<'PY'
import json
import sys
from pathlib import Path

wl_path, store, expected = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].split()
import pandas as pd

df = pd.read_csv(wl_path, dtype=str, keep_default_na=False)
syms = [str(s).strip().upper() for s in df["symbol"] if str(s).strip()]
print("WATCHLIST_N", len(syms))
print("WATCHLIST_SYMBOLS", " ".join(syms))
if syms != expected:
    raise SystemExit(f"STOP: watchlist symbols {syms} != {expected}")
if not all(str(v).strip().lower() == "true" for v in df["enabled"]):
    raise SystemExit("STOP: all rows must be enabled=true")

board = json.loads((store / "board.json").read_text(encoding="utf-8"))
status = json.loads((store / "status.json").read_text(encoding="utf-8"))
print("BOARD_SCHEMA", board.get("schema"))
print("STATUS_SCHEMA", status.get("schema"))
print("STATUS_N", status.get("n_symbols"))
print("BOARD_SESSION", board.get("session_phase"))
print("STATUS_SESSION", status.get("session_phase"))
if board.get("schema") != "rotation_watch_board.v1":
    raise SystemExit("STOP: board schema")
if status.get("schema") != "rotation_watch_status.v1":
    raise SystemExit("STOP: status schema")
if int(status.get("n_symbols") or 0) != 10:
    raise SystemExit(f"STOP: status n_symbols={status.get('n_symbols')}")
rows = board.get("rows") or []
got = [str(r.get("symbol") or "") for r in rows]
print("BOARD_N", len(rows))
print("BOARD_SYMBOLS", " ".join(got))
if got != expected:
    raise SystemExit(f"STOP: board symbols {got} != {expected}")
need = (
    "current_price",
    "location",
    "lower_zone",
    "upper_zone",
    "range_position_pct",
    "last_session_state",
    "last_session_action",
    "raw_pxv",
    "published_pxv",
    "freshness",
    "session_phase",
    "suggested_action",
    "actionable",
    "last_bar_ts",
    "data_source",
)
failed = []
for row in rows:
    missing = [k for k in need if k not in row]
    session = str(row.get("session_phase") or board.get("session_phase") or "")
    print(
        "ROW",
        json.dumps(
            {k: row.get(k) for k in ("symbol",) + need},
            ensure_ascii=False,
        ),
    )
    if missing:
        failed.append(f"{row.get('symbol')}: missing {missing}")
    if session != "WEEKEND":
        failed.append(f"{row.get('symbol')}: session={session}")
    if row.get("actionable") is True:
        failed.append(f"{row.get('symbol')}: actionable true")
    if str(row.get("suggested_action") or "") != "WAIT":
        failed.append(f"{row.get('symbol')}: action={row.get('suggested_action')}")
    if not str(row.get("last_session_state") or ""):
        failed.append(f"{row.get('symbol')}: empty last_session_state")
    if str(row.get("data_source") or "") == "unavailable" or row.get("current_price") is None:
        print(f"NOTE: {row.get('symbol')} fail-closed/unusable source={row.get('data_source')} err={row.get('freshness_reason') or row.get('freshness')}")
if failed:
    print("STOP_DETAILS", "; ".join(failed))
    raise SystemExit("STOP: weekend/row validation failed")
print("LOCAL_STORE_OK")
PY

echo "NOTE: public HTTPS check uses EDGE_RESEARCH_DURABLE_URL if exported; else https://mrbot-edge.duckdns.org"
echo "NOTE: bearer from /etc/mrbot/edge-artifacts.env — not printed"

BASE="${EDGE_RESEARCH_DURABLE_URL:-https://mrbot-edge.duckdns.org}"
BASE="${BASE%/}"
python3 - "${BASE}" "${EXPECTED}" <<'PY'
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

base, expected = sys.argv[1].rstrip("/"), sys.argv[2].split()
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

def get(path: str) -> tuple[int, bytes]:
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "mrbot-rotation-top10/1.0"},
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read() if exc.fp else b""

print("PUBLIC_BASE_HOST", urlparse(base).netloc)
print("TOKEN_PRINTED=no")
b_code, b_raw = get("/current/rotation_watch/board.json")
s_code, s_raw = get("/current/rotation_watch/status.json")
print("PUBLIC_BOARD_AUTH", b_code)
print("PUBLIC_STATUS_AUTH", s_code)
if b_code != 200 or s_code != 200:
    raise SystemExit("STOP: public Rotation GET not 200/200")
board = json.loads(b_raw.decode("utf-8"))
status = json.loads(s_raw.decode("utf-8"))
print("PUBLIC_BOARD_SCHEMA", board.get("schema"))
print("PUBLIC_STATUS_SCHEMA", status.get("schema"))
print("PUBLIC_BOARD_N", len(board.get("rows") or []))
print("PUBLIC_STATUS_N", status.get("n_symbols"))
got = [str(r.get("symbol") or "") for r in (board.get("rows") or [])]
if got != expected:
    raise SystemExit(f"STOP: public board symbols {got}")
if board.get("schema") != "rotation_watch_board.v1" or status.get("schema") != "rotation_watch_status.v1":
    raise SystemExit("STOP: public schema")
if any(r.get("actionable") is True for r in board.get("rows") or []):
    raise SystemExit("STOP: public row actionable")
print("PUBLIC_HTTPS_OK")
PY

echo "OK: Top-10 one cycle complete — STOP. Do not start --loop or Telegram."
echo "LIVE_EXIT_WAS=${rc}"
[[ "${rc}" -eq 0 ]] || echo "NOTE: sidecar --live exited ${rc}; inspect ROWs above"

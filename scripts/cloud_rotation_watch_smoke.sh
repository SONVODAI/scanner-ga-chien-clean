#!/usr/bin/env bash
# HUMAN-ONLY Cloud←VPS Rotation Watch HTTPS smoke.
# Proves the existing durable URL serves Rotation GET the same way as Candidate.
# Never prints EDGE_RESEARCH_DURABLE_TOKEN / EDGE_RESEARCH_ARTIFACT_TOKEN.
# Does not deploy Streamlit, restart services, or merge.
#
#   EDGE_RESEARCH_DURABLE_URL=https://<host>/edge-research \
#   EDGE_RESEARCH_DURABLE_TOKEN=<same bearer Streamlit uses> \
#   /tmp/cloud_rotation_watch_smoke.sh
set -euo pipefail

die() { echo "STOP: $*" >&2; exit 2; }

BASE="${EDGE_RESEARCH_DURABLE_URL:-}"
TOKEN="${EDGE_RESEARCH_DURABLE_TOKEN:-}"
[[ -n "${BASE}" ]] || die "set EDGE_RESEARCH_DURABLE_URL (Streamlit secret name; do not commit the value)"
[[ -n "${TOKEN}" ]] || die "set EDGE_RESEARCH_DURABLE_TOKEN (do not print or commit the value)"
BASE="${BASE%/}"

http_code() {
  local url="$1"
  local auth="${2:-}"
  if [[ -n "${auth}" ]]; then
    curl -sS -o /tmp/rw-cloud.body -w '%{http_code}' --max-time 20 \
      -H "Authorization: Bearer ${auth}" "$url" || true
  else
    curl -sS -o /tmp/rw-cloud.body -w '%{http_code}' --max-time 20 "$url" || true
  fi
}

python3 - <<PY
from urllib.parse import urlparse
p = urlparse("${BASE}")
print(f"DURABLE_SCHEME={p.scheme}")
print(f"DURABLE_HOST={p.netloc}")
print(f"DURABLE_PREFIX={p.path or '/'}")
PY

CAND_UNAUTH="$(http_code "${BASE}/current/live_shadow/live_evidence.jsonl")"
ROT_B_UNAUTH="$(http_code "${BASE}/current/rotation_watch/board.json")"
ROT_S_UNAUTH="$(http_code "${BASE}/current/rotation_watch/status.json")"
echo "CANDIDATE_UNAUTH_GET=${CAND_UNAUTH}"
echo "ROTATION_BOARD_UNAUTH=${ROT_B_UNAUTH}"
echo "ROTATION_STATUS_UNAUTH=${ROT_S_UNAUTH}"
[[ "${ROT_B_UNAUTH}" == "401" ]] || die "Rotation board unauth expected 401, got ${ROT_B_UNAUTH}"
[[ "${ROT_S_UNAUTH}" == "401" ]] || die "Rotation status unauth expected 401, got ${ROT_S_UNAUTH}"

ROT_B="$(http_code "${BASE}/current/rotation_watch/board.json" "${TOKEN}")"
echo "ROTATION_BOARD_AUTH=${ROT_B}"
[[ "${ROT_B}" == "200" ]] || die "Rotation board auth expected 200, got ${ROT_B}"
python3 - <<'PY'
import json
from pathlib import Path
board = json.loads(Path("/tmp/rw-cloud.body").read_text(encoding="utf-8"))
rows = board.get("rows") or []
print("BOARD_SCHEMA", board.get("schema"))
print("BOARD_SESSION", board.get("session_phase"))
print("BOARD_SOURCE", board.get("source"))
print("BOARD_OBSERVED", board.get("observed_at"))
print("BOARD_N", len(rows))
for row in rows:
    print("ROW", json.dumps({
        "symbol": row.get("symbol"),
        "current_price": row.get("current_price"),
        "location": row.get("location"),
        "last_session_state": row.get("last_session_state"),
        "last_session_action": row.get("last_session_action"),
        "suggested_action": row.get("suggested_action"),
        "published_pxv": row.get("published_pxv"),
        "freshness": row.get("freshness"),
        "session_phase": row.get("session_phase"),
        "actionable": row.get("actionable"),
        "last_bar_ts": row.get("last_bar_ts"),
        "data_source": row.get("data_source"),
    }, ensure_ascii=False))
    if row.get("actionable") is True:
        raise SystemExit("STOP: weekend/historical artifact must not be actionable")
    if str(row.get("suggested_action") or "") in {"BUY READY", "SELL READY"} and str(row.get("session_phase") or "") == "WEEKEND":
        raise SystemExit("STOP: weekend current action must be WAIT")
PY

ROT_S="$(http_code "${BASE}/current/rotation_watch/status.json" "${TOKEN}")"
echo "ROTATION_STATUS_AUTH=${ROT_S}"
[[ "${ROT_S}" == "200" ]] || die "Rotation status auth expected 200, got ${ROT_S}"
python3 - <<'PY'
import json
from pathlib import Path
status = json.loads(Path("/tmp/rw-cloud.body").read_text(encoding="utf-8"))
print("STATUS_SCHEMA", status.get("schema"))
print("STATUS_SESSION", status.get("session_phase"))
if status.get("schema") != "rotation_watch_status.v1":
    raise SystemExit("STOP: unexpected status schema")
PY

CAND_AUTH="$(http_code "${BASE}/current/live_shadow/live_evidence.jsonl" "${TOKEN}")"
echo "CANDIDATE_AUTH_GET=${CAND_AUTH}"
echo "NOTE: Candidate 200 = evidence present; 404 = empty live-shadow store (legitimate)"

unset TOKEN
echo "OK: external HTTPS Rotation GET matched Candidate durable path (token not printed)"
echo "NOT CLAIMED: Streamlit Cloud panel. That requires deploying this PR's app.py to the Cloud-connected branch."

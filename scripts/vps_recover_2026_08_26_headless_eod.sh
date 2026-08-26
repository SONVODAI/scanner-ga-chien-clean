#!/usr/bin/env bash
# Controlled 2026-08-26 RECOVERY / MANUAL REMEDIATION on production VPS.
#
# Prerequisites (already verified by operator audit):
#   - HEAD contains headless EOD + this repair
#   - Streamlit NOT opened for this recovery path
#   - Today's autonomous FAIL ledgers/manifests MUST remain untouched
#
# This script:
#   1) installs research-venv deps (vnstock==0.2.9.2)
#   2) verifies trading-day probe for 2026-08-26
#   3) runs ONE labeled recovery (--recovery --mode RECOVERY_MANUAL_REMEDIATION)
#   4) does NOT overwrite headless_eod_status.json autonomy FAIL evidence
#
# Usage (on mrbot-camera as deploy user):
#   sudo -u <deploy> bash scripts/vps_recover_2026_08_26_headless_eod.sh
set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
VENV="${MRBOT_RESEARCH_VENV:-/opt/mrbot-research-venv}"
TD="${RECOVERY_TRADE_DATE:-2026-08-26}"
PY="${VENV}/bin/python"
AUTONOMY_STATUS="${REPO}/data/forecast_research/headless_eod_status.json"
AUTONOMY_BACKUP="/tmp/mrbot-autonomy-fail-evidence-${TD}.json"

cd "${REPO}"

echo "== PRE: preserve autonomy FAIL evidence =="
if [[ -f "${AUTONOMY_STATUS}" ]]; then
  cp -a "${AUTONOMY_STATUS}" "${AUTONOMY_BACKUP}"
  echo "backed_up ${AUTONOMY_STATUS} -> ${AUTONOMY_BACKUP}"
  sha256sum "${AUTONOMY_STATUS}" "${AUTONOMY_BACKUP}"
else
  echo "WARN: autonomy status missing at ${AUTONOMY_STATUS}"
fi

echo "== STEP: install research deps =="
bash "${REPO}/scripts/install_research_venv_deps.sh"

echo "== STEP: verify probe recognizes ${TD} =="
"${PY}" - <<PY
from modules.production_eod.headless_eod import resolve_trading_today, PROBE_OK
r = resolve_trading_today("${TD}")
print({"trading_today": r.trading_today, "probe_status": r.probe_status, "reason": r.reason})
assert r.probe_status == PROBE_OK and r.trading_today is True, r
print("probe_ok")
PY

echo "== STEP: recovery run (NOT autonomous evidence) =="
"${PY}" -m modules.edge_research.opr_bridge.production_daily_run_entrypoint \
  --trade-date "${TD}" \
  --mode RECOVERY_MANUAL_REMEDIATION \
  --recovery \
  --use-lock

echo "== POST: prove autonomy FAIL evidence preserved =="
if [[ -f "${AUTONOMY_BACKUP}" && -f "${AUTONOMY_STATUS}" ]]; then
  if cmp -s "${AUTONOMY_BACKUP}" "${AUTONOMY_STATUS}"; then
    echo "PRESERVED: headless_eod_status.json unchanged vs pre-recovery backup"
  else
    echo "ALERT: autonomy status file changed — investigate before accepting recovery" >&2
    diff -u "${AUTONOMY_BACKUP}" "${AUTONOMY_STATUS}" || true
    exit 2
  fi
fi
echo "Recovery status (if any): ${REPO}/data/forecast_research/headless_eod_recovery_status.json"
ls -la "${REPO}/data/forecast_research/recovery_runs" 2>/dev/null || true
echo "DONE — classify ${TD} autonomy as FAIL; this run is RECOVERY_MANUAL_REMEDIATION only"

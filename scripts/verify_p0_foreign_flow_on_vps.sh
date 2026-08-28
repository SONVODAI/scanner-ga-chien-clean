#!/usr/bin/env bash
# Run on the REAL production VPS only — AFTER this branch is present in the checkout.
#
# If this file is missing on VPS, that is NOT provider failure: it only exists on
# unmerged PR #89. Prefer the standalone probe with NO deploy:
#   curl -fsSL -o /tmp/standalone_ssi_foreign_flow_probe.py \
#     https://raw.githubusercontent.com/SONVODAI/scanner-ga-chien-clean/cursor/p0-foreign-flow-vps-verification-aad2/scripts/standalone_ssi_foreign_flow_probe.py
#   python3 /tmp/standalone_ssi_foreign_flow_probe.py --out /tmp/ssi_foreign_probe.json
# See diagnostics/p0_foreign_flow_vps_verification/OPERATOR_STANDALONE_PROBE.md
#
# Usage (only when this script exists in the checkout):
#   cd /opt/mrbot-camera
#   bash scripts/verify_p0_foreign_flow_on_vps.sh
# Optional:
#   TRADE_DATE=2026-08-22 bash scripts/verify_p0_foreign_flow_on_vps.sh
#
# Prefer the Python that powers Streamlit / market_t0_capture (vnstock 0.2.9.2
# with fr_trade_heatmap). Collector venv vnstock 4.x does NOT expose that API.

set -euo pipefail

REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
TRADE_DATE="${TRADE_DATE:-}"
OUT_DIR="${REPO}/diagnostics/p0_foreign_flow_vps_verification"
mkdir -p "${OUT_DIR}"

if [[ ! -d "${REPO}/modules/forecast_research" ]]; then
  echo "ERROR: ${REPO} is not a Mr.BOT checkout with forecast_research. Refusing." >&2
  echo "Use scripts/standalone_ssi_foreign_flow_probe.py via /tmp instead (no deploy)." >&2
  exit 2
fi
if [[ ! -f "${REPO}/modules/forecast_research/p0_foreign_vps_verify.py" ]]; then
  echo "ERROR: p0_foreign_vps_verify.py missing (PR #89 not in this checkout)." >&2
  echo "Use /tmp standalone probe — see OPERATOR_STANDALONE_PROBE.md" >&2
  exit 2
fi

cd "${REPO}"

pick_python() {
  local candidates=(
    "${MRBOT_APP_PYTHON:-}"
    "${REPO}/.venv/bin/python"
    "/opt/mrbot-camera-venv/bin/python"
    "python3"
  )
  local py
  for py in "${candidates[@]}"; do
    [[ -z "${py}" ]] && continue
    if [[ -x "${py}" ]] || command -v "${py}" >/dev/null 2>&1; then
      if "${py}" -c "from vnstock import fr_trade_heatmap" >/dev/null 2>&1; then
        echo "${py}"
        return 0
      fi
    fi
  done
  # Fallback: still run probe so operator sees import/HTTP evidence
  for py in "${candidates[@]}"; do
    [[ -z "${py}" ]] && continue
    if [[ -x "${py}" ]] || command -v "${py}" >/dev/null 2>&1; then
      echo "${py}"
      return 0
    fi
  done
  echo "python3"
}

PY="$(pick_python)"
echo "Using Python: ${PY}"
"${PY}" -c "import sys, vnstock; print('python', sys.version); print('vnstock', getattr(vnstock,'__file__',None)); print('has_fr', hasattr(vnstock,'fr_trade_heatmap'))" || true

ARGS=( -m modules.forecast_research.p0_foreign_vps_verify --out "${OUT_DIR}/vps_probe.json" )
if [[ -n "${TRADE_DATE}" ]]; then
  ARGS+=( --trade-date "${TRADE_DATE}" )
fi

"${PY}" "${ARGS[@]}"

echo
echo "Wrote ${OUT_DIR}/vps_probe.json"
echo "If provider_reachable=YES, also run:"
echo "  ${PY} -m modules.forecast_research.daily_entrypoint --p0-collect --trade-date <session>"
echo "then re-run collect once to confirm ALREADY_PRESENT idempotency."

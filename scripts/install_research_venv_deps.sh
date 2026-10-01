#!/usr/bin/env bash
# Install headless/research dependencies into the daily-research venv.
# Safe to re-run. Does not open Streamlit. Does not reboot.
set -euo pipefail

VENV="${MRBOT_RESEARCH_VENV:-/opt/mrbot-research-venv}"
REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
REQ="${REPO}/requirements-research.txt"

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "ERROR: missing interpreter ${VENV}/bin/python" >&2
  exit 1
fi
if [[ ! -f "${REQ}" ]]; then
  echo "ERROR: missing ${REQ}" >&2
  exit 1
fi

echo "== research venv =="
"${VENV}/bin/python" -V
echo "== installing ${REQ} =="
"${VENV}/bin/pip" install -r "${REQ}"
echo "== verify vnstock =="
"${VENV}/bin/python" - <<'PY'
import vnstock
from vnstock import stock_historical_data
print("vnstock_ok", getattr(vnstock, "__version__", "unknown"))
print("stock_historical_data", callable(stock_historical_data))
PY
echo "DONE"

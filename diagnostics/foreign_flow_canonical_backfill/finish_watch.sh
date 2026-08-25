#!/usr/bin/env bash
set -u
cd /workspace
LOG=diagnostics/foreign_flow_canonical_backfill/watcher.log
PIDFILE=/tmp/ff_stage_b_backfill.pid
prev=$(ls data/foreign_flow_history/canonical/by_symbol/*.csv 2>/dev/null | wc -l)
echo "watcher_start $(date -u +%H:%M:%SZ) prev=$prev" >> "$LOG"
while true; do
  alive=0
  if [[ -f "$PIDFILE" ]]; then
    pid=$(cat "$PIDFILE" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && ps -p "$pid" >/dev/null 2>&1; then alive=1; fi
  fi
  py=$(pgrep -f '^python3 -m modules.foreign_flow_history.backfill' || true)
  if [[ -n "${py:-}" ]]; then
    alive=1
    echo "$py" | awk 'NR==1{print; exit}' > "$PIDFILE"
  fi
  n=$(ls data/foreign_flow_history/canonical/by_symbol/*.csv 2>/dev/null | wc -l)
  echo "$(date -u +%H:%M:%SZ) alive=$alive csvs=$n" >> "$LOG"
  if [[ "$n" -ge $((prev + 10)) ]]; then
    git add data/foreign_flow_history/canonical data/foreign_flow_history/manifests diagnostics/foreign_flow_canonical_backfill || true
    git commit -m "WIP Stage B foreign-flow backfill progress (${n}/117 symbols)" || true
    git push -u origin cursor/hsx-foreign-flow-canonical-backfill-aad2 || true
    prev=$n
  fi
  if [[ "$alive" = "0" ]]; then
    sleep 8
    py2=$(pgrep -f '^python3 -m modules.foreign_flow_history.backfill' || true)
    [[ -n "${py2:-}" ]] && continue
    break
  fi
  sleep 90
done
echo "PROCESS_EXITED $(date -u +%H:%M:%SZ)" >> "$LOG"
python3 - <<'PY'
import json
from pathlib import Path
elig=json.loads(Path("diagnostics/foreign_flow_historical_audit/ems142_hsx_eligibility.json").read_text())
hose=set(s.upper() for s in elig["hose_eligible"])
cp=json.loads(Path("data/foreign_flow_history/manifests/backfill_checkpoint.json").read_text())
done={s for s,m in (cp.get("symbols") or {}).items() if str(m.get("status","")).startswith("completed")}
pending=sorted(hose-done)
rl=[s for s,m in (cp.get("symbols") or {}).items() if m.get("status")=="rate_limited"]
print("completed", len(hose&done), "/", len(hose), "pending", len(pending), "rate_limited", rl)
Path("/tmp/stage_b_need_resume").write_text("1" if pending and not rl else "0")
PY
NEED=$(cat /tmp/stage_b_need_resume)
ROUND=0
while [[ "$NEED" = "1" && "$ROUND" -lt 3 ]]; do
  ROUND=$((ROUND+1))
  echo "RESUMING_ROUND_${ROUND} $(date -u +%H:%M:%SZ)" >> "$LOG"
  python3 -m modules.foreign_flow_history.backfill --stage B --page-size 1000 --pacing-sec 0.3 >> diagnostics/foreign_flow_canonical_backfill/stage_b_run.log 2>&1
  python3 - <<'PY'
import json
from pathlib import Path
elig=json.loads(Path("diagnostics/foreign_flow_historical_audit/ems142_hsx_eligibility.json").read_text())
hose=set(s.upper() for s in elig["hose_eligible"])
cp=json.loads(Path("data/foreign_flow_history/manifests/backfill_checkpoint.json").read_text())
done={s for s,m in (cp.get("symbols") or {}).items() if str(m.get("status","")).startswith("completed")}
pending=sorted(hose-done)
rl=[s for s,m in (cp.get("symbols") or {}).items() if m.get("status")=="rate_limited"]
Path("/tmp/stage_b_need_resume").write_text("1" if pending and not rl else "0")
print("post_resume", len(hose&done), len(pending), rl)
PY
  NEED=$(cat /tmp/stage_b_need_resume)
done
python3 -m modules.foreign_flow_history.backfill --stage freeze
python3 diagnostics/foreign_flow_canonical_backfill/build_report.py
git add data/foreign_flow_history/canonical data/foreign_flow_history/manifests diagnostics/foreign_flow_canonical_backfill
git commit -m "Complete Stage B HSX foreign-flow canonical backfill + research freeze" || true
git push -u origin cursor/hsx-foreign-flow-canonical-backfill-aad2 || true
echo "ALL_DONE $(date -u +%H:%M:%SZ)" >> "$LOG"

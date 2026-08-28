# Operator runbook — P0 SSI foreign-flow probe WITHOUT production deploy

**STOP before any production deployment / merge of PRs #85–#89.**

Missing `scripts/verify_p0_foreign_flow_on_vps.sh` on VPS is expected: that file exists only on unmerged PR #89. It is **not** provider failure.

---

## 1. Where the verifier lives

| Item | Value |
| --- | --- |
| Branch | `cursor/p0-foreign-flow-vps-verification-aad2` |
| Commit (introduces wrapper + module) | `fd53312a1d30ac5371155013087e502bb23be566` |
| Wrapper script | `scripts/verify_p0_foreign_flow_on_vps.sh` |
| Module (needs PR stack) | `modules/forecast_research/p0_foreign_vps_verify.py` |
| **Standalone (preferred)** | `scripts/standalone_ssi_foreign_flow_probe.py` |
| On `main`? | **NO** |
| On PR #88 tip? | **NO** (wrapper only landed in #89) |

---

## 2. PR dependency vs production HEAD

PR stack (unmerged):

```text
main
 └─ #85  cursor/forecast-data-contract-v1-aad2
      └─ #87  cursor/historical-fc-recovery-mdrr-v1-aad2
           └─ #88  cursor/p0-forward-market-memory-aad2
                └─ #89  cursor/p0-foreign-flow-vps-verification-aad2   ← verifier
```

- PR **#89 depends on unmerged #85 → #87 → #88** (stacked bases).
- PR **#86** (forensic audit) is a **sibling** off `main`; **not** an ancestor of #89.
- Production VPS HEAD on `main` (or any pre-#85 checkout) **does not** contain #85–#89 commits → script missing is correct.

---

## 3. SAFEST procedure (read-only, no app deploy)

Prefer downloading the **standalone** probe into `/tmp` and running it. No `git pull`, no merge, no service restart, no write under application code paths (output defaults to `/tmp`).

### A. Inspect current VPS HEAD (read-only)

```bash
cd /opt/mrbot-camera
git rev-parse --short HEAD
git log -1 --oneline
git status -sb
test -f scripts/verify_p0_foreign_flow_on_vps.sh && echo SCRIPT_PRESENT || echo SCRIPT_ABSENT_EXPECTED
test -f scripts/standalone_ssi_foreign_flow_probe.py && echo STANDALONE_PRESENT || echo STANDALONE_ABSENT_EXPECTED
```

### B. Download standalone probe to /tmp (no deploy)

```bash
curl -fsSL -o /tmp/standalone_ssi_foreign_flow_probe.py \
  https://raw.githubusercontent.com/SONVODAI/scanner-ga-chien-clean/cursor/p0-foreign-flow-vps-verification-aad2/scripts/standalone_ssi_foreign_flow_probe.py

# optional integrity check
wc -l /tmp/standalone_ssi_foreign_flow_probe.py
head -5 /tmp/standalone_ssi_foreign_flow_probe.py
```

### C. Run probe with app Python first (legacy vnstock / fr_trade_heatmap)

```bash
# Discover pythons that can see vnstock
for PY in \
  "${MRBOT_APP_PYTHON:-}" \
  /opt/mrbot-camera/.venv/bin/python \
  "$(command -v python3)" \
  /opt/mrbot-camera-venv/bin/python
do
  [ -z "$PY" ] && continue
  [ -x "$PY" ] || command -v "$PY" >/dev/null 2>&1 || continue
  echo "=== $PY ==="
  "$PY" -c "import sys; print(sys.version); import vnstock; print('vnstock', getattr(vnstock,'__file__',None)); print('has_fr', hasattr(vnstock,'fr_trade_heatmap'))" 2>/dev/null || echo "vnstock unavailable"
done
```

```bash
# Pick the interpreter that prints has_fr True if possible; else python3
PY="${MRBOT_APP_PYTHON:-python3}"
"$PY" /tmp/standalone_ssi_foreign_flow_probe.py --out /tmp/ssi_foreign_probe.json
```

### D. Also probe collector venv (vnstock 4.x — may lack fr_trade_heatmap)

```bash
/opt/mrbot-camera-venv/bin/python /tmp/standalone_ssi_foreign_flow_probe.py \
  --out /tmp/ssi_foreign_probe_collector_venv.json || true
```

### E. Read result (still no deploy)

```bash
python3 - <<'PY'
import json
for p in ("/tmp/ssi_foreign_probe.json","/tmp/ssi_foreign_probe_collector_venv.json"):
  try:
    d=json.load(open(p))
  except FileNotFoundError:
    print(p, "MISSING"); continue
  print("====", p)
  print("verdict:", d.get("verdict"))
  print("reachable:", d.get("production_result",{}).get("provider_reachable"))
  print("http:", d.get("production_result",{}).get("http_status"), d.get("production_result",{}).get("server"))
  print("heatmap_ok:", d.get("production_result",{}).get("fr_trade_heatmap_ok"))
  print("heatmap_err:", d.get("production_result",{}).get("fr_trade_heatmap_error"))
  print("aggregate:", d.get("production_result",{}).get("aggregate"))
  print("vnstock:", d.get("runtime",{}).get("vnstock_version"), "has_fr=", d.get("runtime",{}).get("has_fr_trade_heatmap"))
PY
```

Interpret:

| Result | Meaning |
| --- | --- |
| `provider_reachable=YES` / verdict `P0_FOREIGN_FLOW_FORWARD_ONLY_READY` | SSI works on VPS; still FORWARD_ONLY (no date param); **do not deploy yet** — report only |
| HTTP 403 / verdict `P0_FOREIGN_PROVIDER_BLOCKED` | Provider blocked on VPS |
| Script/curl failure | Tooling issue — still not provider failure |

**Do not** merge #85–#89 or restart services to complete this probe.

---

## 4. Fallback if GitHub raw is blocked on VPS

Paste/scp the standalone file from a laptop, or:

```bash
# from a machine that can reach GitHub, then scp:
scp /tmp/standalone_ssi_foreign_flow_probe.py user@VPS:/tmp/
```

---

## 5. `mrbot-daily-research.service` inactive after run

**Yes — normal.** Unit is `Type=oneshot` with `Restart=no`.

After a successful (or finished) timer/manual run, systemd shows the service as **inactive (dead)**. That does **not** mean the timer is broken.

Read-only checks:

```bash
systemctl cat mrbot-daily-research.service | sed -n '1,25p'
systemctl status mrbot-daily-research.service --no-pager || true
systemctl status mrbot-daily-research.timer --no-pager || true
systemctl list-timers 'mrbot-daily-research*' --no-pager || true
```

Expect `Type=oneshot` in the unit; `inactive` after SUCCESS is expected.

---

## 6. Explicitly out of scope for this step

- No `git pull` / checkout of research branches onto production
- No merge of #85–#89
- No changes to Market First / Forecast / Edge / Camera
- No timer/service enablement changes
- No foreign-flow backfill
- No Cloudflare bypass

#!/usr/bin/env bash
# READ-ONLY forensic coverage audit for one trade_date (default 2026-08-26).
# Does NOT write/modify production artifacts. Run on VPS:
#   bash scripts/audit_eod_coverage_readonly.sh 2026-08-26
set -euo pipefail
REPO="${MRBOT_REPO:-/opt/mrbot-camera}"
TD="${1:-2026-08-26}"
cd "${REPO}"
python3 - <<PY
from pathlib import Path
import json
import pandas as pd

repo = Path("${REPO}")
td = "${TD}"
wl = None
try:
    from modules.scanner_core import WATCHLIST
    wl = set(str(s).upper() for s in WATCHLIST)
except Exception as e:
    print("watchlist_import_error", e)

ems_p = repo / "data" / "earning_money_snapshots.csv"
md_p = repo / "data" / "earning_learning" / "market_daily_t0.csv"
obs_p = repo / "data" / "earning_learning" / "observations.csv"
fr_p = repo / "data" / "earning_learning" / "t0_observation_freeze.csv"
t0_p = repo / "data" / "forecast_research" / "forecast_t0_daily.csv"
p0_p = repo / "data" / "forecast_research" / "p0_market_daily.csv"
auto_p = repo / "data" / "forecast_research" / "headless_eod_status.json"
rec_p = repo / "data" / "forecast_research" / "headless_eod_recovery_status.json"
hist_p = repo / "data" / "forecast_research" / "headless_eod_run_history.jsonl"
rec_dir = repo / "data" / "forecast_research" / "recovery_runs"

report = {"trade_date": td, "expected_universe": 142 if wl is None else len(wl)}

def load(p):
    if not p.exists():
        return None
    return pd.read_csv(p, low_memory=False)

ems = load(ems_p)
if ems is None or ems.empty:
    report["ems"] = {"exists": False}
else:
    day = ems[ems["snapshot_date"].astype(str).str[:10] == td]
    syms = day["symbol"].astype(str).str.upper().drop_duplicates() if not day.empty else pd.Series(dtype=str)
    missing = sorted(wl - set(syms)) if wl else []
    extra = sorted(set(syms) - wl) if wl else []
    report["ems"] = {
        "exists": True,
        "rows": int(len(day)),
        "unique_symbols": int(len(syms)),
        "missing_vs_watchlist": missing,
        "extra_vs_watchlist": extra,
        "saved_at_max": str(day["saved_at"].max()) if "saved_at" in day.columns and len(day) else None,
    }

md = load(md_p)
if md is None:
    report["mdt0"] = {"exists": False}
else:
    hit = md[md["trade_date"].astype(str).str[:10] == td]
    report["mdt0"] = {
        "exists": True,
        "rows": int(len(hit)),
        "tail": hit.tail(1).to_dict(orient="records"),
    }

for name, p, col in [
    ("observations", obs_p, "trade_date"),
    ("t0_freeze", fr_p, "trade_date"),
]:
    df = load(p)
    if df is None:
        report[name] = {"exists": False}
        continue
    hit = df[df[col].astype(str).str[:10] == td]
    report[name] = {
        "exists": True,
        "rows": int(len(hit)),
        "unique_symbols": int(hit["symbol"].astype(str).nunique()) if "symbol" in hit.columns and len(hit) else 0,
    }

t0 = load(t0_p)
if t0 is None:
    report["forecast_t0"] = {"exists": False}
else:
    hit = t0[t0["trade_date"].astype(str).str[:10] == td]
    report["forecast_t0"] = {
        "exists": True,
        "rows": int(len(hit)),
        "tail": hit.tail(1)[[c for c in hit.columns if c in (
            "trade_date","universe_count","completeness_status","market_real","market_live","market_forecast","created_at","snapshot_asof"
        )]].to_dict(orient="records") if len(hit) else [],
    }

p0 = load(p0_p)
if p0 is None:
    report["p0"] = {"exists": False}
else:
    hit = p0[p0["trade_date"].astype(str).str[:10] == td] if "trade_date" in p0.columns else p0.iloc[0:0]
    report["p0"] = {"exists": True, "rows": int(len(hit))}

for label, p in [("autonomy_status", auto_p), ("recovery_status", rec_p)]:
    report[label] = {"exists": p.exists(), "path": str(p)}
    if p.exists():
        try:
            report[label]["payload"] = json.loads(p.read_text())
        except Exception as e:
            report[label]["error"] = str(e)

report["recovery_runs"] = sorted([x.name for x in rec_dir.glob("*.json")]) if rec_dir.exists() else []
report["history_exists"] = hist_p.exists()
if hist_p.exists():
    lines = hist_p.read_text().strip().splitlines()
    report["history_tail"] = [json.loads(x) for x in lines[-5:]]

print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
PY

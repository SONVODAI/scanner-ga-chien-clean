"""Staged canonical HSX foreign-flow historical backfill (research store only)."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from modules.foreign_flow_history.hsx_client import (
    DEFAULT_PACING_SEC,
    DEFAULT_PAGE_SIZE,
    FetchResult,
    fetch_symbol_pages,
)
from modules.foreign_flow_history.parse import parse_payload_to_rows
from modules.foreign_flow_history.schema import DEFAULT_DATA_ROOT, SCHEMA_VERSION, SOURCE_NAME
from modules.foreign_flow_history.store import (
    append_raw_pages,
    ensure_dirs,
    list_completed_symbols,
    load_checkpoint,
    manifests_dir,
    read_symbol_canonical,
    resolve_root,
    save_checkpoint,
    symbol_coverage_summary,
    utc_now_iso,
    write_symbol_canonical,
)
from modules.foreign_flow_history.validate import price_outcome_readiness, validate_canonical_df

DEFAULT_ELIGIBILITY = Path("diagnostics/foreign_flow_historical_audit/ems142_hsx_eligibility.json")
DEFAULT_DIAG_DIR = Path("diagnostics/foreign_flow_canonical_backfill")

# Diverse Stage A pilot (long-listed + newer + mid)
STAGE_A_PILOT = ["VNM", "HPG", "FPT", "MWG", "NAB", "SSI", "DIG"]


def load_eligibility(path: Path = DEFAULT_ELIGIBILITY) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "hose_eligible": [str(s).upper() for s in data.get("hose_eligible") or []],
        "hsx_empty": [str(s).upper() for s in data.get("hsx_empty") or []],
        "trade_date": data.get("trade_date"),
        "n_ems": data.get("n_ems"),
        "source_path": str(path),
    }


def stage_symbols(stage: str, eligibility: Dict[str, Any]) -> List[str]:
    stage = stage.upper()
    hose = list(eligibility["hose_eligible"])
    if stage == "A":
        # Prefer pilot symbols that are in eligibility; keep order, skip missing
        out = [s for s in STAGE_A_PILOT if s in set(hose)]
        # If eligibility missing symbols unexpectedly, still allow anchors
        for s in STAGE_A_PILOT:
            if s not in out:
                out.append(s)
        return out
    if stage == "B":
        return sorted(hose)
    if stage == "C":
        # Broader HOSE not reconstructed safely — Stage C = Stage B only unless extended list provided
        return sorted(hose)
    raise ValueError(f"unknown stage {stage}")


def _mark_checkpoint(
    checkpoint: Dict[str, Any],
    symbol: str,
    *,
    status: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    symbols = checkpoint.setdefault("symbols", {})
    entry = dict(symbols.get(symbol) or {})
    entry.update(meta or {})
    entry["status"] = status
    entry["updated_at"] = utc_now_iso()
    symbols[symbol] = entry


def backfill_symbol(
    symbol: str,
    *,
    root: Path,
    checkpoint: Dict[str, Any],
    pacing_sec: float = DEFAULT_PACING_SEC,
    page_size: int = DEFAULT_PAGE_SIZE,
    skip_completed: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    sym = str(symbol).strip().upper()
    existing_meta = (checkpoint.get("symbols") or {}).get(sym) or {}
    if skip_completed and existing_meta.get("status") == "completed":
        cov = symbol_coverage_summary(sym, root)
        return {
            "symbol": sym,
            "status": "skipped_completed",
            "n_rows": cov.get("n_rows", 0),
            "coverage": cov,
        }

    if dry_run:
        return {"symbol": sym, "status": "dry_run"}

    t0 = time.time()
    fetch: FetchResult = fetch_symbol_pages(
        sym,
        page_size=page_size,
        pacing_sec=pacing_sec,
        prefer_full_page=True,
    )

    if fetch.stopped_reason == "rate_limited":
        _mark_checkpoint(
            checkpoint,
            sym,
            status="rate_limited",
            meta={"errors": fetch.errors, "mode": fetch.mode},
        )
        save_checkpoint(checkpoint, root)
        return {
            "symbol": sym,
            "status": "rate_limited",
            "errors": fetch.errors,
            "elapsed_sec": round(time.time() - t0, 3),
        }

    if fetch.stopped_reason == "transient_error" and not fetch.pages:
        _mark_checkpoint(
            checkpoint,
            sym,
            status="failed",
            meta={"errors": fetch.errors, "stopped_reason": fetch.stopped_reason},
        )
        save_checkpoint(checkpoint, root)
        return {
            "symbol": sym,
            "status": "failed",
            "errors": fetch.errors,
            "elapsed_sec": round(time.time() - t0, 3),
        }

    fetched_at = utc_now_iso()
    if fetch.pages:
        append_raw_pages(sym, fetch.pages, root=root, fetched_at=fetched_at)

    rows: List[Dict[str, Any]] = []
    for page in fetch.pages:
        rows.extend(parse_payload_to_rows(page, symbol=sym, fetched_at=fetched_at))

    # Dedup within fetch by natural key (first wins)
    seen = set()
    deduped = []
    for r in rows:
        k = (r["trade_date"], r["symbol"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    rows = deduped

    if not rows:
        # Empty may be legitimate non-HOSE — mark completed_empty
        status = "completed_empty"
        _mark_checkpoint(
            checkpoint,
            sym,
            status=status,
            meta={
                "n_rows": 0,
                "fetch_mode": fetch.mode,
                "stopped_reason": fetch.stopped_reason,
                "errors": fetch.errors,
            },
        )
        save_checkpoint(checkpoint, root)
        return {
            "symbol": sym,
            "status": status,
            "n_rows": 0,
            "elapsed_sec": round(time.time() - t0, 3),
        }

    ok, write_status, n_after = write_symbol_canonical(sym, rows, root=root, backup=True)
    if not ok:
        _mark_checkpoint(
            checkpoint,
            sym,
            status="write_failed",
            meta={"write_status": write_status, "n_incoming": len(rows)},
        )
        save_checkpoint(checkpoint, root)
        return {
            "symbol": sym,
            "status": "write_failed",
            "write_status": write_status,
            "n_incoming": len(rows),
            "elapsed_sec": round(time.time() - t0, 3),
        }

    df = read_symbol_canonical(sym, root)
    validation = validate_canonical_df(df)
    readiness = price_outcome_readiness(df)
    cov = symbol_coverage_summary(sym, root)

    status = "completed" if validation.get("ok") else "completed_with_anomalies"
    _mark_checkpoint(
        checkpoint,
        sym,
        status=status,
        meta={
            "n_rows": n_after,
            "first_trade_date": cov.get("first_trade_date"),
            "last_trade_date": cov.get("last_trade_date"),
            "sha256": cov.get("sha256"),
            "fetch_mode": fetch.mode,
            "page_count": fetch.page_count,
            "raw_row_count": fetch.raw_row_count,
            "stopped_reason": fetch.stopped_reason,
            "validation_ok": bool(validation.get("ok")),
            "issue_codes": [i.get("code") for i in validation.get("issues") or []],
            "outcome_readiness": readiness.get("ready"),
        },
    )
    save_checkpoint(checkpoint, root)

    return {
        "symbol": sym,
        "status": status,
        "n_rows": n_after,
        "coverage": cov,
        "validation": validation,
        "outcome_readiness": readiness,
        "fetch": {
            "mode": fetch.mode,
            "page_count": fetch.page_count,
            "raw_row_count": fetch.raw_row_count,
            "stopped_reason": fetch.stopped_reason,
            "errors": fetch.errors,
        },
        "elapsed_sec": round(time.time() - t0, 3),
    }


def run_stage(
    stage: str,
    *,
    root: Path,
    eligibility_path: Path = DEFAULT_ELIGIBILITY,
    pacing_sec: float = DEFAULT_PACING_SEC,
    page_size: int = DEFAULT_PAGE_SIZE,
    skip_completed: bool = True,
    stop_on_rate_limit: bool = True,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    ensure_dirs(root)
    eligibility = load_eligibility(eligibility_path)
    symbols = stage_symbols(stage, eligibility)
    if limit is not None:
        symbols = symbols[: int(limit)]

    checkpoint = load_checkpoint(root)
    checkpoint["stage"] = stage.upper()
    checkpoint["eligibility_source"] = eligibility["source_path"]
    checkpoint["excluded_hnx_upcom"] = eligibility["hsx_empty"]

    results: List[Dict[str, Any]] = []
    rate_limited = False

    for i, sym in enumerate(symbols):
        if i > 0 and pacing_sec > 0:
            time.sleep(pacing_sec)
        print(f"[{stage}:{i+1}/{len(symbols)}] {sym} ...", flush=True)
        res = backfill_symbol(
            sym,
            root=root,
            checkpoint=checkpoint,
            pacing_sec=pacing_sec,
            page_size=page_size,
            skip_completed=skip_completed,
        )
        results.append(res)
        print(
            f"  -> {res.get('status')} rows={res.get('n_rows')} "
            f"elapsed={res.get('elapsed_sec')}s",
            flush=True,
        )
        if res.get("status") == "rate_limited":
            rate_limited = True
            if stop_on_rate_limit:
                print("STOP: provider rate limited; progress preserved.", flush=True)
                break

    summary = summarize_run(stage, symbols, results, eligibility, root, rate_limited=rate_limited)
    out_path = manifests_dir(root) / f"stage_{stage.upper()}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary


def summarize_run(
    stage: str,
    attempted: Sequence[str],
    results: Sequence[Dict[str, Any]],
    eligibility: Dict[str, Any],
    root: Path,
    *,
    rate_limited: bool,
) -> Dict[str, Any]:
    completed = [r for r in results if str(r.get("status", "")).startswith("completed")]
    failed = [
        r
        for r in results
        if r.get("status") in ("failed", "write_failed", "rate_limited")
    ]
    skipped = [r for r in results if r.get("status") == "skipped_completed"]

    # Aggregate from disk for all completed symbols in root
    all_completed = list_completed_symbols(root)
    # Also include completed_with_anomalies / completed_empty from checkpoint
    cp = load_checkpoint(root)
    session_counts = []
    firsts = []
    lasts = []
    total_rows = 0
    integrity_failures = []
    for sym, meta in (cp.get("symbols") or {}).items():
        st = meta.get("status")
        if st not in ("completed", "completed_with_anomalies"):
            continue
        n = int(meta.get("n_rows") or 0)
        total_rows += n
        if n:
            session_counts.append(n)
        if meta.get("first_trade_date"):
            firsts.append(meta["first_trade_date"])
        if meta.get("last_trade_date"):
            lasts.append(meta["last_trade_date"])
        if st == "completed_with_anomalies":
            integrity_failures.append({"symbol": sym, "codes": meta.get("issue_codes")})

    hose = set(eligibility["hose_eligible"])
    completed_syms = {
        s
        for s, m in (cp.get("symbols") or {}).items()
        if str(m.get("status", "")).startswith("completed")
    } | set(all_completed)
    covered_hose = sorted(hose & completed_syms)

    disk_bytes = 0
    can_dir = resolve_root(root) / "canonical" / "by_symbol"
    if can_dir.exists():
        for p in can_dir.glob("*.csv"):
            disk_bytes += p.stat().st_size
    raw_d = resolve_root(root) / "raw"
    if raw_d.exists():
        for p in raw_d.glob("*.jsonl"):
            disk_bytes += p.stat().st_size

    return {
        "stage": stage.upper(),
        "created_at": utc_now_iso(),
        "symbols_attempted": list(attempted),
        "n_attempted": len(attempted),
        "n_completed_this_run": len(completed) + len(skipped),
        "n_failed_this_run": len(failed),
        "results": results,
        "rate_limited": rate_limited,
        "aggregate": {
            "symbols_completed_on_disk": sorted(
                {
                    s
                    for s, m in (cp.get("symbols") or {}).items()
                    if str(m.get("status", "")).startswith("completed")
                }
            ),
            "total_rows": total_rows,
            "earliest_date": min(firsts) if firsts else None,
            "latest_date": max(lasts) if lasts else None,
            "median_sessions_per_symbol": (
                float(statistics.median(session_counts)) if session_counts else None
            ),
            "max_sessions_per_symbol": max(session_counts) if session_counts else None,
            "current_ems_hose_coverage": {
                "n_eligible": len(hose),
                "n_completed": len(covered_hose),
                "symbols": covered_hose,
            },
            "excluded_hnx_upcom": eligibility["hsx_empty"],
            "integrity_failures": integrity_failures,
            "disk_footprint_bytes": disk_bytes,
        },
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "data_root": str(resolve_root(root)),
    }


def build_research_freeze(root: Path, eligibility_path: Path = DEFAULT_ELIGIBILITY) -> Dict[str, Any]:
    eligibility = load_eligibility(eligibility_path)
    cp = load_checkpoint(root)
    per_symbol = []
    hashes = {}
    total_rows = 0
    firsts, lasts = [], []
    for sym, meta in sorted((cp.get("symbols") or {}).items()):
        if not str(meta.get("status", "")).startswith("completed"):
            continue
        if meta.get("status") == "completed_empty":
            continue
        cov = symbol_coverage_summary(sym, root)
        per_symbol.append(cov)
        if cov.get("sha256"):
            hashes[sym] = cov["sha256"]
        total_rows += int(cov.get("n_rows") or 0)
        if cov.get("first_trade_date"):
            firsts.append(cov["first_trade_date"])
        if cov.get("last_trade_date"):
            lasts.append(cov["last_trade_date"])

    dataset_version = f"{SCHEMA_VERSION}_{utc_now_iso().replace(':', '').replace('-', '')}"
    freeze = {
        "dataset_version": dataset_version,
        "schema_version": SCHEMA_VERSION,
        "creation_timestamp": utc_now_iso(),
        "source": SOURCE_NAME,
        "grain": "trade_date x symbol",
        "symbol_count": len(per_symbol),
        "row_count": total_rows,
        "first_trade_date": min(firsts) if firsts else None,
        "last_trade_date": max(lasts) if lasts else None,
        "per_symbol_coverage": per_symbol,
        "hashes": hashes,
        "exclusions": {
            "current_ems_hnx_upcom": eligibility["hsx_empty"],
            "reason": "HSX foreign endpoint returns empty for non-HOSE; not fabricated",
        },
        "known_biases": [
            "Current EMS HOSE overlap (117) is a present-day relevance set, not historical membership-as-of.",
            "Long-listed names have deeper history than recent listings (listing-age bias).",
            "No complete historical HOSE membership reconstruction claimed.",
            "Market-context / ADV overlap much shorter than foreign-flow history.",
            "Raw OHLC; corporate-action adjustment status unknown.",
        ],
        "provenance": {
            "endpoint": "https://api.hsx.vn/mk/api/v1/market/securities/foreign/{SYM}",
            "eligibility_manifest": eligibility["source_path"],
            "eligibility_asof": eligibility.get("trade_date"),
            "checkpoint": str(manifests_dir(root) / "backfill_checkpoint.json"),
            "data_root": str(resolve_root(root)),
        },
        "no_propositions": True,
        "no_winning_conditions": True,
        "no_outcome_labels_in_store": True,
    }
    path = manifests_dir(root) / "research_freeze.json"
    path.write_text(json.dumps(freeze, indent=2, default=str) + "\n", encoding="utf-8")
    return freeze


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Canonical HSX foreign-flow historical backfill")
    p.add_argument("--stage", choices=["A", "B", "C", "freeze"], required=True)
    p.add_argument("--root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--eligibility", default=str(DEFAULT_ELIGIBILITY))
    p.add_argument("--pacing-sec", type=float, default=DEFAULT_PACING_SEC)
    p.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-skip-completed", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    root = Path(args.root)
    ensure_dirs(root)

    if args.stage == "freeze":
        freeze = build_research_freeze(root, Path(args.eligibility))
        print(json.dumps({"freeze": freeze["dataset_version"], "symbols": freeze["symbol_count"]}, indent=2))
        return 0

    summary = run_stage(
        args.stage,
        root=root,
        eligibility_path=Path(args.eligibility),
        pacing_sec=args.pacing_sec,
        page_size=args.page_size,
        skip_completed=not args.no_skip_completed,
        limit=args.limit,
    )
    print(json.dumps({k: summary[k] for k in summary if k != "results"}, indent=2, default=str))
    if summary.get("rate_limited"):
        return 2
    if summary.get("n_failed_this_run", 0) > 0 and summary.get("n_completed_this_run", 0) == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

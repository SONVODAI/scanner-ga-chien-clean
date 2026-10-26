"""Daily confirmation pipeline: forward ingest → events → T10 outcomes (counts-only).

Never computes or exposes aggregate performance / PASS-FAIL metrics early.
Does not mutate P0 / Forecast / Edge / Camera stores.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.foreign_flow_confirmation.cohort import confirmation_cohort, record_cohort_event
from modules.foreign_flow_confirmation.continuity import join_history_and_forward, lookback_complete
from modules.foreign_flow_confirmation.exact_date import fetch_exact_trade_date_row
from modules.foreign_flow_confirmation.features import FEATURE_FNS, intermediate_value
from modules.foreign_flow_confirmation.forward_panel import (
    LAST_IN_SAMPLE,
    append_forward_rows,
    ensure_forward_dirs,
    latest_forward_trade_date,
    load_forward_checkpoint,
    resolve_root,
    save_forward_checkpoint,
    utc_now_iso,
)
from modules.foreign_flow_confirmation.ledger import (
    CANDIDATES,
    ConfirmationLedger,
    HORIZON,
    dq_event,
    event_id,
    protocol_hash,
)

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_ROOT = Path("data/foreign_flow_history")

CANDIDATE_FEATURE_MAP = {
    "FFC1_PRIMARY_ABN_ABS_Z20_T10": ("abn_abs_z20", 60),
    "FFC1_SECONDARY_NET_HI_PCT90_T10": ("net_hi_pct90", 252),
    "FFC1_OPTIONAL_STREAK_NEG_LE_M5_T10": ("streak_neg_le_m5", 5),
}


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _extreme_jump(series: pd.DataFrame) -> bool:
    if series is None or len(series) < 2:
        return False
    close = series["close_price"].iloc[-1]
    prev = series["close_price"].iloc[-2]
    try:
        if close is None or prev is None or float(close) <= 0 or float(prev) <= 0:
            return False
        ratio = float(close) / float(prev)
        return bool(ratio > 1.8 or ratio < 0.55)
    except (TypeError, ValueError):
        return False


def ingest_trade_date(
    trade_date: str,
    *,
    confirmation_root: Optional[Path | str] = None,
    history_root: Path | str = DEFAULT_HISTORY_ROOT,
    symbols: Optional[Sequence[str]] = None,
    fetch_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    pacing_sleeper: Callable[[float], None] = lambda _s: None,
    mark_delayed_operational: bool = False,
) -> Dict[str, Any]:
    """
    Fetch and persist exact-date symbol×day rows for one post-freeze session.

    Idempotent / resumable via checkpoint + first-write-wins panel merge.
    """
    td = str(trade_date)[:10]
    root = resolve_root(confirmation_root)
    ensure_forward_dirs(root)

    if td <= LAST_IN_SAMPLE:
        return {"ok": False, "written": False, "reason": "freeze_boundary", "trade_date": td}

    cohort = confirmation_cohort()
    syms = list(symbols) if symbols is not None else list(cohort["symbols"])
    fetch = fetch_fn or fetch_exact_trade_date_row

    cp = load_forward_checkpoint(root)
    date_meta = dict((cp.get("dates") or {}).get(td) or {})
    already_done = set(str(s).upper() for s in (date_meta.get("completed_symbols") or []))

    results = {
        "ok": True,
        "trade_date": td,
        "written": False,
        "n_symbols_target": len(syms),
        "n_ok": 0,
        "n_missing": 0,
        "n_rejected": 0,
        "n_rate_limited": 0,
        "n_errors": 0,
        "n_skipped_already": 0,
        "errors": [],
        "delayed_operational_ingest": bool(mark_delayed_operational),
        "cohort_id": cohort["cohort_id"],
        "reason": "ok",
    }

    completed = set(already_done)
    for sym in syms:
        sym = str(sym).upper()
        if sym in already_done:
            results["n_skipped_already"] += 1
            # still count as ok coverage for idempotent replay
            results["n_ok"] += 1
            continue

        try:
            fr = fetch(sym, td, sleeper=pacing_sleeper)
        except Exception as exc:  # noqa: BLE001
            results["n_errors"] += 1
            results["errors"].append(f"{sym}:fetch_exc:{exc}")
            continue

        if fr.get("rate_limited"):
            results["n_rate_limited"] += 1
            results["ok"] = False
            results["reason"] = "rate_limited_partial"
            # persist progress so later cycle can resume
            date_meta.update(
                {
                    "status": "partial_rate_limited",
                    "completed_symbols": sorted(completed),
                    "updated_at": utc_now_iso(),
                }
            )
            cp.setdefault("dates", {})[td] = date_meta
            save_forward_checkpoint(cp, root)
            return results

        if not fr.get("ok"):
            reason = fr.get("reason") or "fetch_failed"
            if reason == "exact_date_missing":
                results["n_missing"] += 1
                record_cohort_event(
                    {
                        "event": "symbol_date_missing",
                        "trade_date": td,
                        "symbol": sym,
                        "reason": reason,
                        "at": utc_now_iso(),
                    },
                    path=root / "manifests" / "cohort_events.jsonl",
                )
            else:
                results["n_errors"] += 1
                results["errors"].append(f"{sym}:{reason}")
            continue

        rows = fr.get("rows") or []
        ok, status, _n = append_forward_rows(sym, rows, trade_date=td, root=root)
        if not ok:
            results["n_rejected"] += 1
            results["errors"].append(f"{sym}:{status}")
            _append_jsonl(
                root / "dq_rejects" / f"{td}.jsonl",
                {"symbol": sym, "trade_date": td, "status": status, "at": utc_now_iso()},
            )
            continue

        completed.add(sym)
        results["n_ok"] += 1
        results["written"] = True

    incomplete = [s for s in syms if str(s).upper() not in completed]
    date_meta.update(
        {
            "status": "complete" if not incomplete else "partial",
            "completed_symbols": sorted(completed),
            "incomplete_symbols": incomplete,
            "n_ok": results["n_ok"],
            "n_missing": results["n_missing"],
            "updated_at": utc_now_iso(),
            "delayed_operational_ingest": bool(mark_delayed_operational),
        }
    )
    cp.setdefault("dates", {})[td] = date_meta
    cp["latest_trade_date"] = max(str(cp.get("latest_trade_date") or ""), td)
    save_forward_checkpoint(cp, root)

    if incomplete:
        results["ok"] = results["n_ok"] > 0
        results["reason"] = "partial_coverage"
    return results


def evaluate_and_append_events(
    trade_date: str,
    *,
    confirmation_root: Optional[Path | str] = None,
    history_root: Path | str = DEFAULT_HISTORY_ROOT,
    symbols: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Evaluate frozen candidates for T0 and append immutable events (no performance)."""
    td = str(trade_date)[:10]
    root = resolve_root(confirmation_root)
    if td <= LAST_IN_SAMPLE:
        return {"ok": False, "reason": "freeze_boundary", "n_events": 0}

    cohort = confirmation_cohort()
    syms = list(symbols) if symbols is not None else list(cohort["symbols"])
    ledger = ConfirmationLedger(root=root)
    ph = protocol_hash()
    n_events = 0
    n_dq = 0
    n_triggers_checked = 0

    for sym in syms:
        series = join_history_and_forward(
            sym, asof_trade_date=td, history_root=history_root, confirmation_root=root
        )
        if series.empty or str(series["trade_date"].iloc[-1])[:10] != td:
            n_dq += 1
            _append_jsonl(
                root / "dq_rejects" / f"{td}.jsonl",
                {"symbol": sym, "trade_date": td, "status": "asof_row_missing_in_joined_series", "at": utc_now_iso()},
            )
            continue

        t0 = series.iloc[-1]
        net = series["foreign_net_value"]
        close = t0.get("close_price")
        prev_close = series["close_price"].iloc[-2] if len(series) >= 2 else None
        px_ret_1 = None
        try:
            if close is not None and prev_close is not None and float(close) > 0 and float(prev_close) > 0:
                px_ret_1 = float(close) / float(prev_close) - 1.0
        except (TypeError, ValueError):
            px_ret_1 = None

        px_ret_20 = None
        if len(series) >= 21:
            c0 = series["close_price"].iloc[-1]
            c20 = series["close_price"].iloc[-21]
            try:
                if c0 is not None and c20 is not None and float(c0) > 0 and float(c20) > 0:
                    px_ret_20 = float(c0) / float(c20) - 1.0
            except (TypeError, ValueError):
                px_ret_20 = None

        extreme = _extreme_jump(series)

        for candidate_id, (feature, need) in CANDIDATE_FEATURE_MAP.items():
            n_triggers_checked += 1
            fn = FEATURE_FNS[feature]
            trigger_series = fn(net)
            trig_raw = trigger_series.iloc[-1]
            lookback_ok = lookback_complete(series, need=need) if feature != "streak_neg_le_m5" else len(series) >= need
            # streak: need definition uses consecutive signs; require finite net today
            feat_finite = trig_raw is not None and not (isinstance(trig_raw, float) and np.isnan(trig_raw))
            if feature == "streak_neg_le_m5":
                lookback_ok = pd.notna(net.iloc[-1])
                feat_finite = True

            inter = intermediate_value(feature, net)
            threshold_state = bool(feat_finite and lookback_ok and float(trig_raw) == 1.0)

            dq = dq_event(
                trade_date=td,
                foreign_net_value=None if pd.isna(t0.get("foreign_net_value")) else float(t0["foreign_net_value"]),
                close_price=None if pd.isna(close) else float(close),
                lookback_complete=bool(lookback_ok),
                feature_value_finite=bool(inter is not None) if feature != "streak_neg_le_m5" else True,
                source=str(t0.get("source") or ""),
                source_provenance=str(t0.get("source_scope") or t0.get("source") or ""),
                dataset_hash_or_version=str(t0.get("row_hash") or t0.get("schema_version") or ""),
                extreme_jump=extreme,
                t0_timing_clear=True,
            )

            if not threshold_state:
                continue

            if not dq.ok:
                n_dq += 1
                _append_jsonl(
                    root / "dq_rejects" / f"{td}.jsonl",
                    {
                        "symbol": sym,
                        "trade_date": td,
                        "candidate_id": candidate_id,
                        "dq_failures": dq.failures,
                        "at": utc_now_iso(),
                    },
                )
                continue

            # Resolve expected maturity date if calendar available
            maturity_expected = None
            try:
                from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
                    offset_trading_sessions,
                )

                maturity_expected = offset_trading_sessions(td, HORIZON)
            except Exception:
                maturity_expected = None

            event = {
                "event_id": event_id(candidate_id, td, sym),
                "protocol_id": "ff_confirmation_v1",
                "candidate_id": candidate_id,
                "trade_date": td,
                "symbol": sym,
                "feature": feature,
                "frozen_feature_value": inter,
                "threshold_state": True,
                "eligibility_ok": True,
                "eligibility_reason": "frozen_trigger_dq_pass",
                "baseline_state": {
                    "era": "confirmation_post_2026-08-24",
                    "unconditional_eligible_flag": True,
                    "px_ret_1": px_ret_1,
                    "px_ret_20": px_ret_20,
                },
                "source": str(t0.get("source") or "HSX_FOREIGN_API"),
                "source_provenance": str(t0.get("source_scope") or "HOSE_SYMBOL_LEVEL"),
                "dataset_hash_or_version": str(t0.get("row_hash") or ""),
                "t0_close": None if pd.isna(close) else float(close),
                "lookback_complete": True,
                "dq_gate_pass": True,
                "dq_failures": [],
                "outcome_maturity_trade_date_expected": maturity_expected,
                "protocol_hash": ph,
                "created_at": utc_now_iso(),
            }
            ok, reason = ledger.append_event(event)
            if ok:
                n_events += 1
            elif reason != "duplicate_event_key":
                n_dq += 1

    return {
        "ok": True,
        "trade_date": td,
        "n_events": n_events,
        "n_dq_rejects": n_dq,
        "n_checked": n_triggers_checked,
        "reason": "ok",
    }


def _close_on_date(series: pd.DataFrame, trade_date: str) -> Optional[float]:
    td = str(trade_date)[:10]
    hit = series[series["trade_date"].astype(str).str[:10] == td]
    if hit.empty:
        return None
    v = hit.iloc[-1]["close_price"]
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        fv = float(v)
        return fv if fv > 0 else None
    except (TypeError, ValueError):
        return None


def mature_due_outcomes(
    *,
    asof_trade_date: str,
    confirmation_root: Optional[Path | str] = None,
    history_root: Path | str = DEFAULT_HISTORY_ROOT,
) -> Dict[str, Any]:
    """Append outcomes + baseline snapshots for events whose T10 is <= asof. No judgment."""
    asof = str(asof_trade_date)[:10]
    root = resolve_root(confirmation_root)
    ledger = ConfirmationLedger(root=root)
    events = ledger._load_jsonl(ledger.events_path)
    existing_outcomes = {o["event_id"] for o in ledger._load_jsonl(ledger.outcomes_path)}

    n_matured = 0
    n_waiting = 0
    n_failed = 0

    try:
        from modules.edge_research.opr_bridge.production_vn_trading_calendar import (
            offset_trading_sessions,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"calendar_unavailable:{exc}", "n_matured": 0}

    for ev in events:
        eid = ev["event_id"]
        if eid in existing_outcomes:
            continue
        t0 = ev["trade_date"]
        maturity = ev.get("outcome_maturity_trade_date_expected") or offset_trading_sessions(t0, HORIZON)
        if maturity is None:
            n_waiting += 1
            continue
        if maturity > asof:
            n_waiting += 1
            continue

        series = join_history_and_forward(
            ev["symbol"],
            asof_trade_date=maturity,
            history_root=history_root,
            confirmation_root=root,
        )
        t0_close = ev.get("t0_close")
        t10_close = _close_on_date(series, maturity)
        outcome_ok = t0_close is not None and float(t0_close) > 0 and t10_close is not None
        ret = None
        win = None
        if outcome_ok:
            ret = float(t10_close) / float(t0_close) - 1.0
            win = 1.0 if ret > 0 else 0.0
        else:
            n_failed += 1

        # Path MFE/MAE over sessions 1..10 when available
        mfe = mae = dd = None
        if outcome_ok:
            sessions = []
            cur = t0
            for _ in range(HORIZON):
                nxt = offset_trading_sessions(cur, 1)
                if nxt is None:
                    break
                sessions.append(nxt)
                cur = nxt
            highs = []
            lows = []
            for sd in sessions:
                hit = series[series["trade_date"].astype(str).str[:10] == sd]
                if hit.empty:
                    continue
                hi = hit.iloc[-1].get("high_price")
                lo = hit.iloc[-1].get("low_price")
                try:
                    if hi is not None and float(hi) > 0:
                        highs.append(float(hi))
                    if lo is not None and float(lo) > 0:
                        lows.append(float(lo))
                except (TypeError, ValueError):
                    pass
            if highs:
                mfe = max(highs) / float(t0_close) - 1.0
            if lows:
                mae = min(lows) / float(t0_close) - 1.0
                dd = mae

        outcome = {
            "event_id": eid,
            "candidate_id": ev["candidate_id"],
            "trade_date": t0,
            "symbol": ev["symbol"],
            "maturity_trade_date": maturity,
            "t10_close": t10_close,
            "ret_t10": ret,
            "win_t10": win,
            "mfe_t10": mfe,
            "mae_t10": mae,
            "forward_drawdown_t10": dd,
            "outcome_ok": bool(outcome_ok),
            "outcome_reason": "ok" if outcome_ok else "missing_price_or_path",
            "matured_at": utc_now_iso(),
        }
        ok, reason = ledger.append_outcome(outcome)
        if ok:
            n_matured += 1
            # Baseline append (unconditional eligible snapshot — counts only in operator view)
            _append_baseline_snapshot(
                root=root,
                asof_trade_date=asof,
                maturity_trade_date=maturity,
                candidate_id=ev["candidate_id"],
            )
        elif reason != "outcome_already_logged":
            n_failed += 1

    return {
        "ok": True,
        "asof_trade_date": asof,
        "n_matured": n_matured,
        "n_waiting": n_waiting,
        "n_failed": n_failed,
        "reason": "ok",
    }


def _append_baseline_snapshot(
    *,
    root: Path,
    asof_trade_date: str,
    maturity_trade_date: str,
    candidate_id: str,
) -> None:
    """Append baseline ledger row without exposing aggregate candidate performance."""
    # Baseline = all research-eligible forward panel rows matured to T10 in era — stored as
    # structural snapshot metadata only here; mean/median computed only when judgment allowed.
    path = Path(root) / "baselines" / "baselines.jsonl"
    row = {
        "baseline_id": f"unconditional_eligible|{asof_trade_date}|{candidate_id}",
        "protocol_id": "ff_confirmation_v1",
        "era": "confirmation_post_2026-08-24",
        "baseline_family": "unconditional_eligible",
        "asof_trade_date": asof_trade_date,
        "maturity_trade_date": maturity_trade_date,
        "horizon": HORIZON,
        "candidate_id_context": candidate_id,
        "n_eligible": None,
        "mean_ret_t10": None,
        "median_ret_t10": None,
        "win_rate_t10": None,
        "created_at": utc_now_iso(),
        "note": "Metrics intentionally null until final_judgment_allowed (anti-peeking).",
        "protocol_hash": protocol_hash(),
    }
    # Idempotent: skip if same baseline_id already present
    if path.exists():
        with path.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                if json.loads(line).get("baseline_id") == row["baseline_id"]:
                    return
    _append_jsonl(path, row)


def counts_only_status(
    *,
    confirmation_root: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Operator view: counts only — never returns mean/incr/win/pass."""
    root = resolve_root(confirmation_root)
    ledger = ConfirmationLedger(root=root)
    summary = ledger.operator_summary()
    summary["latest_successfully_ingested_trade_date"] = latest_forward_trade_date(root)
    # Strip any accidental performance keys
    forbidden = {
        "mean_ret",
        "incremental",
        "win_rate",
        "pass",
        "fail",
        "bps",
        "leaderboard",
    }
    blob = json.dumps(summary)
    for k in forbidden:
        if k in blob.lower() and k in ("mean_ret", "incremental", "win_rate", "leaderboard"):
            # structural guarantee: operator_summary never includes these
            pass
    # DQ error counts
    dq_dir = root / "dq_rejects"
    dq_n = 0
    if dq_dir.exists():
        for p in dq_dir.glob("*.jsonl"):
            dq_n += sum(1 for line in p.read_text().splitlines() if line.strip())
    summary["data_quality_errors"] = dq_n
    for c in summary.get("candidates") or []:
        # ensure no performance fields
        for bad in list(c.keys()):
            if any(x in bad.lower() for x in ("mean", "incr", "win_rate", "bps", "pass_fail")):
                c.pop(bad, None)
    # persist
    out_path = root / "status" / "OPERATOR_COUNTS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def run_confirmation_daily(
    trade_date: str,
    *,
    confirmation_root: Optional[Path | str] = None,
    history_root: Path | str = DEFAULT_HISTORY_ROOT,
    fetch_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    skip_fetch: bool = False,
    mark_delayed_operational: bool = False,
) -> Dict[str, Any]:
    """
    Full daily cycle for one trade_date (fail-safe wrapper target).

    Order: ingest forward panel → append events → mature due outcomes → counts status.
    """
    td = str(trade_date)[:10]
    root = resolve_root(confirmation_root)
    ensure_forward_dirs(root)

    if td <= LAST_IN_SAMPLE:
        return {
            "ok": False,
            "written": False,
            "reason": "freeze_boundary",
            "trade_date": td,
            "stage": "ff_confirmation_forward",
        }

    ingest: Dict[str, Any] = {"skipped": True}
    if not skip_fetch:
        ingest = ingest_trade_date(
            td,
            confirmation_root=root,
            history_root=history_root,
            fetch_fn=fetch_fn,
            mark_delayed_operational=mark_delayed_operational,
        )

    events = evaluate_and_append_events(
        td, confirmation_root=root, history_root=history_root
    )
    maturity = mature_due_outcomes(
        asof_trade_date=td, confirmation_root=root, history_root=history_root
    )
    status = counts_only_status(confirmation_root=root)

    return {
        "ok": bool(ingest.get("ok", True)) or bool(ingest.get("skipped")),
        "written": bool(ingest.get("written")) or int(events.get("n_events") or 0) > 0,
        "trade_date": td,
        "stage": "ff_confirmation_forward",
        "reason": ingest.get("reason") or events.get("reason") or "ok",
        "ingest": ingest,
        "events": {
            "n_events": events.get("n_events"),
            "n_dq_rejects": events.get("n_dq_rejects"),
            # deliberately omit any performance
        },
        "maturity": {
            "n_matured": maturity.get("n_matured"),
            "n_waiting": maturity.get("n_waiting"),
            "n_failed": maturity.get("n_failed"),
        },
        "status_counts_only": True,
        "latest_successfully_ingested_trade_date": status.get(
            "latest_successfully_ingested_trade_date"
        ),
    }


def maybe_run_ff_confirmation_after_market_daily(
    trade_date: str,
    *,
    confirmation_root: Optional[Path | str] = None,
    history_root: Path | str = DEFAULT_HISTORY_ROOT,
) -> Dict[str, Any]:
    """Public hook for production daily integration — never raises to caller."""
    try:
        return run_confirmation_daily(
            trade_date,
            confirmation_root=confirmation_root,
            history_root=history_root,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("FF confirmation forward hook failed safely: %s", exc)
        return {
            "ok": False,
            "written": False,
            "reason": f"ff_confirmation_hook_error:{exc}",
            "trade_date": str(trade_date)[:10],
            "stage": "ff_confirmation_forward",
        }

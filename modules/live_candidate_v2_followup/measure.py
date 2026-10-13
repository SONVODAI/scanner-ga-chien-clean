"""Immutable Follow-up Watch measurement ledger (arms A/B/C).

Append-only JSONL. Keeps wins, losses, WAIT, EXPIRED, Guardian rejects.
T3/T5/T10 matured later from trading-session prices + VNIndex excess.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from modules.live_candidate_v2_followup.contract import (
    ARM_BASELINE,
    ARM_FOLLOWUP,
    ARM_FOLLOWUP_GUARDIAN,
    ENV_FOLLOWUP_DIR,
    HORIZONS,
    LEDGER_NAME,
    REMOTE_DIR,
    SCHEMA_LEDGER,
    STATUS_BUY_READY,
    STATUS_EXPIRED,
    STATUS_REJECTED,
    STATUS_WAIT,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def measure_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_FOLLOWUP_DIR, "").strip()
    if raw:
        return Path(raw)
    return REPO_ROOT / REMOTE_DIR


def ledger_path(directory: Path | None = None) -> Path:
    return measure_dir(directory) / LEDGER_NAME


def _append_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False, default=str) + "\n")
            added += 1
    return added


def load_ledger(directory: Path | None = None) -> list[dict[str, Any]]:
    path = ledger_path(directory)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _base_row(
    *,
    arm: str,
    session: str,
    candidate: Mapping[str, Any],
    result: Mapping[str, Any],
    status_override: str | None = None,
    reason_override: str | None = None,
    action_state_override: str | None = None,
) -> dict[str, Any]:
    status = status_override if status_override is not None else (
        result.get("status") or candidate.get("status")
    )
    reason = reason_override if reason_override is not None else (result.get("reason") or "")
    action_state = (
        action_state_override
        if action_state_override is not None
        else (result.get("action_state") or "")
    )
    return {
        "schema": SCHEMA_LEDGER,
        "arm": arm,
        "recorded_at": _utc_now(),
        "session": str(session)[:10],
        "candidate_key": candidate.get("candidate_key"),
        "symbol": candidate.get("symbol"),
        "source": candidate.get("source"),
        "original_session": candidate.get("original_session"),
        "first_seen": candidate.get("first_seen"),
        "first_seen_price": candidate.get("first_seen_price"),
        "original_setup": candidate.get("original_setup"),
        "current_setup": candidate.get("current_setup"),
        "status": status,
        "reason": reason,
        "action_state": action_state,
        "market_real": candidate.get("market_real"),
        "market_permission": candidate.get("market_permission"),
        "guardian_status": candidate.get("guardian_status"),
        "candidate_quality": result.get("candidate_quality")
        or candidate.get("candidate_quality")
        or "",
        "candidate_quality_reason": result.get("candidate_quality_reason")
        or candidate.get("candidate_quality_reason")
        or "",
        "guardian_filtered": bool(result.get("guardian_filtered")),
        "candidate_guardian_filtered": bool(result.get("candidate_guardian_filtered")),
        "position_guardian_sell": bool(result.get("position_guardian_sell")),
        "sessions_elapsed": candidate.get("sessions_elapsed"),
        "buy_ready_session": candidate.get("buy_ready_session"),
        "buy_ready_at": candidate.get("buy_ready_at"),
        "buy_ready_price": candidate.get("buy_ready_price"),
        "reject_session": candidate.get("last_evaluated_session")
        if status == STATUS_REJECTED
        else "",
        "reject_price": candidate.get("prior_quality_snapshot", {}).get("price")
        if isinstance(candidate.get("prior_quality_snapshot"), Mapping)
        else None,
        "t3_return_pct": None,
        "t5_return_pct": None,
        "t10_return_pct": None,
        "t3_excess_vnindex_pct": None,
        "t5_excess_vnindex_pct": None,
        "t10_excess_vnindex_pct": None,
        "t3_max_drawdown_pct": None,
        "t5_max_drawdown_pct": None,
        "t10_max_drawdown_pct": None,
        "outcome_matured_at": None,
    }


def _ledger_fingerprint(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("arm") or ""),
        str(row.get("session") or "")[:10],
        str(row.get("candidate_key") or ""),
        str(row.get("status") or ""),
        str(row.get("reason") or ""),
        str(row.get("record_kind") or ""),
    )


def append_ledger_rows(
    *,
    session: str,
    registry: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    ingested: Sequence[str],
    directory: Path | None = None,
) -> int:
    """Write arm B/C rows for this session. Arm A is recorded separately.

    Arm B uses ``status_b`` / ``reason_b`` (Follow-up without Candidate Guardian).
    Arm C uses registry path status (Follow-up + Candidate Guardian).
    Restart/retry safe: skips fingerprints already present for the session.
    """
    candidates = registry.get("candidates") or {}
    existing = {
        _ledger_fingerprint(r)
        for r in load_ledger(directory)
        if str(r.get("session") or "")[:10] == str(session)[:10]
    }
    rows: list[dict[str, Any]] = []

    def _maybe(row: dict[str, Any]) -> None:
        fp = _ledger_fingerprint(row)
        if fp in existing:
            return
        existing.add(fp)
        rows.append(row)

    for result in results:
        if result.get("idempotent_skip"):
            continue
        key = str(result.get("candidate_key") or "")
        cand = candidates.get(key) or {}
        if not cand:
            continue
        status_c = str(result.get("status") or "")
        status_b = str(result.get("status_b") or status_c)
        reason_b = str(result.get("reason_b") or result.get("reason") or "")
        action_b = str(result.get("action_state_b") or result.get("action_state") or "")
        # Arm B: follow-up path without Candidate Guardian gates.
        if status_b in {STATUS_WAIT, STATUS_BUY_READY, STATUS_EXPIRED, STATUS_REJECTED}:
            _maybe(
                _base_row(
                    arm=ARM_FOLLOWUP,
                    session=session,
                    candidate=cand,
                    result=result,
                    status_override=status_b,
                    reason_override=reason_b,
                    action_state_override=action_b,
                )
            )
        # Arm C: Follow-up + Candidate Guardian.
        if status_c in {STATUS_WAIT, STATUS_BUY_READY, STATUS_EXPIRED, STATUS_REJECTED}:
            _maybe(
                _base_row(
                    arm=ARM_FOLLOWUP_GUARDIAN,
                    session=session,
                    candidate=cand,
                    result=result,
                )
            )
    # Ingest markers (still WAIT / ACTIVE start) for opportunity counting.
    for key in ingested:
        cand = candidates.get(key) or {}
        if not cand:
            continue
        _maybe(
            _base_row(
                arm=ARM_FOLLOWUP,
                session=session,
                candidate=cand,
                result={"status": STATUS_WAIT, "reason": "INGESTED", "action_state": ""},
            )
        )
        _maybe(
            _base_row(
                arm=ARM_FOLLOWUP_GUARDIAN,
                session=session,
                candidate=cand,
                result={"status": STATUS_WAIT, "reason": "INGESTED", "action_state": ""},
            )
        )
    return _append_jsonl(ledger_path(directory), rows)


def record_baseline_action_rows(
    *,
    session: str,
    action_rows: Sequence[Mapping[str, Any]] | None,
    directory: Path | None = None,
) -> int:
    """Arm A — snapshot of current V2 Action outcomes (research only)."""
    rows: list[dict[str, Any]] = []
    for raw in action_rows or ():
        if not isinstance(raw, Mapping):
            continue
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        fake_cand = {
            "candidate_key": f"{symbol}|baseline|{str(session)[:10]}",
            "symbol": symbol,
            "source": raw.get("nomination_source") or raw.get("source") or "",
            "original_session": str(raw.get("session") or session)[:10],
            "first_seen": raw.get("candidate_first_seen_ts"),
            "first_seen_price": raw.get("price_at_first_seen"),
            "original_setup": raw.get("setup") or raw.get("group") or "",
            "current_setup": raw.get("setup") or raw.get("group") or "",
            "market_real": raw.get("market_real"),
            "market_permission": raw.get("market_permission"),
            "guardian_status": "",
            "sessions_elapsed": 1,
            "buy_ready_session": str(session)[:10]
            if str(raw.get("shadow_action") or raw.get("action_state") or "") == "BUY_READY"
            else "",
            "buy_ready_at": raw.get("first_met_at") or raw.get("trigger_bar_ts"),
            "buy_ready_price": raw.get("price_at_first_met") or raw.get("trigger_price"),
        }
        rows.append(
            _base_row(
                arm=ARM_BASELINE,
                session=session,
                candidate=fake_cand,
                result={
                    "status": str(raw.get("shadow_action") or raw.get("action_state") or ""),
                    "reason": str(raw.get("action_reason") or ""),
                    "action_state": str(raw.get("shadow_action") or raw.get("action_state") or ""),
                },
            )
        )
    return _append_jsonl(ledger_path(directory), rows)


def _return_and_dd(
    entry: float,
    path_prices: Sequence[float],
) -> tuple[float | None, float | None]:
    if not path_prices or entry <= 0:
        return None, None
    last = float(path_prices[-1])
    ret = (last / entry - 1.0) * 100.0
    min_px = min(path_prices)
    dd = (min_px / entry - 1.0) * 100.0
    return ret, dd


def _entry_anchor(row: Mapping[str, Any]) -> tuple[str, float | None]:
    """Session + price used as T0 for outcome maturation.

    BUY_READY → buy_ready_session / buy_ready_price
    REJECTED / EXPIRED → reject/eval session / reject_price or first_seen_price
    (measures false rejects / expired opportunity cost).
    """
    status = str(row.get("status") or "")
    if status == STATUS_BUY_READY:
        session = str(row.get("buy_ready_session") or row.get("session") or "")[:10]
        entry = row.get("buy_ready_price")
    else:
        session = str(
            row.get("reject_session") or row.get("session") or row.get("original_session") or ""
        )[:10]
        entry = row.get("reject_price")
        if entry is None:
            entry = row.get("first_seen_price")
    try:
        entry_f = float(entry) if entry is not None else None
    except (TypeError, ValueError):
        entry_f = None
    return session, entry_f


def mature_buy_ready_outcomes(
    *,
    directory: Path | None = None,
    symbol_session_prices: Mapping[str, Mapping[str, float]] | None = None,
    vnindex_session_prices: Mapping[str, float] | None = None,
    trading_dates: Sequence[str] | None = None,
    as_of_session: str | None = None,
) -> dict[str, Any]:
    """Fill T3/T5/T10 (+ excess vs VNIndex) on terminal research rows.

    Matures BUY_READY, REJECTED, and EXPIRED so false rejects are measurable.
    ``as_of_session`` forbids using prices / trading dates after that day
    (no future peek into decision-time T).
    Appends NEW matured lines (never rewrites prior JSONL rows).
    """
    dates = [str(d)[:10] for d in (trading_dates or [])]
    dates = sorted(set(dates))
    as_of = str(as_of_session or "")[:10]
    if as_of:
        dates = [d for d in dates if d <= as_of]
    sym_px = symbol_session_prices or {}
    vni_px = vnindex_session_prices or {}
    existing = load_ledger(directory)
    matured: list[dict[str, Any]] = []
    mature_statuses = {STATUS_BUY_READY, STATUS_REJECTED, STATUS_EXPIRED}
    # Dedup: skip if a matured line already exists for same arm+key+status+anchor.
    already = {
        (
            str(r.get("arm") or ""),
            str(r.get("candidate_key") or ""),
            str(r.get("status") or ""),
            str(r.get("outcome_anchor_session") or r.get("session") or "")[:10],
        )
        for r in existing
        if r.get("record_kind") == "OUTCOME_MATURED" or r.get("outcome_matured_at")
    }

    for row in existing:
        status = str(row.get("status") or "")
        if status not in mature_statuses:
            continue
        if row.get("record_kind") == "OUTCOME_MATURED":
            continue
        if row.get("outcome_matured_at"):
            continue
        if row.get("t3_return_pct") is not None:
            continue
        symbol = str(row.get("symbol") or "").upper()
        anchor_session, entry_f = _entry_anchor(row)
        if not symbol or not anchor_session or entry_f is None or entry_f <= 0:
            continue
        if as_of and anchor_session > as_of:
            continue
        if anchor_session not in dates:
            continue
        dedup_key = (
            str(row.get("arm") or ""),
            str(row.get("candidate_key") or ""),
            status,
            anchor_session,
        )
        if dedup_key in already:
            continue
        idx = dates.index(anchor_session)
        path = sym_px.get(symbol) or {}
        # As-of filter on price path: ignore future session keys.
        if as_of:
            path = {d: px for d, px in path.items() if str(d)[:10] <= as_of}
        vni_entry = vni_px.get(anchor_session)
        new_row = dict(row)
        filled_any = False
        for horizon in HORIZONS:
            # Skip horizons already filled on a prior partial mature line.
            if new_row.get(f"t{horizon}_return_pct") is not None:
                filled_any = True
                continue
            target_idx = idx + horizon
            if target_idx >= len(dates):
                continue
            target_day = dates[target_idx]
            if as_of and target_day > as_of:
                continue
            window = dates[idx + 1 : target_idx + 1]
            prices = [float(path[d]) for d in window if d in path]
            if len(prices) < horizon:
                continue
            ret, dd = _return_and_dd(entry_f, prices)
            new_row[f"t{horizon}_return_pct"] = ret
            new_row[f"t{horizon}_max_drawdown_pct"] = dd
            if vni_entry and vni_entry > 0 and target_day in vni_px:
                vni_ret = (float(vni_px[target_day]) / float(vni_entry) - 1.0) * 100.0
                new_row[f"t{horizon}_excess_vnindex_pct"] = (
                    None if ret is None else float(ret) - vni_ret
                )
            filled_any = True
        # Require at least T3 before emitting a matured research line.
        if new_row.get("t3_return_pct") is None or not filled_any:
            continue
        new_row["outcome_matured_at"] = _utc_now()
        new_row["record_kind"] = "OUTCOME_MATURED"
        new_row["outcome_anchor_session"] = anchor_session
        new_row["outcome_anchor_price"] = entry_f
        new_row["as_of_session"] = as_of or None
        matured.append(new_row)
        already.add(dedup_key)

    added = _append_jsonl(ledger_path(directory), matured)
    return {"ok": True, "matured": added, "scanned": len(existing), "as_of_session": as_of or None}


def summarize_arms(directory: Path | None = None) -> dict[str, Any]:
    """Aggregate win rate / mean / median / excess / extras for reporting."""
    import statistics

    rows = load_ledger(directory)
    summary: dict[str, Any] = {}
    for arm in (ARM_BASELINE, ARM_FOLLOWUP, ARM_FOLLOWUP_GUARDIAN):
        arm_rows = [r for r in rows if r.get("arm") == arm]
        buy = [r for r in arm_rows if r.get("status") == STATUS_BUY_READY]
        waits = [r for r in arm_rows if r.get("status") == STATUS_WAIT]
        expired = [r for r in arm_rows if r.get("status") == STATUS_EXPIRED]
        rejected = [r for r in arm_rows if r.get("status") == STATUS_REJECTED]
        guardian_kills = [
            r
            for r in arm_rows
            if r.get("guardian_filtered") or r.get("candidate_guardian_filtered")
        ]
        rejected_matured = [
            r
            for r in rejected
            if r.get("t5_return_pct") is not None
        ]
        matured = [r for r in buy if r.get("t5_return_pct") is not None]
        def _stats(values: list[float]) -> dict[str, float | None]:
            if not values:
                return {"n": 0, "win_rate": None, "mean": None, "median": None}
            wins = sum(1 for v in values if v > 0)
            return {
                "n": len(values),
                "win_rate": wins / len(values) * 100.0,
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
            }

        t5 = [float(r["t5_return_pct"]) for r in matured if r.get("t5_return_pct") is not None]
        t5x = [
            float(r["t5_excess_vnindex_pct"])
            for r in matured
            if r.get("t5_excess_vnindex_pct") is not None
        ]
        dd = [
            float(r["t5_max_drawdown_pct"])
            for r in matured
            if r.get("t5_max_drawdown_pct") is not None
        ]
        rej_t5 = [
            float(r["t5_return_pct"])
            for r in rejected_matured
            if r.get("t5_return_pct") is not None
        ]
        summary[arm] = {
            "n_rows": len(arm_rows),
            "n_buy_ready": len(buy),
            "n_wait": len(waits),
            "n_expired": len(expired),
            "n_rejected": len(rejected),
            "n_guardian_filtered": len(guardian_kills),
            "t5": _stats(t5),
            "t5_excess_vnindex": _stats(t5x),
            "t5_max_drawdown_mean": statistics.fmean(dd) if dd else None,
            "rejected_t5": _stats(rej_t5),
        }
    return summary


__all__ = [
    "append_ledger_rows",
    "ledger_path",
    "load_ledger",
    "mature_buy_ready_outcomes",
    "measure_dir",
    "record_baseline_action_rows",
    "summarize_arms",
]

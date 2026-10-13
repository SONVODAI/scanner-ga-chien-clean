"""Per-session Follow-up Watch ingest + re-evaluation.

Rules:
- Never inherit WAIT / BUY rights / old setup into a new evaluation episode.
- Re-read Setup, Market First, Candidate Guardian, and WHEN from current inputs.
- Empty setup or weak market → continue ACTIVE wait (no BUY_READY).
- Market Real < 6 blocks BUY via Market Permission only — never rejects.
- Position Guardian SELL is soft evidence only; Candidate Guardian decides reject.
- Candidate Guardian WEAKENING blocks BUY_READY in the arm-C research path.
- STRONGER continues WAIT until fresh WHEN + Setup + Market Permission.
- TTL inclusive of original_session, max 5 VNIndex sessions → EXPIRED.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from modules.live_candidate.calendar import as_vn, session_open_at
from modules.live_candidate_v2_action.contract import (
    STATE_BUY_READY,
    STATE_WAIT,
)
from modules.live_candidate_v2_action.live_universe import ACTIONABLE_LIVE_SETUPS
from modules.live_candidate_v2_action.state import (
    evaluate_shadow_action,
    nomination_from_mapping,
)
from modules.live_candidate_v2_followup.candidate_guardian import (
    QUALITY_REJECTED,
    QUALITY_STRONGER,
    QUALITY_WEAKENING,
    classify_candidate_quality,
    snapshot_from_scan,
)
from modules.live_candidate_v2_followup.contract import (
    ALLOWED_SOURCES,
    FOLLOWUP_ALERT_ELIGIBLE,
    FOLLOWUP_CANDIDATE_IS_BUY,
    FOLLOWUP_PXV_IMPLIES_BUY,
    MODE,
    REASON_BUY_READY,
    REASON_CANDIDATE_GUARDIAN_REJECT,
    REASON_CANDIDATE_WEAKENING_BLOCK,
    REASON_FLAG_OFF,
    REASON_GUARDIAN_SELL,
    REASON_INGESTED,
    REASON_MARKET_NOT_OK,
    REASON_QUALITY_STRONGER_WAIT,
    REASON_SETUP_EMPTY,
    REASON_TTL_EXPIRED,
    REASON_WHEN_NOT_MET,
    SCHEMA_SESSION,
    SLICE,
    SRC_FOLLOWUP,
    STATUS_ACTIVE,
    STATUS_BUY_READY,
    STATUS_EXPIRED,
    STATUS_REJECTED,
    STATUS_WAIT,
    TTL_SESSIONS_INCLUSIVE,
    followup_enabled,
)
from modules.live_candidate_v2_followup.guardian_bridge import is_guardian_sell
from modules.live_candidate_v2_followup.measure import append_ledger_rows
from modules.live_candidate_v2_followup.registry import (
    active_candidates,
    append_status_history,
    load_registry,
    save_registry,
    upsert_candidate,
)
from modules.live_candidate_v2_nomination.predicate import market_permission

ActionEvaluator = Callable[..., Any]


def normalize_trading_dates(dates: Sequence[object] | None) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in dates or ():
        text = str(raw or "").strip()[:10]
        if len(text) != 10 or text[4] != "-" or text[7] != "-":
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    out.sort()
    return tuple(out)


def sessions_elapsed_inclusive(
    original_session: str,
    current_session: str,
    trading_dates: Sequence[str],
) -> int | None:
    """Count VNIndex sessions from original through current, inclusive."""
    dates = normalize_trading_dates(trading_dates)
    start = str(original_session or "")[:10]
    end = str(current_session or "")[:10]
    if not start or not end or end < start:
        return None
    window = [d for d in dates if start <= d <= end]
    if start not in window or end not in window:
        # Fail closed: if calendar incomplete, estimate by membership gaps.
        if start == end:
            return 1
        return None
    return len(window)


def _setup_of(row: Mapping[str, Any]) -> str:
    return str(row.get("setup") or row.get("group") or "").strip()


def _source_of(row: Mapping[str, Any]) -> str:
    return str(row.get("nomination_source") or row.get("source") or "").strip()


def _num(value: object) -> float | None:
    try:
        if value is None:
            return None
        n = float(value)
        if n != n:  # NaN
            return None
        return n
    except (TypeError, ValueError):
        return None


def ingest_sidecar_rows(
    registry: dict[str, Any],
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    session: str,
) -> list[str]:
    """Register new Brain A / Sweet B nominations that are not yet BUY_READY."""
    ingested: list[str] = []
    for raw in rows or ():
        if not isinstance(raw, Mapping):
            continue
        symbol = str(raw.get("symbol") or "").strip().upper()
        source = _source_of(raw)
        if not symbol or source not in ALLOWED_SOURCES:
            continue
        state = str(raw.get("shadow_action") or raw.get("action_state") or "").strip()
        if state == STATE_BUY_READY:
            continue
        original_session = str(raw.get("session") or session)[:10]
        first_seen = str(raw.get("candidate_first_seen_ts") or "")
        key = upsert_candidate(
            registry,
            symbol=symbol,
            source=source,
            original_session=original_session,
            fields={
                "first_seen": first_seen,
                "original_setup": _setup_of(raw),
                "current_setup": _setup_of(raw),
                "first_seen_price": _num(raw.get("price_at_first_seen")),
                "frozen_ema9": _num(raw.get("ema9_at_first_seen")),
                "frozen_breakout_ref": _num(raw.get("breakout_ref_at_first_seen")),
                "observation_reference": str(raw.get("observation_reference") or ""),
                "last_evaluated_session": "",
                "status": STATUS_ACTIVE,
                "expiry_session": "",
                "rejection_reason": "",
                "market_real": _num(raw.get("market_real")),
                "market_permission": str(raw.get("market_permission") or ""),
                "guardian_status": "",
                "candidate_quality": "",
                "candidate_quality_reason": "",
                "weakening_streak": 0,
                "prior_quality_snapshot": {},
                "candidate_is_buy": FOLLOWUP_CANDIDATE_IS_BUY,
                "pxv_implies_buy": FOLLOWUP_PXV_IMPLIES_BUY,
                "alert_eligible": FOLLOWUP_ALERT_ELIGIBLE,
                "mode": MODE,
                "slice": SLICE,
            },
        )
        cand = registry["candidates"][key]
        if not any(
            h.get("reason") == REASON_INGESTED for h in (cand.get("status_history") or [])
        ):
            append_status_history(
                cand,
                session=original_session,
                status=STATUS_ACTIVE,
                reason=REASON_INGESTED,
            )
            ingested.append(key)
    return ingested


def _scan_setup(scan_row: Mapping[str, Any] | None) -> str:
    if not scan_row:
        return ""
    return str(scan_row.get("group") or scan_row.get("setup") or "").strip()


def _fresh_nomination_dict(
    candidate: Mapping[str, Any],
    *,
    session: str,
    current_setup: str,
    scan_row: Mapping[str, Any] | None,
    market_real: object,
    observed_at: datetime,
) -> dict[str, Any]:
    """Build a NEW evaluation nomination. Does not reuse prior WAIT state."""
    now = as_vn(observed_at)
    day = now.date()
    elig = session_open_at(day).isoformat()
    first = str(candidate.get("first_seen") or now.isoformat())
    # Fresh refs from today's scan when present; otherwise leave empty so
    # Action fails closed rather than reusing a stale buy right.
    ema9 = _num(scan_row.get("ema9")) if scan_row else None
    brk = _num(scan_row.get("breakout_ref")) if scan_row else None
    price = _num(scan_row.get("price")) if scan_row else None
    perm = market_permission(market_real)
    return {
        "symbol": candidate.get("symbol"),
        "session": str(session)[:10],
        "setup": current_setup,
        "group": current_setup,
        "candidate_first_seen_ts": first,
        "eligible_from": elig,
        "candidate_updated_ts": now.isoformat(),
        "price_at_first_seen": price if price is not None else candidate.get("first_seen_price"),
        "ema9_at_first_seen": ema9,
        "breakout_ref_at_first_seen": brk,
        "observation_reference": "EMA9" if current_setup != "MUA BREAK" else "BREAKOUT",
        "nomination_source": SRC_FOLLOWUP,
        "source": SRC_FOLLOWUP,
        "source_action": "FOLLOWUP_REEVAL",
        "origin_setup": candidate.get("original_setup") or "",
        "origin_group": candidate.get("original_setup") or "",
        "origin_ema9": candidate.get("frozen_ema9"),
        "origin_breakout_ref": candidate.get("frozen_breakout_ref"),
        "market_real": _num(market_real),
        "market_permission": perm,
        "followup_parent_key": candidate.get("candidate_key"),
        "followup_parent_source": candidate.get("source"),
        "followup_original_session": candidate.get("original_session"),
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
    }


def _action_eval(
    candidate: Mapping[str, Any],
    *,
    session: str,
    current_setup: str,
    scan_row: Mapping[str, Any] | None,
    market_real: object,
    observed_at: datetime,
    legal_bars: Sequence[Any],
    evaluate: ActionEvaluator,
) -> tuple[str, Any, dict[str, Any] | None]:
    """Fresh Action WHEN evaluation. Returns (action_state, result, camera_row)."""
    fresh = _fresh_nomination_dict(
        candidate,
        session=session,
        current_setup=current_setup,
        scan_row=scan_row,
        market_real=market_real,
        observed_at=observed_at,
    )
    result = evaluate(
        nomination_from_mapping(fresh),
        legal_bars,
        now=as_vn(observed_at),
        observed=True,
        prior_action_state=None,
        prior_session=None,
    )
    action_state = str(getattr(result, "action_state", "") or "") or STATE_WAIT
    return action_state, result, fresh


def _path_without_guardian(
    *,
    current_setup: str,
    perm: str,
    candidate: Mapping[str, Any],
    session: str,
    scan_row: Mapping[str, Any] | None,
    market_real: object,
    observed_at: datetime,
    legal_bars: Sequence[Any],
    evaluate: ActionEvaluator,
) -> dict[str, Any]:
    """Arm B counterfactual: Follow-up Watch without Candidate Guardian gates."""
    if current_setup not in ACTIONABLE_LIVE_SETUPS:
        reason = REASON_SETUP_EMPTY if not current_setup else REASON_WHEN_NOT_MET
        return {
            "status": STATUS_WAIT,
            "reason": reason,
            "action_state": STATE_WAIT,
            "camera_row": None,
            "action_result": None,
        }
    if perm != "OK":
        return {
            "status": STATUS_WAIT,
            "reason": REASON_MARKET_NOT_OK,
            "action_state": STATE_WAIT,
            "camera_row": None,
            "action_result": None,
        }
    action_state, result, fresh = _action_eval(
        candidate,
        session=session,
        current_setup=current_setup,
        scan_row=scan_row,
        market_real=market_real,
        observed_at=observed_at,
        legal_bars=legal_bars,
        evaluate=evaluate,
    )
    if action_state == STATE_BUY_READY:
        return {
            "status": STATUS_BUY_READY,
            "reason": REASON_BUY_READY,
            "action_state": STATE_BUY_READY,
            "camera_row": fresh,
            "action_result": result,
        }
    return {
        "status": STATUS_WAIT,
        "reason": REASON_WHEN_NOT_MET,
        "action_state": action_state or STATE_WAIT,
        "camera_row": fresh,
        "action_result": result,
    }


def evaluate_active_candidate(
    candidate: dict[str, Any],
    *,
    session: str,
    trading_dates: Sequence[str],
    scan_row: Mapping[str, Any] | None,
    market_real: object,
    guardian_signal: str,
    observed_at: datetime,
    legal_bars: Sequence[Any] = (),
    evaluate: ActionEvaluator | None = None,
) -> dict[str, Any]:
    """Re-evaluate one ACTIVE candidate for the current session.

    Registry / camera follow arm C (Follow-up + Candidate Guardian).
    ``status_b`` / ``reason_b`` record the arm-B counterfactual without CG gates.
    Position Guardian SELL is recorded but never hard-rejects.
    """
    eval_fn = evaluate or evaluate_shadow_action
    current_setup = _scan_setup(scan_row)
    candidate["current_setup"] = current_setup
    candidate["last_evaluated_session"] = str(session)[:10]
    candidate["market_real"] = _num(market_real)
    perm = market_permission(market_real)
    candidate["market_permission"] = perm
    candidate["guardian_status"] = str(guardian_signal or "")
    position_guardian_sell = is_guardian_sell(guardian_signal)

    elapsed = sessions_elapsed_inclusive(
        str(candidate.get("original_session") or ""),
        session,
        trading_dates,
    )
    candidate["sessions_elapsed"] = elapsed
    if elapsed is not None and elapsed > TTL_SESSIONS_INCLUSIVE:
        candidate["status"] = STATUS_EXPIRED
        candidate["expiry_session"] = str(session)[:10]
        candidate["rejection_reason"] = REASON_TTL_EXPIRED
        append_status_history(
            candidate,
            session=session,
            status=STATUS_EXPIRED,
            reason=REASON_TTL_EXPIRED,
            extra={"sessions_elapsed": elapsed},
        )
        return {
            "candidate_key": candidate.get("candidate_key"),
            "status": STATUS_EXPIRED,
            "reason": REASON_TTL_EXPIRED,
            "status_b": STATUS_EXPIRED,
            "reason_b": REASON_TTL_EXPIRED,
            "camera_row": None,
            "action_state": "",
            "candidate_quality": "",
            "position_guardian_sell": position_guardian_sell,
        }

    prior_snap = candidate.get("prior_quality_snapshot")
    if not isinstance(prior_snap, Mapping):
        prior_snap = None
    streak = int(candidate.get("weakening_streak") or 0)
    quality = classify_candidate_quality(
        scan_row,
        original_setup=str(candidate.get("original_setup") or ""),
        prior_snapshot=prior_snap,
        weakening_streak=streak,
        market_real=market_real,
    )
    candidate["candidate_quality"] = quality.label
    candidate["candidate_quality_reason"] = quality.reason
    candidate["prior_quality_snapshot"] = snapshot_from_scan(scan_row)
    if quality.label == QUALITY_WEAKENING:
        candidate["weakening_streak"] = streak + 1
    elif quality.label == QUALITY_REJECTED:
        candidate["weakening_streak"] = streak + 1
    else:
        candidate["weakening_streak"] = 0

    # Arm B counterfactual (no Candidate Guardian reject / weakening block).
    path_b = _path_without_guardian(
        current_setup=current_setup,
        perm=perm,
        candidate=candidate,
        session=session,
        scan_row=scan_row,
        market_real=market_real,
        observed_at=observed_at,
        legal_bars=legal_bars,
        evaluate=eval_fn,
    )

    soft_pg = {
        "position_guardian_sell": position_guardian_sell,
        "position_guardian_signal": str(guardian_signal or ""),
        "position_guardian_note": REASON_GUARDIAN_SELL if position_guardian_sell else "",
        "candidate_quality": quality.as_dict(),
    }

    # --- Arm C: Candidate Guardian hard reject ---
    if quality.reject or quality.label == QUALITY_REJECTED:
        candidate["status"] = STATUS_REJECTED
        candidate["rejection_reason"] = REASON_CANDIDATE_GUARDIAN_REJECT
        candidate["rejection_detail"] = quality.reason
        append_status_history(
            candidate,
            session=session,
            status=STATUS_REJECTED,
            reason=REASON_CANDIDATE_GUARDIAN_REJECT,
            extra={
                "quality_reason": quality.reason,
                "quality_label": quality.label,
                **soft_pg,
            },
        )
        return {
            "candidate_key": candidate.get("candidate_key"),
            "status": STATUS_REJECTED,
            "reason": REASON_CANDIDATE_GUARDIAN_REJECT,
            "status_b": path_b["status"],
            "reason_b": path_b["reason"],
            "camera_row": None,
            "action_state": "",
            "action_state_b": path_b.get("action_state") or "",
            "candidate_quality": quality.label,
            "candidate_quality_reason": quality.reason,
            "guardian_filtered": True,
            "candidate_guardian_filtered": True,
            "position_guardian_sell": position_guardian_sell,
            "action_result_b": path_b.get("action_result"),
        }

    # --- Empty / non-actionable setup: continue wait (both arms) ---
    if current_setup not in ACTIONABLE_LIVE_SETUPS:
        reason = REASON_SETUP_EMPTY if not current_setup else REASON_WHEN_NOT_MET
        candidate["status"] = STATUS_ACTIVE
        append_status_history(
            candidate,
            session=session,
            status=STATUS_WAIT,
            reason=reason,
            extra={"current_setup": current_setup, **soft_pg},
        )
        return {
            "candidate_key": candidate.get("candidate_key"),
            "status": STATUS_WAIT,
            "reason": reason,
            "status_b": STATUS_WAIT,
            "reason_b": reason,
            "camera_row": None,
            "action_state": STATE_WAIT,
            "candidate_quality": quality.label,
            "candidate_quality_reason": quality.reason,
            "position_guardian_sell": position_guardian_sell,
        }

    # --- Market First: block BUY only; never reject healthy candidates ---
    if perm != "OK":
        candidate["status"] = STATUS_ACTIVE
        append_status_history(
            candidate,
            session=session,
            status=STATUS_WAIT,
            reason=REASON_MARKET_NOT_OK,
            extra={"market_permission": perm, **soft_pg},
        )
        return {
            "candidate_key": candidate.get("candidate_key"),
            "status": STATUS_WAIT,
            "reason": REASON_MARKET_NOT_OK,
            "status_b": STATUS_WAIT,
            "reason_b": REASON_MARKET_NOT_OK,
            "camera_row": None,
            "action_state": STATE_WAIT,
            "candidate_quality": quality.label,
            "candidate_quality_reason": quality.reason,
            "position_guardian_sell": position_guardian_sell,
        }

    # --- WEAKENING: arm C blocks BUY_READY; arm B may still reach BUY_READY ---
    if quality.block_buy_ready or quality.label == QUALITY_WEAKENING:
        candidate["status"] = STATUS_ACTIVE
        append_status_history(
            candidate,
            session=session,
            status=STATUS_WAIT,
            reason=REASON_CANDIDATE_WEAKENING_BLOCK,
            extra={
                "action_state_raw": path_b.get("action_state") or "",
                "quality_reason": quality.reason,
                **soft_pg,
            },
        )
        return {
            "candidate_key": candidate.get("candidate_key"),
            "status": STATUS_WAIT,
            "reason": REASON_CANDIDATE_WEAKENING_BLOCK,
            "status_b": path_b["status"],
            "reason_b": path_b["reason"],
            "camera_row": path_b.get("camera_row"),
            "action_state": STATE_WAIT,
            "action_state_b": path_b.get("action_state") or "",
            "action_result": path_b.get("action_result"),
            "action_result_b": path_b.get("action_result"),
            "candidate_quality": quality.label,
            "candidate_quality_reason": quality.reason,
            "position_guardian_sell": position_guardian_sell,
        }

    # --- Fresh Action WHEN (arm C = arm B when CG not blocking) ---
    action_state = str(path_b.get("action_state") or STATE_WAIT)
    result = path_b.get("action_result")
    fresh = path_b.get("camera_row")
    if result is None:
        action_state, result, fresh = _action_eval(
            candidate,
            session=session,
            current_setup=current_setup,
            scan_row=scan_row,
            market_real=market_real,
            observed_at=observed_at,
            legal_bars=legal_bars,
            evaluate=eval_fn,
        )

    if action_state == STATE_BUY_READY:
        candidate["status"] = STATUS_BUY_READY
        candidate["buy_ready_session"] = str(session)[:10]
        candidate["buy_ready_at"] = getattr(result, "first_met_at", None) or as_vn(
            observed_at
        ).isoformat()
        candidate["buy_ready_price"] = getattr(result, "price_at_first_met", None)
        append_status_history(
            candidate,
            session=session,
            status=STATUS_BUY_READY,
            reason=REASON_BUY_READY,
            extra={
                "action_reason": getattr(result, "action_reason", ""),
                "quality_label": quality.label,
                **soft_pg,
            },
        )
        return {
            "candidate_key": candidate.get("candidate_key"),
            "status": STATUS_BUY_READY,
            "reason": REASON_BUY_READY,
            "status_b": STATUS_BUY_READY,
            "reason_b": REASON_BUY_READY,
            "camera_row": fresh,
            "action_state": STATE_BUY_READY,
            "action_result": result,
            "candidate_quality": quality.label,
            "candidate_quality_reason": quality.reason,
            "position_guardian_sell": position_guardian_sell,
        }

    wait_reason = (
        REASON_QUALITY_STRONGER_WAIT
        if quality.label == QUALITY_STRONGER
        else REASON_WHEN_NOT_MET
    )
    candidate["status"] = STATUS_ACTIVE
    append_status_history(
        candidate,
        session=session,
        status=STATUS_WAIT,
        reason=wait_reason,
        extra={
            "action_state": action_state,
            "action_reason": getattr(result, "action_reason", "") if result else "",
            **soft_pg,
        },
    )
    return {
        "candidate_key": candidate.get("candidate_key"),
        "status": STATUS_WAIT,
        "reason": wait_reason,
        "status_b": STATUS_WAIT,
        "reason_b": REASON_WHEN_NOT_MET if quality.label != QUALITY_STRONGER else wait_reason,
        "camera_row": fresh,
        "action_state": action_state or STATE_WAIT,
        "action_result": result,
        "candidate_quality": quality.label,
        "candidate_quality_reason": quality.reason,
        "position_guardian_sell": position_guardian_sell,
    }


def run_followup_session(
    *,
    session: str,
    observed_at: datetime,
    market_real: object,
    trading_dates: Sequence[str],
    sidecar_rows: Sequence[Mapping[str, Any]] | None = None,
    scan_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    guardian_by_symbol: Mapping[str, str] | None = None,
    bars_by_symbol: Mapping[str, Sequence[Any]] | None = None,
    directory: Path | None = None,
    force: bool = False,
    evaluate: ActionEvaluator | None = None,
) -> dict[str, Any]:
    """One research session. No-op when feature flag OFF (unless force=True for tests)."""
    if not force and not followup_enabled():
        return {
            "schema": SCHEMA_SESSION,
            "ok": True,
            "enabled": False,
            "reason": REASON_FLAG_OFF,
            "session": str(session)[:10],
            "ingested": [],
            "results": [],
            "camera_rows": [],
        }

    registry = load_registry(directory)
    ingested = ingest_sidecar_rows(registry, sidecar_rows, session=session)
    scan_map = {str(k).upper(): v for k, v in (scan_by_symbol or {}).items()}
    guard_map = {str(k).upper(): v for k, v in (guardian_by_symbol or {}).items()}
    bars_map = {str(k).upper(): v for k, v in (bars_by_symbol or {}).items()}

    results: list[dict[str, Any]] = []
    camera_rows: list[dict[str, Any]] = []
    for cand in active_candidates(registry):
        # Re-bind to mutable registry entry.
        key = str(cand.get("candidate_key") or "")
        live = registry["candidates"].get(key)
        if not isinstance(live, dict):
            continue
        if str(live.get("status") or "") not in {STATUS_ACTIVE, STATUS_WAIT}:
            continue
        symbol = str(live.get("symbol") or "").upper()
        outcome = evaluate_active_candidate(
            live,
            session=session,
            trading_dates=trading_dates,
            scan_row=scan_map.get(symbol),
            market_real=market_real,
            guardian_signal=guard_map.get(symbol, ""),
            observed_at=observed_at,
            legal_bars=bars_map.get(symbol) or (),
            evaluate=evaluate,
        )
        results.append(outcome)
        row = outcome.get("camera_row")
        if isinstance(row, dict) and outcome.get("status") in {STATUS_WAIT, STATUS_BUY_READY}:
            if _setup_of(row) in ACTIONABLE_LIVE_SETUPS:
                camera_rows.append(row)

    save_registry(registry, directory)
    append_ledger_rows(
        session=session,
        registry=registry,
        results=results,
        ingested=ingested,
        directory=directory,
    )
    return {
        "schema": SCHEMA_SESSION,
        "ok": True,
        "enabled": True,
        "mode": MODE,
        "slice": SLICE,
        "session": str(session)[:10],
        "ingested": ingested,
        "results": results,
        "camera_rows": camera_rows,
        "n_active": len(active_candidates(registry)),
        "registry_path": str(registry_path_safe(directory)),
    }


def registry_path_safe(directory: Path | None = None) -> Path:
    from modules.live_candidate_v2_followup.registry import registry_path

    return registry_path(directory)


__all__ = [
    "evaluate_active_candidate",
    "ingest_sidecar_rows",
    "normalize_trading_dates",
    "run_followup_session",
    "sessions_elapsed_inclusive",
]

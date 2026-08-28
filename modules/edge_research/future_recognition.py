"""
Future Recognition — generic ACTIVE-edge matcher (Phase B).

Consumes only edge_memory.status == ACTIVE plus the immutable FrozenHypothesisSpec.
Exact clause matching using Discovery ConditionClause semantics.
MATCH != BUY. No human-taught RSI/EMA/symbol rules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.contracts import (
    ASSESSMENT_NO_QUALIFIED_MATCH,
    ASSESSMENT_QUALIFIED_MATCH_FOUND,
    ASSESSMENT_UNABLE_TO_ASSESS,
    CONTEXT_COMPATIBLE,
    CONTEXT_INCOMPATIBLE,
    CONTEXT_UNKNOWN,
    EDGE_MEMORY_STATUS_ACTIVE,
    FEATURE_BUCKET_CONFIG_VERSION,
    FORWARD_OUTCOME_PENDING,
    FROZEN_SPEC_SCHEMA_VERSION,
    FROZEN_SPECS_DIRNAME,
    FUTURE_RECOGNITION_VERSION,
    MARKET_STATE_CONFIG_VERSION,
    REASON_NO_ACTIVE_EDGE_AVAILABLE,
    REASON_ALL_ACTIVE_EDGES_CONTEXT_INCOMPATIBLE,
    REASON_MATCHES_SUPPRESSED_BY_ANTI_CONTEXT,
    REASON_MATCHES_SUPPRESSED_BY_EDGE_HEALTH,
    REASON_NO_STOCK_SATISFIES_ACTIVE_EDGE,
)
from modules.edge_research.discovery import ConditionClause, apply_condition, canonical_condition_text
from modules.edge_research.edge_memory import load_active_memory
from modules.edge_research.forward_ledger import (
    RESEARCH_LABEL,
    append_session_assessment,
    ledger_id_for,
    persist_births,
    rebuild_daily_sidecar,
    write_latest_assessment,
)
from modules.edge_research.freeze import load_frozen_spec
from modules.edge_research.hypothesis import FrozenHypothesisSpec, spec_hash_from_dict
from modules.edge_research.oos_eval import clauses_from_frozen_spec
from modules.edge_research.storage import ensure_storage
from modules.edge_research.t0_universe import (
    T0Universe,
    T0UniverseError,
    latest_freeze_trade_date,
    load_session_universe,
    load_t0_freeze,
    systemic_features_missing,
)


SUPPORTED_SPEC_SCHEMAS = frozenset({FROZEN_SPEC_SCHEMA_VERSION, "frozen_hypothesis_spec_v2"})


class RecognitionError(RuntimeError):
    """Scientific assessment could not be completed."""


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def verify_spec_integrity(
    spec: FrozenHypothesisSpec,
    *,
    expected_hash: str = "",
    expected_hypothesis_id: str = "",
) -> Tuple[bool, str]:
    recomputed = spec_hash_from_dict(spec.to_dict())
    if spec.spec_hash and recomputed != spec.spec_hash:
        return False, "frozen_spec_hash_mismatch_internal"
    if expected_hash and expected_hash != spec.spec_hash and expected_hash != recomputed:
        return False, "edge_memory_spec_hash_mismatch"
    if expected_hypothesis_id and expected_hypothesis_id != spec.hypothesis_id:
        return False, "hypothesis_id_mismatch"
    schema = str(spec.spec_schema_version or "")
    if schema and schema not in SUPPORTED_SPEC_SCHEMAS:
        return False, f"unsupported_spec_schema:{schema}"
    if spec.feature_bucket_config_version and spec.feature_bucket_config_version != FEATURE_BUCKET_CONFIG_VERSION:
        return False, (
            f"feature_bucket_config_incompatible:"
            f"{spec.feature_bucket_config_version}!={FEATURE_BUCKET_CONFIG_VERSION}"
        )
    if spec.market_state_config_version and spec.market_state_config_version != MARKET_STATE_CONFIG_VERSION:
        return False, (
            f"market_state_config_incompatible:"
            f"{spec.market_state_config_version}!={MARKET_STATE_CONFIG_VERSION}"
        )
    clauses = clauses_from_frozen_spec(spec)
    if not clauses:
        return False, "frozen_spec_has_no_clauses"
    return True, "ok"


def evaluate_market_context(
    spec: FrozenHypothesisSpec,
    current_transition: str,
    current_state: str,
) -> Tuple[str, str]:
    """
    Exact research_market_transition compatibility.

    Does not broaden STRESS -> EARLY_RECOVERY into 'all recovery'.
    UNKNOWN current context does not guess COMPATIBLE.
    """
    expected = str(spec.market_transition or "").strip()
    current = str(current_transition or "").strip()
    cur_state = str(current_state or "").strip()
    if not current or current.upper() == "UNKNOWN" or "UNKNOWN" in current.upper() or cur_state.upper() == "UNKNOWN":
        return CONTEXT_UNKNOWN, (
            f"expected:{expected} current:{current or 'UNKNOWN'} verdict:{CONTEXT_UNKNOWN}"
        )
    if expected and current == expected:
        return CONTEXT_COMPATIBLE, (
            f"expected:{expected} current:{current} verdict:{CONTEXT_COMPATIBLE}"
        )
    return CONTEXT_INCOMPATIBLE, (
        f"expected:{expected} current:{current} verdict:{CONTEXT_INCOMPATIBLE}"
    )


def resolve_session_market_context(
    trade_date: str,
    *,
    universe: Optional[T0Universe] = None,
    override: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    if override:
        return {
            "research_market_state": str(override.get("research_market_state") or override.get("market_state") or "UNKNOWN"),
            "research_market_transition": str(
                override.get("research_market_transition") or override.get("market_transition") or "UNKNOWN"
            ),
            "research_market_level": str(override.get("research_market_level") or "UNKNOWN"),
            "research_market_trajectory": str(override.get("research_market_trajectory") or "UNKNOWN"),
        }
    from modules.edge_research.adapters import build_canonical_market_series
    from modules.edge_research.market_state import enrich_date_with_market_research

    series = build_canonical_market_series()
    if series is None or series.empty:
        return {
            "research_market_state": "UNKNOWN",
            "research_market_transition": "UNKNOWN",
            "research_market_level": "UNKNOWN",
            "research_market_trajectory": "UNKNOWN",
        }
    work = series.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work = work[work["date"] <= str(trade_date)].sort_values("date").reset_index(drop=True)
    if work.empty or str(trade_date) not in set(work["date"].astype(str)):
        # Last-resort PIT field from freeze rows themselves (still T0, not lifecycle).
        if universe is not None and not universe.frame.empty and "market_real" in universe.frame.columns:
            mr = pd.to_numeric(universe.frame["market_real"], errors="coerce").dropna()
            if not mr.empty:
                from modules.edge_research.market_state import (
                    classify_market_level,
                    derive_market_transition,
                    derive_research_market_state,
                    derive_research_market_trajectory,
                )

                level = classify_market_level(float(mr.median()))
                # Trajectory unknown without prior sessions — do not guess IMPROVING.
                traj = derive_research_market_trajectory(None, None)
                state = derive_research_market_state(level, traj, ambiguous=False)
                return {
                    "research_market_state": state,
                    "research_market_transition": derive_market_transition("UNKNOWN", state),
                    "research_market_level": level,
                    "research_market_trajectory": traj,
                }
        return {
            "research_market_state": "UNKNOWN",
            "research_market_transition": "UNKNOWN",
            "research_market_level": "UNKNOWN",
            "research_market_trajectory": "UNKNOWN",
        }
    state_history: Dict[str, str] = {}
    last: Dict[str, Any] = {}
    for d in work["date"].astype(str).tolist():
        last = enrich_date_with_market_research(d, work, pd.DataFrame(), state_history)
    return {
        "research_market_state": str(last.get("research_market_state") or "UNKNOWN"),
        "research_market_transition": str(last.get("research_market_transition") or "UNKNOWN"),
        "research_market_level": str(last.get("research_market_level") or "UNKNOWN"),
        "research_market_trajectory": str(last.get("research_market_trajectory") or "UNKNOWN"),
    }


@dataclass
class LoadedActiveEdge:
    memory_row: Dict[str, Any]
    spec: Optional[FrozenHypothesisSpec]
    ok: bool
    reason: str


def load_interpretable_active_edges(data_dir: Optional[Path] = None) -> List[LoadedActiveEdge]:
    memory = load_active_memory(data_dir)
    loaded: List[LoadedActiveEdge] = []
    if memory.empty:
        return loaded
    for rec in memory.to_dict(orient="records"):
        if str(rec.get("status", "")).upper() != EDGE_MEMORY_STATUS_ACTIVE:
            continue
        hid = str(rec.get("hypothesis_id", "") or "")
        spec = load_frozen_spec(hid, data_dir) if hid else None
        if spec is None:
            loaded.append(LoadedActiveEdge(rec, None, False, "frozen_spec_missing"))
            continue
        ok, reason = verify_spec_integrity(
            spec,
            expected_hash=str(rec.get("spec_hash") or ""),
            expected_hypothesis_id=hid,
        )
        loaded.append(LoadedActiveEdge(rec, spec if ok else spec, ok, reason))
    return loaded


def _feature_values(row: pd.Series, clauses: Sequence[ConditionClause]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for clause in clauses:
        val = pd.to_numeric(row.get(clause.feature), errors="coerce")
        values[clause.feature] = None if pd.isna(val) else float(val)
    return values


def symbol_missing_required_features(row: pd.Series, clauses: Sequence[ConditionClause]) -> List[str]:
    missing: List[str] = []
    for clause in clauses:
        if clause.feature not in row.index:
            missing.append(clause.feature)
            continue
        val = pd.to_numeric(row.get(clause.feature), errors="coerce")
        if pd.isna(val):
            missing.append(clause.feature)
    return missing


def match_universe_to_spec(
    spec: FrozenHypothesisSpec,
    universe: T0Universe,
) -> List[pd.Series]:
    """Exact Discovery clause semantics. Cohort membership is not a predicate."""
    clauses = clauses_from_frozen_spec(spec)
    if not clauses:
        return []
    frame = universe.frame
    eligible_idx = []
    for idx, row in frame.iterrows():
        if symbol_missing_required_features(row, clauses):
            continue
        eligible_idx.append(idx)
    if not eligible_idx:
        return []
    eligible = frame.loc[eligible_idx]
    matched = apply_condition(eligible, clauses)
    return [row for _, row in matched.iterrows()]


def _selection_reason(
    spec: FrozenHypothesisSpec,
    row: pd.Series,
    context_reason: str,
) -> Tuple[str, str]:
    clauses = clauses_from_frozen_spec(spec)
    bits_en: List[str] = []
    bits_vi: List[str] = []
    for clause in clauses:
        val = pd.to_numeric(row.get(clause.feature), errors="coerce")
        shown = "NA" if pd.isna(val) else f"{float(val):g}"
        bits_en.append(f"{clause.to_text()} (T0 {clause.feature}={shown})")
        bits_vi.append(f"{clause.to_text()} (T0 {clause.feature}={shown})")
    en = (
        f"RESEARCH MATCH {spec.edge_id} because market {context_reason}; "
        f"stock {row.get('symbol')} satisfies frozen clauses: " + "; ".join(bits_en)
    )
    vi = (
        f"KHỚP NGHIÊN CỨU {spec.edge_id}: ngữ cảnh {context_reason}; "
        f"mã {row.get('symbol')} thỏa điều kiện đóng băng: " + "; ".join(bits_vi)
    )
    return en, vi


def _oos_summary(memory_row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "oos_result": memory_row.get("oos_result"),
        "oos_candidate_n": memory_row.get("oos_candidate_n"),
        "oos_baseline_n": memory_row.get("oos_baseline_n"),
        "oos_incremental_median": memory_row.get("oos_incremental_median"),
        "oos_incremental_mean": memory_row.get("oos_incremental_mean"),
        "episode_count": memory_row.get("episode_count"),
        "activated_at": memory_row.get("activated_at") or memory_row.get("confirmed_at"),
    }


def _build_birth(
    *,
    spec: FrozenHypothesisSpec,
    memory_row: Dict[str, Any],
    row: pd.Series,
    trade_date: str,
    context_verdict: str,
    context_reason: str,
    current_state: str,
    current_transition: str,
    universe: T0Universe,
    run_id: str,
    born_at: str,
) -> Dict[str, Any]:
    clauses = clauses_from_frozen_spec(spec)
    symbol = str(row.get("symbol", "")).upper().strip()
    reason_en, reason_vi = _selection_reason(spec, row, context_reason)
    return {
        "ledger_id": ledger_id_for(spec.hypothesis_id, trade_date, symbol),
        "hypothesis_id": spec.hypothesis_id,
        "t0_date": trade_date,
        "t0_trade_date": trade_date,
        "symbol": symbol,
        "frozen_at": spec.frozen_at or spec.freeze_timestamp,
        "born_at": born_at,
        "outcome_status": FORWARD_OUTCOME_PENDING,
        "edge_id": spec.edge_id or memory_row.get("edge_id"),
        "spec_path": memory_row.get("spec_path") or f"{FROZEN_SPECS_DIRNAME}/{spec.hypothesis_id}.json",
        "spec_hash": spec.spec_hash,
        "spec_schema_version": spec.spec_schema_version,
        "feature_bucket_config_version": spec.feature_bucket_config_version,
        "market_state_config_version": spec.market_state_config_version,
        "market_state_t0": current_state,
        "market_transition_t0": current_transition,
        "context_verdict": context_verdict,
        "context_reason": context_reason,
        "stock_feature_values_json": json.dumps(_feature_values(row, clauses), ensure_ascii=False),
        "matched_clauses_json": json.dumps(list(spec.feature_clauses), ensure_ascii=False),
        "condition_key": spec.condition_key,
        "condition_text": spec.condition_text or canonical_condition_text(clauses),
        "best_horizon": spec.best_horizon,
        "active_status_at_birth": EDGE_MEMORY_STATUS_ACTIVE,
        "oos_evidence_json": json.dumps(_oos_summary(memory_row), ensure_ascii=False, default=str),
        "universe_count": universe.universe_count,
        "universe_hash": universe.universe_hash,
        "pit_artifact": universe.pit_artifact,
        "pit_artifact_hash": universe.pit_artifact_hash,
        "assessment_run_id": run_id,
        "selection_reason": reason_en,
        "selection_reason_vi": reason_vi,
        "research_label": RESEARCH_LABEL,
    }


def _increment_forward_matches(edge_ids: List[str], data_dir: Path) -> None:
    """Safe birth counter only — does not decay or change ACTIVE status."""
    from modules.edge_research.storage import read_ledger

    if not edge_ids:
        return
    memory = read_ledger("edge_memory.csv", data_dir=data_dir)
    if memory.empty or "edge_id" not in memory.columns:
        return
    if "forward_matches" not in memory.columns:
        memory["forward_matches"] = 0
    memory["forward_matches"] = pd.to_numeric(memory["forward_matches"], errors="coerce").fillna(0)
    for eid in edge_ids:
        mask = memory["edge_id"].astype(str) == str(eid)
        memory.loc[mask, "forward_matches"] = memory.loc[mask, "forward_matches"] + 1
    memory.to_csv(data_dir / "edge_memory.csv", index=False)


def run_future_recognition(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    freeze_path: Optional[Path] = None,
    market_context: Optional[Dict[str, str]] = None,
    raise_internal: Optional[Exception] = None,
) -> Dict[str, Any]:
    """
    One session assessment: load ACTIVE edges, check context, scan T0 universe,
    persist births, write session assessment.

    raise_internal is test-only (injected matcher exception).
    """
    started = _iso_now()
    root = ensure_storage(data_dir)
    run_id = hashlib.sha256(f"{started}:{trade_date}:{FUTURE_RECOGNITION_VERSION}".encode()).hexdigest()[:12]
    assessment: Dict[str, Any] = {
        "trade_date": trade_date or "",
        "run_id": run_id,
        "started_at": started,
        "completed_at": "",
        "assessment_state": ASSESSMENT_UNABLE_TO_ASSESS,
        "reason": "",
        "t0_source_status": "",
        "universe_count": 0,
        "universe_hash": "",
        "active_edge_count": 0,
        "edges_loaded_ok": 0,
        "edges_uninterpretable": 0,
        "edges_context_compatible": 0,
        "edges_context_incompatible": 0,
        "edges_context_unknown": 0,
        "stock_edge_evaluations": 0,
        "qualified_match_count": 0,
        "new_birth_count": 0,
        "duplicate_skip_count": 0,
        "matcher_version": FUTURE_RECOGNITION_VERSION,
        "spec_schema_version": FROZEN_SPEC_SCHEMA_VERSION,
        "pit_artifact": "",
        "failure_detail": "",
        "matches": [],
        "research_label": RESEARCH_LABEL,
    }

    def _finish(state: str, reason: str, detail: str = "") -> Dict[str, Any]:
        assessment["assessment_state"] = state
        assessment["reason"] = reason
        assessment["failure_detail"] = detail
        assessment["completed_at"] = _iso_now()
        append_session_assessment(assessment, data_dir=root)
        write_latest_assessment(assessment, data_dir=root)
        if assessment.get("trade_date"):
            try:
                rebuild_daily_sidecar(str(assessment["trade_date"]), assessment, data_dir=root)
            except Exception:
                pass
        return assessment

    try:
        if raise_internal is not None:
            raise raise_internal

        if freeze_df is None:
            freeze_all = load_t0_freeze(freeze_path)
        else:
            freeze_all = freeze_df
        session_date = trade_date or latest_freeze_trade_date(freeze_all)
        if not session_date:
            return _finish(ASSESSMENT_UNABLE_TO_ASSESS, "T0_FREEZE_DATE_UNAVAILABLE", "no trade_date in freeze")
        assessment["trade_date"] = session_date

        universe = load_session_universe(
            session_date, freeze_df=freeze_all, freeze_path=freeze_path
        )
        assessment["t0_source_status"] = universe.source_status
        assessment["universe_count"] = universe.universe_count
        assessment["universe_hash"] = universe.universe_hash
        assessment["pit_artifact"] = universe.pit_artifact

        loaded = load_interpretable_active_edges(root)
        assessment["active_edge_count"] = len(loaded)
        ok_edges = [e for e in loaded if e.ok and e.spec is not None]
        bad_edges = [e for e in loaded if not e.ok]
        assessment["edges_loaded_ok"] = len(ok_edges)
        assessment["edges_uninterpretable"] = len(bad_edges)

        if loaded and not ok_edges:
            detail = "; ".join(sorted({e.reason for e in bad_edges}))
            return _finish(ASSESSMENT_UNABLE_TO_ASSESS, "ACTIVE_EDGE_SPEC_UNINTERPRETABLE", detail)

        market = resolve_session_market_context(
            session_date, universe=universe, override=market_context
        )
        assessment["market_context"] = market
        current_transition = str(market.get("research_market_transition") or "UNKNOWN")
        current_state = str(market.get("research_market_state") or "UNKNOWN")

        if not loaded:
            from modules.edge_research.contracts import EDGE_MEMORY_STATUS_DECAYING
            from modules.edge_research.edge_memory import load_memory_by_status

            decaying = load_memory_by_status(EDGE_MEMORY_STATUS_DECAYING, root)
            if not decaying.empty:
                return _finish(
                    ASSESSMENT_NO_QUALIFIED_MATCH,
                    REASON_MATCHES_SUPPRESSED_BY_EDGE_HEALTH,
                    f"decaying_edges={len(decaying)}; no ACTIVE reusable edges",
                )
            return _finish(
                ASSESSMENT_NO_QUALIFIED_MATCH,
                REASON_NO_ACTIVE_EDGE_AVAILABLE,
                "pipeline ran; zero ACTIVE reusable edges",
            )

        market_unknown = (
            current_state.upper() == "UNKNOWN"
            or "UNKNOWN" in current_transition.upper()
            or not current_transition
        )
        if market_unknown:
            return _finish(
                ASSESSMENT_UNABLE_TO_ASSESS,
                "MARKET_CONTEXT_UNKNOWN",
                f"state={current_state} transition={current_transition}",
            )

        required: List[str] = []
        for edge in ok_edges:
            for c in clauses_from_frozen_spec(edge.spec):  # type: ignore[arg-type]
                if c.feature not in required:
                    required.append(c.feature)
        systemic = systemic_features_missing(universe, required) if required else []
        if required and systemic and len(systemic) == len(required):
            return _finish(
                ASSESSMENT_UNABLE_TO_ASSESS,
                "FEATURE_CONTRACT_UNAVAILABLE",
                f"missing:{','.join(systemic)}",
            )

        births: List[Dict[str, Any]] = []
        match_views: List[Dict[str, Any]] = []
        evaluations = 0
        born_at = _iso_now()

        for edge in ok_edges:
            spec = edge.spec
            assert spec is not None
            verdict, reason = evaluate_market_context(spec, current_transition, current_state)
            if verdict == CONTEXT_COMPATIBLE:
                assessment["edges_context_compatible"] += 1
            elif verdict == CONTEXT_INCOMPATIBLE:
                assessment["edges_context_incompatible"] += 1
                continue
            else:
                assessment["edges_context_unknown"] += 1
                continue

            from modules.edge_research.anti_context import anti_context_for

            blocked = anti_context_for(spec.hypothesis_id, current_transition, root)
            if blocked:
                assessment["anti_context_suppressions"] = int(assessment.get("anti_context_suppressions") or 0) + 1
                assessment["anti_context_reason"] = blocked.get("reason") or REASON_MATCHES_SUPPRESSED_BY_ANTI_CONTEXT
                continue

            clauses = clauses_from_frozen_spec(spec)
            for _, row in universe.frame.iterrows():
                evaluations += 1
                if symbol_missing_required_features(row, clauses):
                    continue
                one = apply_condition(pd.DataFrame([row]), clauses)
                if one.empty:
                    continue
                birth = _build_birth(
                    spec=spec,
                    memory_row=edge.memory_row,
                    row=row,
                    trade_date=session_date,
                    context_verdict=verdict,
                    context_reason=reason,
                    current_state=current_state,
                    current_transition=current_transition,
                    universe=universe,
                    run_id=run_id,
                    born_at=born_at,
                )
                births.append(birth)
                match_views.append(
                    {
                        "symbol": birth["symbol"],
                        "edge_id": birth["edge_id"],
                        "hypothesis_id": birth["hypothesis_id"],
                        "context_verdict": verdict,
                        "context_reason": reason,
                        "condition_text": birth["condition_text"],
                        "best_horizon": birth["best_horizon"],
                        "oos_evidence": _oos_summary(edge.memory_row),
                        "selection_reason": birth["selection_reason"],
                        "selection_reason_vi": birth["selection_reason_vi"],
                        "feature_values": json.loads(birth["stock_feature_values_json"]),
                        "research_label": RESEARCH_LABEL,
                        "live_forward_status": FORWARD_OUTCOME_PENDING,
                        "edge_health": edge.memory_row.get("health_status") or EDGE_MEMORY_STATUS_ACTIVE,
                        "edge_status": EDGE_MEMORY_STATUS_ACTIVE,
                        "forward_evidence": {
                            "mature_n": edge.memory_row.get("forward_matured"),
                            "incremental_median": edge.memory_row.get("forward_incremental_median"),
                            "sessions": edge.memory_row.get("forward_unique_sessions"),
                            "episodes": edge.memory_row.get("forward_unique_episodes"),
                            "health_reason": edge.memory_row.get("health_reason"),
                        },
                    }
                )

        assessment["stock_edge_evaluations"] = evaluations
        persisted = persist_births(births, data_dir=root)
        assessment["new_birth_count"] = int(persisted.get("new_births") or 0)
        assessment["duplicate_skip_count"] = int(persisted.get("duplicate_skips") or 0)
        assessment["qualified_match_count"] = len(births)
        assessment["matches"] = match_views
        actually_new = list(persisted.get("new_edge_ids") or [])
        if actually_new:
            _increment_forward_matches(actually_new, root)

        if births:
            return _finish(ASSESSMENT_QUALIFIED_MATCH_FOUND, "QUALIFIED_MATCHES_PERSISTED")
        if int(assessment.get("anti_context_suppressions") or 0) > 0:
            return _finish(
                ASSESSMENT_NO_QUALIFIED_MATCH,
                REASON_MATCHES_SUPPRESSED_BY_ANTI_CONTEXT,
                str(assessment.get("anti_context_reason") or ""),
            )
        if assessment["edges_context_compatible"] == 0 and assessment["active_edge_count"] > 0:
            return _finish(
                ASSESSMENT_NO_QUALIFIED_MATCH,
                REASON_ALL_ACTIVE_EDGES_CONTEXT_INCOMPATIBLE,
                f"incompatible={assessment['edges_context_incompatible']}",
            )
        return _finish(
            ASSESSMENT_NO_QUALIFIED_MATCH,
            REASON_NO_STOCK_SATISFIES_ACTIVE_EDGE,
            (
                f"compatible_edges={assessment['edges_context_compatible']} "
                f"universe={universe.universe_count}"
            ),
        )
    except T0UniverseError as exc:
        return _finish(ASSESSMENT_UNABLE_TO_ASSESS, "T0_UNIVERSE_UNAVAILABLE", str(exc))
    except Exception as exc:
        return _finish(ASSESSMENT_UNABLE_TO_ASSESS, "MATCHER_EXCEPTION", f"{type(exc).__name__}: {exc}")


def format_future_recognition_operator_text(assessment: Dict[str, Any]) -> str:
    """Deterministic operator surface for the three daily assessment states."""
    if not assessment:
        return (
            "UNABLE TO ASSESS\n"
            "Reason: session assessment did not run (no latest_future_recognition.json).\n"
            "This is NOT 'no opportunities today.'"
        )
    state = str(assessment.get("assessment_state") or ASSESSMENT_UNABLE_TO_ASSESS)
    reason = str(assessment.get("reason") or "")
    detail = str(assessment.get("failure_detail") or "")
    trade_date = str(assessment.get("trade_date") or "")
    lines: List[str] = ["FUTURE RECOGNITION — LIVE_FORWARD"]
    if trade_date:
        lines.append(f"Session: {trade_date}")
    if state == ASSESSMENT_QUALIFIED_MATCH_FOUND:
        lines.append("QUALIFIED MATCH FOUND")
        matches = assessment.get("matches") or []
        if not matches:
            lines.append("Qualified stock-edge births exist; see edge_forward_ledger.")
        for match in matches:
            oos = match.get("oos_evidence") or {}
            lines.extend(
                [
                    "",
                    str(match.get("symbol") or ""),
                    str(match.get("edge_id") or ""),
                    "LIVE_FORWARD",
                    f"Market context: {match.get('context_verdict') or ''} — {match.get('context_reason') or ''}",
                    f"Why selected: {match.get('condition_text') or ''}",
                    f"Expected horizon: {match.get('best_horizon') or ''}",
                    (
                        "Edge evidence: ACTIVE"
                        f" OOS n={oos.get('oos_candidate_n', '')}"
                        f" incremental median={oos.get('oos_incremental_median', '')}"
                        f" episodes={oos.get('episode_count', '')}"
                    ),
                    (
                        f"Health: {match.get('edge_health') or 'INSUFFICIENT_EVIDENCE'} "
                        f"status={match.get('edge_status') or 'ACTIVE'}"
                    ),
                    (
                        "Forward evidence: "
                        f"{(match.get('forward_evidence') or {}).get('mature_n') or 0} mature "
                        f"{match.get('best_horizon') or 'T5'} matches / "
                        f"{(match.get('forward_evidence') or {}).get('sessions') or 0} sessions / "
                        f"{(match.get('forward_evidence') or {}).get('episodes') or 0} episodes; "
                        f"incremental median={(match.get('forward_evidence') or {}).get('incremental_median') or '—'}"
                    ),
                    f"Status: {match.get('research_label') or RESEARCH_LABEL}",
                    f"Reason: {match.get('selection_reason') or ''}",
                ]
            )
            if match.get("selection_reason_vi"):
                lines.append(f"Lý do: {match['selection_reason_vi']}")
        return "\n".join(lines)
    if state == ASSESSMENT_NO_QUALIFIED_MATCH:
        lines.extend(
            [
                "NO QUALIFIED MATCH",
                "Assessment completed successfully.",
                f"ACTIVE edges checked: {assessment.get('active_edge_count', 0)}",
                f"Compatible edges: {assessment.get('edges_context_compatible', 0)}",
                f"Universe scanned: {assessment.get('universe_count', 0)}",
                f"Qualified stocks: {assessment.get('qualified_match_count', 0)}",
                f"Reason: {reason or 'No current stock satisfies an ACTIVE learned edge in compatible context.'}",
            ]
        )
        if reason == REASON_NO_ACTIVE_EDGE_AVAILABLE:
            lines.append(
                "No ACTIVE reusable knowledge was available to apply. This is not a system failure."
            )
        elif not reason:
            lines.append(
                "No current stock satisfies an ACTIVE learned edge in compatible context."
            )
        lines.append(RESEARCH_LABEL)
        return "\n".join(lines)
    lines.extend(
        [
            "UNABLE TO ASSESS",
            f"Reason: {reason or 'assessment could not be completed scientifically.'}",
        ]
    )
    if detail:
        lines.append(f"Detail: {detail}")
    lines.append("This is NOT 'no opportunities today.'")
    return "\n".join(lines)

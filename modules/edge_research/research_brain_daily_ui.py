"""
Read-only Research Brain daily observability.

Renders canonical production artifacts already written by the autonomous
pipeline. Never mkdir, never write, never calls discovery/challenger/
proposition-selection/experiments/forward/EOD/memory writers.

Intentionally avoids opr_bridge imports so Streamlit Cloud can load this
surface without the full OPR stack.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from modules.edge_research.storage import resolve_data_dir, resolve_production_runs_root

RESEARCH_BRAIN_EXPANDER_TITLE = "🧠 Research Brain — Hôm nay đào gì?"
MISSING_DATA = "Chưa có dữ liệu"
SELECTION_UNSAVED = "Selection reason: chưa được artifact lưu"
MEMORY_NOT_FORMED = "Research Memory: chưa hình thành từ production run mới."
PROVENANCE_INSUFFICIENT = "Chưa đủ provenance để giải thích quyết định nghiên cứu."
NOT_BUY_SELL = "Research conclusion only — NOT a BUY/SELL signal."
COHORT_CONTEXT_ONLY = "MARKET/COHORT CONTEXT ONLY"
HISTORY_LIMIT = 5

_CANONICAL_FORWARD_HORIZONS = ("T3", "T5", "T10")
_EVALUATED = "EVALUATED"
_RELEASED = "RELEASED"
_WAITING = "WAITING"

# Display-only mapping of persisted forward evaluation_status → operator label.
# Does not change ledger status.
_FORWARD_RELEASE_LABELS = {
    "EVALUATED": _RELEASED,
}

# Last-forward adjudications the engine already treats as still pending.
_PENDING_FORWARD_ADJUDICATIONS = frozenset(
    {
        "",
        "MISSING_DATA",
        "CONTEXT_ONLY",
        "LEGACY_INSUFFICIENT_CLAIM_SPEC",
        "CLAIM_INCONCLUSIVE",
    }
)

_SCIENTIFIC_RELATIVE_PREFIXES = (
    "production_observation_ledger.jsonl",
    "production_observation_index.json",
    "production_observations/",
    "research_memory/",
    "opr_research_sessions/",
    "opr_opportunity_registry.json",
    "first_experiment_",
    "second_experiment_",
    "bounded_lifecycle_",
    "proposition_",
)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows


def _edge_root(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir)


def _prod_root(data_dir: Optional[Path] = None) -> Path:
    return resolve_production_runs_root(data_dir)


def _safe_id(value: str) -> str:
    return str(value).replace("/", "_").replace("\\", "_")


def _display(value: Any, *, missing: str = MISSING_DATA) -> str:
    if value is None:
        return missing
    if isinstance(value, str) and not value.strip():
        return missing
    if isinstance(value, (list, tuple)) and not value:
        return missing
    return str(value)


def _latest_successful_run_meta(prod_root: Path, trade_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    index = _read_json(prod_root / "daily_run_index.json") or {}
    runs = index.get("runs") or {}
    candidates = [
        m
        for m in runs.values()
        if isinstance(m, dict) and m.get("run_disposition") == "SUCCESS" and m.get("target_trade_date")
    ]
    if trade_date:
        matches = [m for m in candidates if m.get("target_trade_date") == trade_date]
        if not matches:
            return None
        live = [m for m in matches if m.get("run_mode") == "LIVE_FORWARD"]
        return (live or matches)[0]
    if not candidates:
        return None

    def _key(m: Dict[str, Any]) -> tuple:
        mode_rank = 1 if m.get("run_mode") == "LIVE_FORWARD" else 0
        return (str(m.get("target_trade_date")), mode_rank, str(m.get("run_id") or ""))

    return max(candidates, key=_key)


def _load_birth(prod_root: Path, observation_id: str) -> Optional[Dict[str, Any]]:
    return _read_json(prod_root / f"{_safe_id(observation_id)}.json")


def _load_opr_session(edge_root: Path, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    return _read_json(edge_root / "opr_research_sessions" / f"{_safe_id(session_id)}.json")


def _load_memory_store(edge_root: Path) -> Optional[Dict[str, Any]]:
    return _read_json(edge_root / "research_memory" / "research_memory_index.json")


def _load_memory_events(edge_root: Path) -> List[Dict[str, Any]]:
    return _read_jsonl(edge_root / "research_memory" / "research_memory_events.jsonl")


def _load_observation_index(edge_root: Path) -> Dict[str, Any]:
    return _read_json(edge_root / "production_observation_index.json") or {}


def _claim_spec(birth: Dict[str, Any]) -> Dict[str, Any]:
    contract = birth.get("forward_evaluation_contract") or {}
    if not isinstance(contract, dict):
        return {}
    spec = contract.get("claim_spec")
    if isinstance(spec, dict) and spec:
        return spec
    criteria = contract.get("evaluation_criteria") or {}
    nested = criteria.get("claim_spec") if isinstance(criteria, dict) else None
    return nested if isinstance(nested, dict) else {}


def _claim_contract_status(birth: Dict[str, Any]) -> Optional[str]:
    contract = birth.get("forward_evaluation_contract") or {}
    if not isinstance(contract, dict):
        return None
    status = contract.get("claim_contract_status")
    if status:
        return str(status)
    criteria = contract.get("evaluation_criteria") or {}
    if isinstance(criteria, dict) and criteria.get("claim_contract_status"):
        return str(criteria["claim_contract_status"])
    spec = _claim_spec(birth)
    if spec.get("claim_contract_status"):
        return str(spec["claim_contract_status"])
    return None


def _feature_outcome_horizon(birth: Dict[str, Any], selection: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    spec = _claim_spec(birth)
    feature = spec.get("feature") or selection.get("selected_feature")
    outcome = spec.get("outcome_field") or selection.get("selected_outcome")
    horizon = spec.get("observation_horizon")
    feature = str(feature) if feature not in (None, "") else None
    outcome = str(outcome) if outcome not in (None, "") else None
    if horizon in (None, ""):
        horizon_s = None
    else:
        horizon_s = str(horizon)
    return feature, outcome, horizon_s


def _feature_horizon_label(feature: Optional[str], outcome: Optional[str], horizon: Optional[str]) -> Optional[str]:
    if feature and horizon:
        return f"{feature} → {horizon}"
    if feature and outcome:
        return f"{feature} → {outcome}"
    return None


def _selection_from_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload = event.get("selection_provenance")
    return payload if isinstance(payload, dict) and payload else None


def _lookup_selection_provenance(
    observation_id: str,
    memory: Optional[Dict[str, Any]],
    events: List[Dict[str, Any]],
    birth: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    embedded = birth.get("selection_provenance")
    if isinstance(embedded, dict) and embedded:
        return embedded
    for event in reversed(events):
        if event.get("observation_id") == observation_id:
            found = _selection_from_event(event)
            if found:
                return found
    families = (memory or {}).get("families") or {}
    if not isinstance(families, dict):
        return None
    for family in families.values():
        if not isinstance(family, dict):
            continue
        obs_ids = [str(x) for x in (family.get("observation_ids") or [])]
        if not obs_ids or observation_id not in obs_ids:
            continue
        if obs_ids[-1] != observation_id:
            continue
        prov = family.get("last_selection_provenance")
        if isinstance(prov, dict) and prov:
            return prov
    return None


def _selection_view(provenance: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not provenance:
        return {
            "available": False,
            "scientific_reasons": [],
            "why_selected": None,
            "selected_feature": None,
            "selected_outcome": None,
            "selected_question": None,
            "considered": [],
            "rejected": [],
            "empty_memory": None,
            "memory_consulted": None,
            "unavailable_reason": SELECTION_UNSAVED,
        }
    reasons = provenance.get("scientific_reasons") or []
    if not isinstance(reasons, list):
        reasons = [reasons]
    return {
        "available": True,
        "scientific_reasons": [str(r) for r in reasons if r not in (None, "")],
        "why_selected": provenance.get("why_selected") or None,
        "selected_feature": provenance.get("selected_feature") or None,
        "selected_outcome": provenance.get("selected_outcome") or None,
        "selected_question": provenance.get("selected_question") or None,
        "considered": list(provenance.get("considered") or []),
        "rejected": list(provenance.get("rejected") or []),
        "empty_memory": provenance.get("empty_memory"),
        "memory_consulted": provenance.get("memory_consulted"),
        "unavailable_reason": None,
    }


def _compared_to_known(selection: Dict[str, Any]) -> Dict[str, Any]:
    if not selection.get("available"):
        return {
            "available": False,
            "why_selected": None,
            "scientific_reasons": [],
            "selected_feature": None,
            "selected_outcome": None,
            "unavailable_reason": PROVENANCE_INSUFFICIENT,
        }
    if not selection.get("why_selected") and not selection.get("scientific_reasons"):
        return {
            "available": False,
            "why_selected": None,
            "scientific_reasons": [],
            "selected_feature": selection.get("selected_feature"),
            "selected_outcome": selection.get("selected_outcome"),
            "unavailable_reason": PROVENANCE_INSUFFICIENT,
        }
    return {
        "available": True,
        "why_selected": selection.get("why_selected"),
        "scientific_reasons": list(selection.get("scientific_reasons") or []),
        "selected_feature": selection.get("selected_feature"),
        "selected_outcome": selection.get("selected_outcome"),
        "unavailable_reason": None,
    }


def _session_experiment_entries(session: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not session:
        return []
    hist = session.get("experiment_history")
    if isinstance(hist, list) and hist:
        return [e for e in hist if isinstance(e, dict)]
    entries: List[Dict[str, Any]] = []
    if any(
        session.get(k)
        for k in (
            "initial_experiment_package",
            "first_experiment_execution",
            "first_experiment_interpretation",
            "first_experiment_epistemic_update",
            "first_experiment_research_decision",
        )
    ):
        entries.append(
            {
                "ordinal": 1,
                "package": session.get("initial_experiment_package"),
                "execution": session.get("first_experiment_execution"),
                "interpretation": session.get("first_experiment_interpretation"),
                "epistemic_update": session.get("first_experiment_epistemic_update"),
                "decision": session.get("first_experiment_research_decision"),
            }
        )
    if any(
        session.get(k)
        for k in (
            "second_experiment_package",
            "second_experiment_execution",
            "second_experiment_interpretation",
            "second_experiment_epistemic_update",
            "second_experiment_research_decision",
        )
    ):
        entries.append(
            {
                "ordinal": 2,
                "package": session.get("second_experiment_package"),
                "execution": session.get("second_experiment_execution"),
                "interpretation": session.get("second_experiment_interpretation"),
                "epistemic_update": session.get("second_experiment_epistemic_update"),
                "decision": session.get("second_experiment_research_decision"),
            }
        )
    return entries


def _nested_get(payload: Any, *keys: str) -> Any:
    cur = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _experiment_from_session_entry(entry: Dict[str, Any], ordinal: int) -> Dict[str, Any]:
    pkg = entry.get("package") if isinstance(entry.get("package"), dict) else {}
    interp = entry.get("interpretation") if isinstance(entry.get("interpretation"), dict) else {}
    epistemic = entry.get("epistemic_update") if isinstance(entry.get("epistemic_update"), dict) else {}
    decision = entry.get("decision") if isinstance(entry.get("decision"), dict) else {}
    execution = entry.get("execution") if isinstance(entry.get("execution"), dict) else {}
    ea = interp.get("evidence_assessment") if isinstance(interp.get("evidence_assessment"), dict) else {}
    metrics = interp.get("metrics_used") if isinstance(interp.get("metrics_used"), dict) else {}
    target = pkg.get("target_null") or pkg.get("null_target") or {}
    if isinstance(target, dict):
        target_null = target.get("null_key") or target.get("null_id")
    else:
        target_null = target
    experiment_type = (
        pkg.get("experiment_type")
        or pkg.get("selected_action")
        or _nested_get(decision, "research_decision", "chosen_next_action")
        or decision.get("chosen_next_action")
        or pkg.get("tool")
        or execution.get("tool_name")
    )
    ran = bool(execution or interp or epistemic)
    return {
        "ordinal": ordinal,
        "ran": ran,
        "experiment_type": experiment_type,
        "target_null": target_null,
        "evidence_interpretation": ea.get("evidence_class") or ea.get("direction") or interp.get("evidence_class"),
        "strength": ea.get("strength") or metrics.get("falsify_strength"),
        "epistemic_from": epistemic.get("prior_epistemic_state") or interp.get("prior_epistemic_state"),
        "epistemic_to": epistemic.get("resulting_epistemic_state") or interp.get("resulting_epistemic_state"),
        "transition_key": epistemic.get("transition_key"),
        "source": "opr_session",
    }


def _experiment_from_journey(row: Dict[str, Any]) -> Dict[str, Any]:
    ordinal = int(row.get("ordinal") or 0)
    ran = any(
        row.get(k)
        for k in (
            "tool",
            "evidence_direction",
            "evidence_strength",
            "epistemic_state_leaving",
            "experiment_identity",
            "targeted_null",
        )
    )
    return {
        "ordinal": ordinal,
        "ran": ran,
        "experiment_type": row.get("tool") or row.get("chosen_action"),
        "target_null": row.get("targeted_null"),
        "evidence_interpretation": row.get("evidence_direction"),
        "strength": row.get("evidence_strength"),
        "epistemic_from": row.get("epistemic_state_entering"),
        "epistemic_to": row.get("epistemic_state_leaving"),
        "transition_key": None,
        "source": "birth_journey_rows",
    }


def _merge_experiment(primary: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not extra:
        return primary
    merged = dict(primary)
    for key in (
        "experiment_type",
        "target_null",
        "evidence_interpretation",
        "strength",
        "epistemic_from",
        "epistemic_to",
        "transition_key",
    ):
        if merged.get(key) in (None, "") and extra.get(key) not in (None, ""):
            merged[key] = extra[key]
    merged["ran"] = bool(primary.get("ran") or extra.get("ran"))
    return merged


def _empty_experiment(ordinal: int) -> Dict[str, Any]:
    return {
        "ordinal": ordinal,
        "ran": False,
        "experiment_type": None,
        "target_null": None,
        "evidence_interpretation": None,
        "strength": None,
        "epistemic_from": None,
        "epistemic_to": None,
        "transition_key": None,
        "source": None,
    }


def _build_experiments(birth: Dict[str, Any], session: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_ordinal: Dict[int, Dict[str, Any]] = {}
    for row in birth.get("journey_rows") or []:
        if not isinstance(row, dict):
            continue
        try:
            ordinal = int(row.get("ordinal") or 0)
        except (TypeError, ValueError):
            continue
        if ordinal <= 0:
            continue
        by_ordinal[ordinal] = _experiment_from_journey(row)
    for entry in _session_experiment_entries(session):
        try:
            ordinal = int(entry.get("ordinal") or 0)
        except (TypeError, ValueError):
            continue
        if ordinal <= 0:
            continue
        session_view = _experiment_from_session_entry(entry, ordinal)
        by_ordinal[ordinal] = _merge_experiment(by_ordinal.get(ordinal) or _empty_experiment(ordinal), session_view)
    experiments = [by_ordinal.get(1) or _empty_experiment(1), by_ordinal.get(2) or _empty_experiment(2)]
    extras = [by_ordinal[k] for k in sorted(by_ordinal) if k > 2]
    return experiments + extras


def _latest_assessment(prod_root: Path, observation_id: str) -> Optional[Dict[str, Any]]:
    index = _read_json(prod_root / "living_observation_index.json") or {}
    assessments = index.get("assessments") or {}
    matches: List[Dict[str, Any]] = []
    if isinstance(assessments, dict):
        for meta in assessments.values():
            if isinstance(meta, dict) and meta.get("observation_id") == observation_id:
                matches.append(meta)
    best_payload = None
    best_key = None
    for meta in matches:
        aid = meta.get("assessment_id")
        if not aid:
            continue
        payload = _read_json(prod_root / "daily_assessments" / f"{_safe_id(str(aid))}.json")
        if not payload:
            continue
        key = (
            str(payload.get("assessment_trade_date") or meta.get("trade_date") or ""),
            str(payload.get("assessment_timestamp") or ""),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_payload = payload
    if best_payload:
        return best_payload
    # Fallback: latest matching ledger row, then the JSON file if present.
    rows = [
        r
        for r in _read_jsonl(prod_root / "daily_assessment_ledger.jsonl")
        if r.get("observation_id") == observation_id
    ]
    for row in reversed(rows):
        aid = row.get("assessment_id")
        if not aid:
            continue
        payload = _read_json(prod_root / "daily_assessments" / f"{_safe_id(str(aid))}.json")
        if payload:
            return payload
    return None


def _outcomes_for_observation(prod_root: Path, observation_id: str) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    index = _read_json(prod_root / "living_observation_index.json") or {}
    outcomes = index.get("outcomes") or {}
    candidates: List[str] = []
    if isinstance(outcomes, dict):
        for meta in outcomes.values():
            if isinstance(meta, dict) and meta.get("observation_id") == observation_id:
                oid = meta.get("outcome_record_id")
                if oid:
                    candidates.append(str(oid))
    for row in _read_jsonl(prod_root / "forward_outcome_ledger.jsonl"):
        if row.get("observation_id") == observation_id and row.get("outcome_record_id"):
            candidates.append(str(row["outcome_record_id"]))
    for oid in candidates:
        payload = _read_json(prod_root / "forward_outcomes" / f"{_safe_id(oid)}.json")
        if not payload:
            continue
        horizon = str(payload.get("horizon") or "")
        if horizon:
            found[horizon] = payload
    return found


def _generic_cohort_block(realized: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    keys = (
        "cohort_mean_return",
        "cohort_median_return",
        "cohort_size",
        "positive_fraction",
        "return_field",
    )
    metrics = {k: realized.get(k) for k in keys if k in realized and realized.get(k) is not None}
    if not metrics:
        return None
    return {
        "present": True,
        "label": COHORT_CONTEXT_ONLY,
        "metrics": metrics,
        "adjudicates_proposition": False,
    }


def _claim_aligned_block(realized: Dict[str, Any], contract_status: Optional[str]) -> Dict[str, Any]:
    claim = realized.get("claim_aligned")
    if not isinstance(claim, dict) or not claim:
        return {
            "present": False,
            "adjudication": None,
            "metrics": {},
            "adjudicates_proposition": False,
            "lifecycle_signal": None,
            "reason": None,
            "legacy_status": contract_status,
        }
    return {
        "present": True,
        "adjudication": claim.get("adjudication"),
        "metrics": dict(claim.get("metrics") or {}),
        "adjudicates_proposition": bool(claim.get("adjudicates_proposition")),
        "lifecycle_signal": claim.get("lifecycle_signal") or claim.get("suggested_lifecycle_signal"),
        "reason": claim.get("reason"),
        "legacy_status": claim.get("claim_contract_status") or contract_status,
        "claim_family": claim.get("claim_family"),
        "differential": (
            (claim.get("metrics") or {}).get("signed_high_minus_low_differential")
            if isinstance(claim.get("metrics"), dict)
            else None
        ),
    }


def _forward_schedule(birth: Dict[str, Any], outcomes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    contract_status = _claim_contract_status(birth)
    placeholders = {
        str(h.get("horizon")): h
        for h in (birth.get("forward_horizons") or [])
        if isinstance(h, dict) and h.get("horizon")
    }
    rows: List[Dict[str, Any]] = []
    for horizon in _CANONICAL_FORWARD_HORIZONS:
        placeholder = placeholders.get(horizon) or {}
        outcome = outcomes.get(horizon)
        eval_status = (outcome or {}).get("evaluation_status")
        released = bool(outcome) and str(eval_status) == _EVALUATED
        realized = (outcome or {}).get("realized_outcomes") or {}
        if not isinstance(realized, dict):
            realized = {}
        rows.append(
            {
                "horizon": horizon,
                "eligible_date": placeholder.get("eligible_evaluation_date") or (outcome or {}).get("eligible_evaluation_date"),
                "canonical_birth_status": placeholder.get("status"),
                "evaluation_status": eval_status,
                "release_status": _FORWARD_RELEASE_LABELS.get(str(eval_status), _WAITING),
                "released": released,
                "claim_aligned": _claim_aligned_block(realized, contract_status),
                "generic_cohort": _generic_cohort_block(realized),
                "claim_contract_status": contract_status,
            }
        )
    return rows


def _conclusion(birth: Dict[str, Any], assessment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if assessment and assessment.get("current_epistemic_state"):
        return {
            "epistemic_state": assessment.get("current_epistemic_state"),
            "lifecycle_state": assessment.get("observation_lifecycle_state") or assessment.get("current_lifecycle_status"),
            "research_status": assessment.get("current_research_status"),
            "source": "daily_assessment",
        }
    return {
        "epistemic_state": birth.get("final_epistemic_state"),
        "lifecycle_state": birth.get("lifecycle_outcome"),
        "research_status": birth.get("observation_outcome_kind"),
        "source": "birth" if birth.get("final_epistemic_state") or birth.get("lifecycle_outcome") else None,
    }


def _memory_summary(memory: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not memory or not isinstance(memory.get("families"), dict) or not memory["families"]:
        return {
            "present": False,
            "unavailable_reason": MEMORY_NOT_FORMED,
            "families_known": 0,
            "supported": 0,
            "weakened": 0,
            "falsified": 0,
            "waiting_forward": 0,
            "unresolved": 0,
            "last_memory_update": None,
        }
    families = memory["families"]
    supported = 0
    weakened = 0
    falsified = 0
    unresolved = 0
    waiting_forward = 0
    last_update = None
    for family in families.values():
        if not isinstance(family, dict):
            continue
        state = family.get("last_epistemic_state")
        if state == "SUPPORTED":
            supported += 1
        elif state == "WEAKENED":
            weakened += 1
        elif state == "FALSIFIED":
            falsified += 1
        elif state in ("UNRESOLVED", "INSUFFICIENT_EVIDENCE", None, ""):
            unresolved += 1
        history = family.get("forward_validation_history") or []
        if not history:
            if int(family.get("episode_count") or 0) > 0:
                waiting_forward += 1
        else:
            last = history[-1] if isinstance(history[-1], dict) else {}
            if str(last.get("adjudication") or "") in _PENDING_FORWARD_ADJUDICATIONS:
                waiting_forward += 1
        updated = family.get("updated_at")
        if updated and (last_update is None or str(updated) > str(last_update)):
            last_update = updated
    return {
        "present": True,
        "unavailable_reason": None,
        "families_known": len(families),
        "supported": supported,
        "weakened": weakened,
        "falsified": falsified,
        "waiting_forward": waiting_forward,
        "unresolved": unresolved,
        "last_memory_update": last_update,
    }


def _previous_observation_ids(
    edge_root: Path,
    today_ids: Iterable[str],
    *,
    limit: int = HISTORY_LIMIT,
) -> List[str]:
    today = set(today_ids)
    index = _load_observation_index(edge_root)
    rows = []
    for obs_id, meta in (index.get("observations") or {}).items():
        if obs_id in today:
            continue
        if not isinstance(meta, dict):
            rows.append((str(obs_id), ""))
            continue
        rows.append((str(obs_id), str(meta.get("birth_timestamp") or meta.get("trade_date") or "")))
    rows.sort(key=lambda item: item[1], reverse=True)
    return [obs_id for obs_id, _ in rows[:limit]]


def _build_card(
    observation_id: str,
    *,
    prod_root: Path,
    edge_root: Path,
    memory: Optional[Dict[str, Any]],
    events: List[Dict[str, Any]],
    born_today: bool,
) -> Dict[str, Any]:
    birth = _load_birth(prod_root, observation_id)
    if birth is None:
        return {
            "observation_id": observation_id,
            "available": False,
            "born_in_selected_session": born_today,
            "unavailable_reason": MISSING_DATA,
            "buy_sell_warning": NOT_BUY_SELL,
        }
    session = _load_opr_session(edge_root, birth.get("session_id"))
    selection = _selection_view(_lookup_selection_provenance(observation_id, memory, events, birth))
    feature, outcome, horizon = _feature_outcome_horizon(birth, selection)
    assessment = _latest_assessment(prod_root, observation_id)
    outcomes = _outcomes_for_observation(prod_root, observation_id)
    return {
        "observation_id": observation_id,
        "available": True,
        "born_in_selected_session": born_today,
        "unavailable_reason": None,
        "research_question": birth.get("research_question") or selection.get("selected_question"),
        "feature": feature,
        "outcome": outcome,
        "horizon": horizon,
        "feature_horizon_label": _feature_horizon_label(feature, outcome, horizon),
        "selection": selection,
        "compared_to_known": _compared_to_known(selection),
        "experiments": _build_experiments(birth, session),
        "current_conclusion": _conclusion(birth, assessment),
        "buy_sell_warning": NOT_BUY_SELL,
        "forward": _forward_schedule(birth, outcomes),
        "claim_contract_status": _claim_contract_status(birth),
        "final_epistemic_state": birth.get("final_epistemic_state"),
    }


def build_research_brain_daily_view(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
    history_limit: int = HISTORY_LIMIT,
) -> Dict[str, Any]:
    """
    Pure read-model. Opening / refreshing this view must not create, mutate,
    or evaluate any scientific artifact.
    """
    edge_root = _edge_root(data_dir)
    prod_root = _prod_root(data_dir)
    meta = _latest_successful_run_meta(prod_root, trade_date=trade_date)
    run_id = (meta or {}).get("run_id")
    session_date = (meta or {}).get("target_trade_date")
    run_payload = _read_json(prod_root / "daily_runs" / f"{_safe_id(str(run_id))}.json") if run_id else None
    today_ids = []
    if isinstance(run_payload, dict):
        today_ids = [str(x) for x in (run_payload.get("observations_born") or []) if x]
    memory = _load_memory_store(edge_root)
    events = _load_memory_events(edge_root)
    today_cards = [
        _build_card(
            oid,
            prod_root=prod_root,
            edge_root=edge_root,
            memory=memory,
            events=events,
            born_today=True,
        )
        for oid in today_ids
    ]
    previous_ids = _previous_observation_ids(edge_root, today_ids, limit=history_limit)
    previous_cards = [
        _build_card(
            oid,
            prod_root=prod_root,
            edge_root=edge_root,
            memory=memory,
            events=events,
            born_today=False,
        )
        for oid in previous_ids
    ]
    return {
        "section": "RESEARCH_BRAIN_DAILY",
        "expander_title": RESEARCH_BRAIN_EXPANDER_TITLE,
        "expander_expanded_default": False,
        "view_only": True,
        "requires_streamlit_action": False,
        "scientific_side_effects": False,
        "session_date": session_date,
        "run_id": run_id,
        "today_observation_ids": today_ids,
        "previous_observation_ids": previous_ids,
        "today_cards": today_cards,
        "previous_cards": previous_cards,
        "memory": _memory_summary(memory),
        "missing_label": MISSING_DATA,
        "buy_sell_warning": NOT_BUY_SELL,
        "canonical_root": str(prod_root),
        "edge_data_dir": str(edge_root),
    }


def _experiment_lines(exp: Dict[str, Any]) -> List[str]:
    ordinal = exp.get("ordinal")
    lines = [f"Experiment {ordinal}"]
    if not exp.get("ran") and not any(
        exp.get(k) for k in ("experiment_type", "evidence_interpretation", "epistemic_to", "target_null")
    ):
        lines.append("Chưa được chạy / không có trong artifact")
        return lines
    lines.append(f"Loại: {_display(exp.get('experiment_type'))}")
    lines.append(f"Target/null: {_display(exp.get('target_null'))}")
    lines.append(f"Evidence: {_display(exp.get('evidence_interpretation'))}")
    lines.append(f"Strength: {_display(exp.get('strength'))}")
    if exp.get("epistemic_from") or exp.get("epistemic_to"):
        lines.append(
            f"{_display(exp.get('epistemic_from'))} → {_display(exp.get('epistemic_to'))}"
        )
    else:
        lines.append(f"Chuyển epistemic: {MISSING_DATA}")
    return lines


def _card_text_lines(card: Dict[str, Any]) -> List[str]:
    oid = card.get("observation_id")
    lines = [f"Observation: {oid}"]
    if not card.get("available"):
        lines.append(card.get("unavailable_reason") or MISSING_DATA)
        lines.append(card.get("buy_sell_warning") or NOT_BUY_SELL)
        return lines
    lines.append("A. Câu hỏi nghiên cứu")
    lines.append(_display(card.get("feature_horizon_label")))
    lines.append(_display(card.get("research_question")))
    lines.append("B. Vì sao Brain chọn?")
    selection = card.get("selection") or {}
    if selection.get("available"):
        reasons = selection.get("scientific_reasons") or []
        lines.append("Selection reason: " + (", ".join(reasons) if reasons else MISSING_DATA))
        if selection.get("why_selected"):
            lines.append(str(selection["why_selected"]))
        if selection.get("selected_feature") or selection.get("selected_outcome"):
            lines.append(
                "Selected: "
                f"{_display(selection.get('selected_feature'))} × {_display(selection.get('selected_outcome'))}"
            )
    else:
        lines.append(selection.get("unavailable_reason") or SELECTION_UNSAVED)
    lines.append("C. Hành trình thí nghiệm")
    for exp in card.get("experiments") or []:
        if int(exp.get("ordinal") or 0) > 2:
            continue
        lines.extend(_experiment_lines(exp))
    lines.append("D. Kết luận nghiên cứu hiện tại")
    conclusion = card.get("current_conclusion") or {}
    lines.append(_display(conclusion.get("epistemic_state")))
    lines.append(card.get("buy_sell_warning") or NOT_BUY_SELL)
    lines.append("Forward evidence")
    for row in card.get("forward") or []:
        lines.append(
            f"{row.get('horizon')} — {_display(row.get('eligible_date'))} — {row.get('release_status') or MISSING_DATA}"
        )
        if row.get("released"):
            claim = row.get("claim_aligned") or {}
            if claim.get("legacy_status") == "LEGACY_INSUFFICIENT_CLAIM_SPEC" and not claim.get("adjudicates_proposition"):
                lines.append("LEGACY_INSUFFICIENT_CLAIM_SPEC")
            if claim.get("present"):
                lines.append(f"Claim result: {_display(claim.get('adjudication'))}")
                if claim.get("differential") is not None:
                    lines.append(f"Claim differential: {claim.get('differential')}")
                elif claim.get("metrics"):
                    lines.append(f"Claim metrics: {claim.get('metrics')}")
            generic = row.get("generic_cohort")
            if generic:
                lines.append(COHORT_CONTEXT_ONLY)
                lines.append(f"cohort_mean_return={generic.get('metrics', {}).get('cohort_mean_return')}")
        if row.get("claim_contract_status") == "LEGACY_INSUFFICIENT_CLAIM_SPEC" and not row.get("released"):
            # Birth-level legacy status is still shown so old observations are not retrofitted.
            lines.append("LEGACY_INSUFFICIENT_CLAIM_SPEC")
    compared = card.get("compared_to_known") or {}
    lines.append("So với những gì tôi đã biết")
    if compared.get("available"):
        if compared.get("scientific_reasons"):
            lines.append(", ".join(compared["scientific_reasons"]))
        if compared.get("why_selected"):
            lines.append(str(compared["why_selected"]))
    else:
        lines.append(compared.get("unavailable_reason") or PROVENANCE_INSUFFICIENT)
    return lines


def render_research_brain_text_snapshot(view: Dict[str, Any]) -> str:
    """Deterministic text surface for tests / operator mock (no Streamlit)."""
    lines: List[str] = [
        view.get("expander_title") or RESEARCH_BRAIN_EXPANDER_TITLE,
        "collapsed_default=true",
        "read_only=true",
        f"Session: {view.get('session_date') or MISSING_DATA}",
    ]
    today = view.get("today_cards") or []
    if not today:
        lines.append(MISSING_DATA)
    else:
        for card in today:
            lines.extend(_card_text_lines(card))
    prev_ids = view.get("previous_observation_ids") or []
    if prev_ids:
        lines.append("Previous observations")
        lines.append(", ".join(prev_ids))
    memory = view.get("memory") or {}
    lines.append("Research Memory")
    if memory.get("present"):
        lines.append(f"Families known: {memory.get('families_known', 0)}")
        lines.append(f"Supported: {memory.get('supported', 0)}")
        lines.append(f"Weakened: {memory.get('weakened', 0)}")
        lines.append(f"Falsified: {memory.get('falsified', 0)}")
        lines.append(f"Waiting forward: {memory.get('waiting_forward', 0)}")
        lines.append(f"Unresolved: {memory.get('unresolved', 0)}")
        lines.append(f"Last memory update: {_display(memory.get('last_memory_update'))}")
    else:
        lines.append(memory.get("unavailable_reason") or MEMORY_NOT_FORMED)
    return "\n".join(lines)


def _render_experiment(st: Any, exp: Dict[str, Any]) -> None:
    st.markdown(f"**Experiment {exp.get('ordinal')}**")
    if not exp.get("ran") and not any(
        exp.get(k) for k in ("experiment_type", "evidence_interpretation", "epistemic_to", "target_null")
    ):
        st.caption("Chưa được chạy / không có trong artifact")
        return
    st.markdown(f"- Loại: `{_display(exp.get('experiment_type'))}`")
    st.markdown(f"- Target/null: `{_display(exp.get('target_null'))}`")
    st.markdown(f"- Evidence: `{_display(exp.get('evidence_interpretation'))}`")
    st.markdown(f"- Strength: `{_display(exp.get('strength'))}`")
    if exp.get("epistemic_from") or exp.get("epistemic_to"):
        st.markdown(
            f"- Epistemic: `{_display(exp.get('epistemic_from'))}` → `{_display(exp.get('epistemic_to'))}`"
        )
    else:
        st.markdown(f"- Chuyển epistemic: {MISSING_DATA}")


def _render_card(st: Any, card: Dict[str, Any]) -> None:
    st.markdown(f"**{card.get('observation_id')}**")
    if not card.get("available"):
        st.info(card.get("unavailable_reason") or MISSING_DATA)
        st.caption(card.get("buy_sell_warning") or NOT_BUY_SELL)
        return
    st.markdown("**A. Câu hỏi nghiên cứu**")
    if card.get("feature_horizon_label"):
        st.markdown(f"`{card['feature_horizon_label']}`")
    else:
        st.caption(MISSING_DATA)
    st.markdown(_display(card.get("research_question")))

    st.markdown("**B. Vì sao Brain chọn?**")
    selection = card.get("selection") or {}
    if selection.get("available"):
        reasons = selection.get("scientific_reasons") or []
        st.markdown("Selection reason: " + (", ".join(f"`{r}`" for r in reasons) if reasons else MISSING_DATA))
        if selection.get("why_selected"):
            st.caption(selection["why_selected"])
        if selection.get("selected_feature") or selection.get("selected_outcome"):
            st.markdown(
                "Selected alternative: "
                f"`{_display(selection.get('selected_feature'))}` × `{_display(selection.get('selected_outcome'))}`"
            )
    else:
        st.caption(selection.get("unavailable_reason") or SELECTION_UNSAVED)

    st.markdown("**C. Hành trình thí nghiệm**")
    for exp in card.get("experiments") or []:
        if int(exp.get("ordinal") or 0) > 2:
            continue
        _render_experiment(st, exp)

    st.markdown("**D. Kết luận nghiên cứu hiện tại**")
    conclusion = card.get("current_conclusion") or {}
    st.markdown(f"### `{_display(conclusion.get('epistemic_state'))}`")
    st.warning(card.get("buy_sell_warning") or NOT_BUY_SELL)

    st.markdown("**Forward evidence**")
    for row in card.get("forward") or []:
        st.markdown(
            f"- `{row.get('horizon')}` — {_display(row.get('eligible_date'))} — `{row.get('release_status') or MISSING_DATA}`"
        )
        if row.get("claim_contract_status") == "LEGACY_INSUFFICIENT_CLAIM_SPEC":
            st.caption("LEGACY_INSUFFICIENT_CLAIM_SPEC")
        if not row.get("released"):
            continue
        claim = row.get("claim_aligned") or {}
        if claim.get("present"):
            st.markdown(f"  - Claim result: `{_display(claim.get('adjudication'))}`")
            if claim.get("differential") is not None:
                st.markdown(f"  - Claim differential: `{claim.get('differential')}`")
            if claim.get("lifecycle_signal"):
                st.markdown(f"  - Forward lifecycle: `{claim.get('lifecycle_signal')}`")
        generic = row.get("generic_cohort")
        if generic:
            st.caption(COHORT_CONTEXT_ONLY)
            metrics = generic.get("metrics") or {}
            if "cohort_mean_return" in metrics:
                st.markdown(f"  - cohort_mean_return: `{metrics.get('cohort_mean_return')}`")

    compared = card.get("compared_to_known") or {}
    st.markdown("**So với những gì tôi đã biết**")
    if compared.get("available"):
        if compared.get("scientific_reasons"):
            st.markdown(", ".join(f"`{r}`" for r in compared["scientific_reasons"]))
        if compared.get("why_selected"):
            st.caption(compared["why_selected"])
    else:
        st.caption(compared.get("unavailable_reason") or PROVENANCE_INSUFFICIENT)


def render_research_brain_expander(st: Any, view: Dict[str, Any]) -> None:
    """Collapsed-by-default Streamlit expander. Read-only. No buttons that run research."""
    with st.expander(view.get("expander_title") or RESEARCH_BRAIN_EXPANDER_TITLE, expanded=False):
        st.caption(
            "Quan sát read-only — không chạy discovery, không sinh observation, "
            "không đổi epistemic / BUY/SELL."
        )
        if not view.get("session_date"):
            st.info(MISSING_DATA)
            memory = view.get("memory") or {}
            st.markdown("**Research Memory**")
            st.caption(memory.get("unavailable_reason") or MEMORY_NOT_FORMED)
            return
        today = view.get("today_cards") or []
        previous = view.get("previous_cards") or []
        mode = "Today"
        if previous:
            mode = st.radio(
                "Quan sát",
                ("Today", "Previous observations"),
                horizontal=True,
                key="research_brain_history_mode",
            )
        cards = today if mode == "Today" else previous
        if not cards:
            st.info(MISSING_DATA)
        else:
            for card in cards:
                _render_card(st, card)
                st.markdown("---")
        memory = view.get("memory") or {}
        st.markdown("**Research Memory**")
        if memory.get("present"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Families known", memory.get("families_known", 0))
            c2.metric("Supported", memory.get("supported", 0))
            c3.metric("Falsified", memory.get("falsified", 0))
            c4.metric("Unresolved", memory.get("unresolved", 0))
            st.caption(
                f"Weakened: {memory.get('weakened', 0)} · "
                f"Waiting forward: {memory.get('waiting_forward', 0)} · "
                f"Last memory update: {_display(memory.get('last_memory_update'))}"
            )
        else:
            st.caption(memory.get("unavailable_reason") or MEMORY_NOT_FORMED)


def snapshot_scientific_artifact_hashes(data_dir: Optional[Path] = None) -> Dict[str, str]:
    """
    SHA-256 of existing canonical scientific files. Never creates paths.
    Used to prove UI render leaves artifacts byte-identical.
    """
    edge_root = _edge_root(data_dir)
    hashes: Dict[str, str] = {}
    if not edge_root.exists():
        return hashes
    for path in sorted(edge_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(edge_root).as_posix()
        if not any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in _SCIENTIFIC_RELATIVE_PREFIXES):
            continue
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def scientific_artifact_file_set(data_dir: Optional[Path] = None) -> Tuple[str, ...]:
    return tuple(sorted(snapshot_scientific_artifact_hashes(data_dir)))

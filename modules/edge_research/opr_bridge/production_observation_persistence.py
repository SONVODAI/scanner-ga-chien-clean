"""
Phase 3K.0 — Production research observation persistence (append-only ledger).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.evidence_synthesis_records import new_id, stable_hash
from modules.edge_research.opr_bridge.production_observation_records import (
    LEDGER_VERSION,
    ObservationLedgerEntry,
    ResearchObservationBirthRecord,
)
from modules.edge_research.storage import resolve_data_dir

OBSERVATIONS_DIR = "production_observations"
OBSERVATION_INDEX = "production_observation_index.json"
OBSERVATION_LEDGER = "production_observation_ledger.jsonl"
PERSISTENCE_VERSION = "production_observation_persistence_v1_3k0"


def observations_dir(data_dir: Optional[Path] = None) -> Path:
    root = resolve_data_dir(data_dir)
    path = root / OBSERVATIONS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def observation_birth_path(observation_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = observation_id.replace("/", "_")
    return observations_dir(data_dir) / f"{safe}.json"


def ledger_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / OBSERVATION_LEDGER


def index_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_data_dir(data_dir) / OBSERVATION_INDEX


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def load_observation_index(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = index_path(data_dir)
    if not path.exists():
        return {"version": PERSISTENCE_VERSION, "observations": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_observation_index(index: Dict[str, Any], data_dir: Optional[Path] = None) -> None:
    index["version"] = PERSISTENCE_VERSION
    _atomic_write(index_path(data_dir), json.dumps(index, indent=2, default=str))


def lookup_birth_record(
    observation_id: str,
    data_dir: Optional[Path] = None,
) -> Optional[ResearchObservationBirthRecord]:
    path = observation_birth_path(observation_id, data_dir=data_dir)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _birth_from_dict(payload)


def birth_record_exists(observation_id: str, data_dir: Optional[Path] = None) -> bool:
    return observation_birth_path(observation_id, data_dir=data_dir).exists()


def persist_birth_record(
    birth: ResearchObservationBirthRecord,
    *,
    data_dir: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Path:
    if birth_record_exists(birth.observation_id, data_dir=data_dir) and not allow_overwrite:
        raise ValueError(f"birth_record_immutable:{birth.observation_id}")
    path = observation_birth_path(birth.observation_id, data_dir=data_dir)
    _atomic_write(path, json.dumps(birth.to_dict(), indent=2, default=str))
    index = load_observation_index(data_dir)
    index.setdefault("observations", {})[birth.observation_id] = {
        "observation_id": birth.observation_id,
        "birth_timestamp": birth.birth_timestamp,
        "birth_record_hash": birth.birth_record_hash,
        "research_session_identity_hash": birth.research_session_identity_hash,
        "observation_outcome_kind": birth.observation_outcome_kind,
        "final_epistemic_state": birth.final_epistemic_state,
        "trade_date": birth.cutoff.trade_date,
        "temporal_provenance_hash": birth.cutoff.temporal_provenance_hash,
        "frozen": True,
    }
    save_observation_index(index, data_dir)
    return path


def append_ledger_entry(entry: ObservationLedgerEntry, *, data_dir: Optional[Path] = None) -> None:
    path = ledger_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict(), default=str) + "\n")


def load_ledger_entries(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = ledger_path(data_dir)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def assert_birth_record_immutable(
    observation_id: str,
    *,
    attempted_mutation: Dict[str, Any],
    data_dir: Optional[Path] = None,
) -> bool:
    existing = lookup_birth_record(observation_id, data_dir=data_dir)
    if existing is None:
        return True
    existing_hash = existing.birth_record_hash
    mutated = dict(existing.to_dict())
    mutated.update(attempted_mutation)
    new_hash = stable_hash({k: v for k, v in mutated.items() if k != "birth_record_hash"})
    return new_hash == existing_hash


def build_ledger_entry_from_birth(birth: ResearchObservationBirthRecord) -> ObservationLedgerEntry:
    what = birth.research_question or birth.observation_outcome_kind
    why = birth.stop_reason or birth.termination_reason or birth.observation_outcome_kind
    return ObservationLedgerEntry(
        ledger_entry_id=new_id("obsled"),
        observation_id=birth.observation_id,
        birth_timestamp=birth.birth_timestamp,
        cutoff_timestamp=birth.cutoff.cutoff_timestamp,
        trade_date=birth.cutoff.trade_date,
        what_bot_believed=str(what),
        when_believed=birth.birth_timestamp,
        data_visible_summary={
            "market_data_max_timestamp": birth.cutoff.market_data_max_timestamp,
            "panel_row_count": birth.cutoff.panel_row_count,
            "data_availability_status": birth.cutoff.data_availability_status,
            "temporal_provenance_hash": birth.cutoff.temporal_provenance_hash,
        },
        why_believed=str(why),
        evidence_strength=birth.evidence_strength,
        uncertainty_remaining=birth.unresolved_uncertainties,
        stop_reason=birth.stop_reason,
        pending_horizons=tuple(h.horizon for h in birth.forward_horizons),
        observation_outcome_kind=birth.observation_outcome_kind,
        final_epistemic_state=birth.final_epistemic_state,
        birth_record_hash=birth.birth_record_hash,
        research_session_identity_hash=birth.research_session_identity_hash,
        shadow_authority=birth.shadow_authority.to_dict(),
        record_version=LEDGER_VERSION,
    )


def _birth_from_dict(payload: Dict[str, Any]) -> ResearchObservationBirthRecord:
    from modules.edge_research.opr_bridge.production_observation_records import (
        CohortAttribution,
        ForwardEvaluationContract,
        ForwardHorizonPlaceholder,
        ObservationCutoff,
        ShadowAuthoritySemantics,
    )

    cutoff_d = payload["cutoff"]
    cutoff = ObservationCutoff(
        observation_id=cutoff_d["observation_id"],
        trade_date=cutoff_d["trade_date"],
        cutoff_timestamp=cutoff_d["cutoff_timestamp"],
        timezone=cutoff_d["timezone"],
        data_availability_status=cutoff_d["data_availability_status"],
        market_data_max_timestamp=cutoff_d["market_data_max_timestamp"],
        dataset_identities=tuple(cutoff_d.get("dataset_identities") or []),
        dataset_hashes=tuple(cutoff_d.get("dataset_hashes") or []),
        universe_identity=cutoff_d["universe_identity"],
        universe_hash=cutoff_d["universe_hash"],
        market_context_identity=cutoff_d["market_context_identity"],
        market_context_hash=cutoff_d["market_context_hash"],
        research_policy_hashes=dict(cutoff_d.get("research_policy_hashes") or {}),
        code_identity=cutoff_d["code_identity"],
        panel_row_count=int(cutoff_d.get("panel_row_count", 0)),
        panel_max_trade_date=cutoff_d.get("panel_max_trade_date", ""),
        temporal_provenance_hash=cutoff_d["temporal_provenance_hash"],
    )
    auth_d = payload.get("shadow_authority") or {}
    shadow = ShadowAuthoritySemantics(
        research_only=bool(auth_d.get("research_only", True)),
        trading_authority=bool(auth_d.get("trading_authority", False)),
        buy_signal=bool(auth_d.get("buy_signal", False)),
        sell_signal=bool(auth_d.get("sell_signal", False)),
        edge_active=bool(auth_d.get("edge_active", False)),
    )
    cohort_d = payload.get("cohort_attribution") or {}
    cohort = CohortAttribution(
        attribution_kind=cohort_d.get("attribution_kind", "MARKET_WIDE"),
        population_spec=dict(cohort_d.get("population_spec") or {}),
        symbols_at_birth=tuple(cohort_d.get("symbols_at_birth") or []),
        sector_groups=tuple(cohort_d.get("sector_groups") or []),
        cohort_hash=cohort_d.get("cohort_hash", ""),
    )
    fw_d = payload.get("forward_evaluation_contract") or {}
    criteria = dict(fw_d.get("evaluation_criteria") or {})
    nested_spec = dict(fw_d.get("claim_spec") or criteria.get("claim_spec") or {})
    fw = ForwardEvaluationContract(
        contract_id=fw_d["contract_id"],
        observation_id=fw_d["observation_id"],
        horizons=tuple(fw_d.get("horizons") or []),
        evaluation_criteria=criteria,
        cohort_evaluation_rules=dict(fw_d.get("cohort_evaluation_rules") or {}),
        missing_data_policy=fw_d.get("missing_data_policy", ""),
        contract_hash=fw_d.get("contract_hash", ""),
        record_version=fw_d.get("record_version", "forward_evaluation_contract_v1_3k0"),
        claim_family=fw_d.get("claim_family") or criteria.get("claim_family") or "LEGACY_UNSPECIFIED",
        claim_spec=nested_spec,
        claim_contract_status=(
            fw_d.get("claim_contract_status")
            or criteria.get("claim_contract_status")
            or "LEGACY_INSUFFICIENT_CLAIM_SPEC"
        ),
    )
    horizons = tuple(
        ForwardHorizonPlaceholder(
            horizon=h["horizon"],
            status=h.get("status", "PENDING_FUTURE"),
            eligible_evaluation_date=h.get("eligible_evaluation_date"),
            realized_outcome=h.get("realized_outcome"),
        )
        for h in payload.get("forward_horizons") or []
    )
    return ResearchObservationBirthRecord(
        observation_id=payload["observation_id"],
        birth_timestamp=payload["birth_timestamp"],
        cutoff=cutoff,
        shadow_authority=shadow,
        session_id=payload.get("session_id"),
        proposition_id=payload.get("proposition_id"),
        proposition_hash=payload.get("proposition_hash"),
        research_question=payload.get("research_question"),
        cohort_attribution=cohort,
        observation_outcome_kind=payload.get("observation_outcome_kind", "SILENCE"),
        final_epistemic_state=payload.get("final_epistemic_state"),
        strongest_evidence=payload.get("strongest_evidence"),
        evidence_strength=payload.get("evidence_strength"),
        incremental_evidence_strength=payload.get("incremental_evidence_strength"),
        null_ledger_summary=list(payload.get("null_ledger_summary") or []),
        surviving_nulls=tuple(payload.get("surviving_nulls") or []),
        dependence_warning=payload.get("dependence_warning"),
        contradictions=tuple(payload.get("contradictions") or payload.get("contrictions") or []),
        stop_reason=payload.get("stop_reason"),
        limitations=tuple(payload.get("limitations") or []),
        experiment_count=int(payload.get("experiment_count", 0)),
        research_burden=dict(payload.get("research_burden") or {}),
        rejected_hypotheses=tuple(payload.get("rejected_hypotheses") or []),
        weakened_findings=tuple(payload.get("weakened_findings") or []),
        artifact_warnings=tuple(payload.get("artifact_warnings") or []),
        unresolved_uncertainties=tuple(payload.get("unresolved_uncertainties") or []),
        lifecycle_outcome=payload.get("lifecycle_outcome"),
        termination_reason=payload.get("termination_reason"),
        journey_rows=list(payload.get("journey_rows") or []),
        forward_horizons=horizons,
        forward_evaluation_contract=fw,
        research_session_identity_hash=payload.get("research_session_identity_hash", ""),
        birth_record_hash=payload.get("birth_record_hash", ""),
        observation_mode=payload.get("observation_mode", "PRODUCTION_SHADOW"),
        frozen=bool(payload.get("frozen", True)),
    )

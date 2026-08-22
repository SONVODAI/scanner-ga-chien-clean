"""
Phase 3J.0 — Production OPR lifecycle orchestrator.

Connects frozen Phase 3I transitions to production entry — wiring only.
Does NOT execute new market experiments or modify scientific rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.opr_bridge.lifecycle_dormancy_integration import (
    ResearchOpportunityState,
    integration_content_hash,
    on_research_opportunity_state_changed,
    reconstruct_authoritative_state,
    run_post_synthesis_frontier_pipeline,
    verify_frozen_scientific_integrity,
)
from modules.edge_research.opr_bridge.lifecycle_synthesis_hook import (
    LifecycleKnowledgeState,
    on_epistemic_update_completed,
)
from modules.edge_research.opr_bridge.production_persistence import (
    OprProductionSessionRecord,
    deserialize_knowledge_state,
    lookup_opportunity_session,
    read_opr_session,
    register_opportunity,
    serialize_knowledge_state,
    write_opr_session,
)
from modules.edge_research.opr_bridge.production_trigger import (
    ProductionOpportunityDetection,
    compute_replay_identity,
    detect_production_opportunity,
    new_production_session_id,
)
from modules.edge_research.opr_bridge.real_ledger_adapter import load_real_lifecycle_events
from modules.edge_research.opr_bridge.first_experiment_execution_records import (
    STOP_FIRST_EXPERIMENT_EXECUTED,
)
from modules.edge_research.opr_bridge.first_experiment_interpretation_records import (
    STOP_FIRST_EVIDENCE_INTERPRETED,
)

ORCHESTRATOR_VERSION = "production_opr_orchestrator_v1_3j4"

# Documented STOP boundaries — preserved from Phase 3I
STOP_PROPOSITION_PERSISTED = "STOP_PROPOSITION_PERSISTED"
STOP_ACTION_RECORDED_ONLY = "STOP_ACTION_RECORDED_ONLY"
STOP_NO_AUTO_EXPERIMENT = "STOP_NO_AUTO_EXPERIMENT"
STOP_REOPEN_CANDIDATE_ONLY = "STOP_REOPEN_CANDIDATE_ONLY"
STOP_PACKAGE_NOT_EXECUTED = "STOP_PACKAGE_NOT_EXECUTED"
STOP_FROZEN_LINEAGE_REPLAY = "STOP_FROZEN_LINEAGE_REPLAY"

T2_CANONICAL_PROPOSITION_ID = "prop-efb650d9bd5c451f"
T2_CANONICAL_PROPOSITION_HASH = (
    "c3aab7de80fdb9e56b7be68d517ec0e4792b711ec9772638143df3cfe4e39c9b"
)


@dataclass
class ProductionOprCycleResult:
    orchestrator_version: str = ORCHESTRATOR_VERSION
    outcome: str = "SILENT"
    session_id: Optional[str] = None
    opportunity_identity: Optional[str] = None
    idempotent_skip: bool = False
    detection: Optional[ProductionOpportunityDetection] = None
    session_record: Optional[OprProductionSessionRecord] = None
    authoritative_state: Optional[Dict[str, Any]] = None
    stop_boundaries: List[str] = field(default_factory=list)
    frozen_integrity: Optional[Dict[str, Any]] = None
    first_experiment: Optional[Dict[str, Any]] = None
    first_experiment_interpretation: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orchestrator_version": self.orchestrator_version,
            "outcome": self.outcome,
            "session_id": self.session_id,
            "opportunity_identity": self.opportunity_identity,
            "idempotent_skip": self.idempotent_skip,
            "detection": self.detection.to_dict() if self.detection else None,
            "authoritative_state": self.authoritative_state,
            "stop_boundaries": list(self.stop_boundaries),
            "frozen_integrity": self.frozen_integrity,
            "first_experiment": self.first_experiment,
            "first_experiment_interpretation": self.first_experiment_interpretation,
            "error": self.error,
        }


def _load_frozen_t2_events_if_matching(proposition_id: str) -> Optional[List[Dict[str, Any]]]:
    if proposition_id != T2_CANONICAL_PROPOSITION_ID:
        return None
    prop, events = load_real_lifecycle_events()
    if prop.get("proposition_id") != proposition_id:
        return None
    return events


def _replay_frozen_lineage_to_dormancy(
    prop: Dict[str, Any],
    state: LifecycleKnowledgeState,
) -> Dict[str, Any]:
    """Replay stored authoritative events through synthesis → frontier → dormancy."""
    from modules.edge_research.opr_bridge.scientific_action_context import ExecutabilityContext

    events = _load_frozen_t2_events_if_matching(prop["proposition_id"])
    if not events:
        raise ValueError("No frozen lineage available for proposition")

    for event in events:
        state, _outcome = on_epistemic_update_completed(
            prop,
            event["epistemic_update"],
            event.get("experiment_spec", {}),
            event.get("experiment_ref", ""),
            event.get("tool_result_hash", ""),
            interpretation=event.get("interpretation"),
            lineage_metadata=event.get("lineage_metadata"),
            knowledge_state=state,
            deterministic_replay=True,
        )

    cutoff = prop["observation_provenance"]["evidence_anchor"]["data_cutoff_date"]
    ex = ExecutabilityContext.real_partition_default(data_cutoff=cutoff)
    last_outcome = state.outcomes[-1]
    pipeline = run_post_synthesis_frontier_pipeline(
        prop, state, last_outcome, executability=ex
    )
    return {
        "pipeline": {
            "frontier_decision": pipeline.frontier.frontier_decision.value,
            "research_activity_state": pipeline.research_activity_state,
            "epistemic_state": pipeline.epistemic_state,
        },
        "authoritative_state": reconstruct_authoritative_state(state),
    }


def run_production_opr_cycle(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
    data_dir: Optional[Path] = None,
    replay_frozen_lineage: bool = False,
    reopening_opportunity: Optional[ResearchOpportunityState] = None,
    execute_first_experiment: bool = False,
    interpret_first_experiment: bool = False,
) -> ProductionOprCycleResult:
    """
    Production-facing OPR cycle: detect → idempotency → persist → optional first-experiment execution/interpretation.

    When execute_first_experiment=True, runs 3J.2 selection then 3J.3 execution.
    When interpret_first_experiment=True (requires execution), runs 3J.4 evidence interpretation.
    Does NOT generate research decisions or invoke synthesis hooks.
    """
    result = ProductionOprCycleResult()
    result.frozen_integrity = verify_frozen_scientific_integrity()

    detection = detect_production_opportunity(panel, data_cutoff_date=data_cutoff_date)
    result.detection = detection

    if detection.outcome != "OPPORTUNITY_DETECTED":
        result.outcome = detection.outcome
        result.stop_boundaries.append(STOP_NO_AUTO_EXPERIMENT)
        return result

    assert detection.opportunity_identity is not None
    assert detection.proposition_record is not None
    result.opportunity_identity = detection.opportunity_identity

    existing = lookup_opportunity_session(detection.opportunity_identity, data_dir=data_dir)
    if existing:
        record = read_opr_session(existing, data_dir=data_dir)
        result.outcome = "NO_NEW_RESEARCH_OPPORTUNITY"
        result.session_id = existing
        result.idempotent_skip = True
        result.session_record = record
        from modules.edge_research.opr_bridge.production_persistence import (
            reconstruct_session_authoritative_state as _recon_persisted,
        )

        result.authoritative_state = _recon_persisted(record)
        result.stop_boundaries = list(record.stop_boundaries_reached)
        if execute_first_experiment and record.first_experiment_execution:
            result.first_experiment = {
                "package": record.initial_experiment_package,
                "execution": record.first_experiment_execution,
                "idempotent_replay": True,
            }
            if STOP_FIRST_EXPERIMENT_EXECUTED not in result.stop_boundaries:
                result.stop_boundaries.append(STOP_FIRST_EXPERIMENT_EXECUTED)
        if interpret_first_experiment and record.first_experiment_interpretation:
            result.first_experiment_interpretation = record.first_experiment_interpretation
            if STOP_FIRST_EVIDENCE_INTERPRETED not in result.stop_boundaries:
                result.stop_boundaries.append(STOP_FIRST_EVIDENCE_INTERPRETED)
        return result

    session_id = new_production_session_id(detection.proposition_id or "unknown")
    replay_id = compute_replay_identity(detection.opportunity_identity, session_id)
    state = LifecycleKnowledgeState(detection.proposition_id or "")
    stop_boundaries = [STOP_PROPOSITION_PERSISTED, STOP_NO_AUTO_EXPERIMENT]

    lineage_replay: Optional[Dict[str, Any]] = None
    if replay_frozen_lineage:
        events = _load_frozen_t2_events_if_matching(detection.proposition_id or "")
        if events:
            lineage_replay = _replay_frozen_lineage_to_dormancy(detection.proposition_record, state)
            stop_boundaries.extend([STOP_FROZEN_LINEAGE_REPLAY, STOP_ACTION_RECORDED_ONLY, STOP_PACKAGE_NOT_EXECUTED])
            result.authoritative_state = lineage_replay["authoritative_state"]
        else:
            result.error = "replay_frozen_lineage requested but no matching frozen lineage"
            result.outcome = "REPLAY_UNAVAILABLE"
            return result
    else:
        result.authoritative_state = {
            "proposition_id": detection.proposition_id,
            "proposition_hash": detection.proposition_hash,
            "research_activity_state": "ACTIVE",
            "evidence_event_count": 0,
        }

    if reopening_opportunity is not None and state.is_dormant():
        hook = on_research_opportunity_state_changed(
            detection.proposition_record,
            state,
            reopening_opportunity,
        )
        stop_boundaries.append(STOP_REOPEN_CANDIDATE_ONLY)
        if hook.evaluation_result:
            result.authoritative_state = reconstruct_authoritative_state(state)
            result.authoritative_state["reopening_outcome"] = hook.evaluation_result.outcome.value

    record = OprProductionSessionRecord(
        session_id=session_id,
        opportunity_identity=detection.opportunity_identity,
        replay_identity=replay_id,
        proposition_id=detection.proposition_id or "",
        proposition_hash=detection.proposition_hash or "",
        data_cutoff_date=data_cutoff_date,
        evidence_cutoff_hash=detection.evidence_cutoff_hash or "",
        research_activity_state=state.research_activity_state,
        proposition_record=detection.proposition_record,
        knowledge_state=serialize_knowledge_state(state),
        stop_boundaries_reached=stop_boundaries,
        lineage_artifacts=["real_ledger_adapter"] if lineage_replay else [],
    )

    write_opr_session(record, data_dir=data_dir)
    register_opportunity(detection.opportunity_identity, session_id, data_dir=data_dir)

    if execute_first_experiment and detection.proposition_record:
        from modules.edge_research.opr_bridge.production_first_experiment_execution import (
            run_production_first_experiment_execution,
        )

        fx = run_production_first_experiment_execution(
            detection.proposition_record,
            panel,
            session_id=session_id,
            data_cutoff_date=data_cutoff_date,
            data_dir=data_dir,
        )
        record.initial_experiment_package = fx.package_dict
        if fx.execution and fx.execution.envelope:
            record.first_experiment_execution = fx.execution.envelope.to_dict()
        if fx.frozen_contract_ref:
            record.frozen_interpretation_contract = fx.frozen_contract_ref
        stop_boundaries.append(STOP_FIRST_EXPERIMENT_EXECUTED)
        write_opr_session(record, data_dir=data_dir)
        result.first_experiment = fx.to_dict()

        if interpret_first_experiment and record.first_experiment_execution and record.frozen_interpretation_contract:
            from modules.edge_research.opr_bridge.production_first_experiment_interpretation import (
                run_production_first_experiment_interpretation,
            )

            ix = run_production_first_experiment_interpretation(
                detection.proposition_record,
                session_id=session_id,
                package_dict=record.initial_experiment_package or {},
                execution_dict=record.first_experiment_execution,
                frozen_contract_dict=record.frozen_interpretation_contract,
                data_dir=data_dir,
            )
            if ix.interpretation and ix.interpretation.envelope:
                record.first_experiment_interpretation = ix.interpretation.envelope.to_dict()
                record.first_experiment_epistemic_update = ix.interpretation.envelope.epistemic_update
            stop_boundaries.append(STOP_FIRST_EVIDENCE_INTERPRETED)
            write_opr_session(record, data_dir=data_dir)
            result.first_experiment_interpretation = ix.to_dict()

    result.outcome = "SESSION_CREATED"
    result.session_id = session_id
    result.session_record = record
    result.stop_boundaries = stop_boundaries
    return result


def simulate_process_restart(
    session_id: str,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Cold restart reconstruction from durable storage only."""
    from modules.edge_research.opr_bridge.production_persistence import (
        reconstruct_session_authoritative_state,
    )

    record = read_opr_session(session_id, data_dir=data_dir)
    state = deserialize_knowledge_state(record.knowledge_state) if record.knowledge_state else None
    auth = reconstruct_session_authoritative_state(record)
    return {
        "session_id": session_id,
        "record_hash": record.record_hash(),
        "authoritative_state": auth,
        "evidence_event_count": len(state.evidence_events) if state else 0,
        "research_activity_state": record.research_activity_state,
    }


def list_documented_stop_boundaries() -> List[Dict[str, str]]:
    return [
        {"code": STOP_PROPOSITION_PERSISTED, "description": "After proposition birth; no auto experiment"},
        {"code": STOP_ACTION_RECORDED_ONLY, "description": "After synthesis priority; no auto execution (3I.13)"},
        {"code": STOP_NO_AUTO_EXPERIMENT, "description": "No new ToolResult in 3J.0 production cycle"},
        {"code": STOP_REOPEN_CANDIDATE_ONLY, "description": "Reopening records REOPEN_CANDIDATE only (3I.19/20)"},
        {"code": STOP_PACKAGE_NOT_EXECUTED, "description": "Action package boundary preserved (3I.16/17)"},
        {"code": STOP_FROZEN_LINEAGE_REPLAY, "description": "Historical events replayed from artifacts only"},
        {"code": STOP_FIRST_EXPERIMENT_EXECUTED, "description": "First experiment executed; auditable ToolResult persisted (3J.3)"},
        {"code": STOP_FIRST_EVIDENCE_INTERPRETED, "description": "First experiment evidence interpreted; EpistemicUpdate persisted (3J.4)"},
    ]

"""
Phase 3K.0 — Trading system isolation audit for production research observation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Tuple

FORBIDDEN_IMPORT_FRAGMENTS = (
    "market_first",
    "earning",
    "sweetspot",
    "position_guardian",
    "final_decision_engine",
    "leader_memory",
    "regime_alpha",
    "shadow_observation_board",
)

FORBIDDEN_WRITE_PATHS = (
    "data/earning_learning/",
    "brain/ai_recommendation",
    "buy_elite",
)

OBSERVATION_MODULES = (
    "production_research_observation.py",
    "production_observation_records.py",
    "production_observation_cutoff.py",
    "production_observation_persistence.py",
    "production_observation_narrative.py",
    "production_observation_isolation.py",
    "production_living_observation_records.py",
    "production_living_observation_persistence.py",
    "production_market_delta.py",
    "production_forward_outcome_evaluator.py",
    "production_observation_lifecycle.py",
    "production_daily_assessment.py",
    "production_daily_voice.py",
    "production_living_read_model.py",
    "production_living_research_observation.py",
    "production_daily_run_records.py",
    "production_trading_session_eligibility.py",
    "production_data_readiness_gate.py",
    "production_forward_clock.py",
    "production_daily_run_persistence.py",
    "production_daily_run_observability.py",
    "production_daily_manifest.py",
    "production_scheduling_contract.py",
    "production_notification_contract.py",
    "production_daily_run_orchestrator.py",
    "production_daily_run_entrypoint.py",
    "production_calibration_records.py",
    "production_forward_evidence_eligibility.py",
    "production_pre_outcome_snapshot.py",
    "production_calibration_cohorts.py",
    "production_calibration_ledger_persistence.py",
    "production_calibration_engine.py",
    "production_calibration_updater.py",
    "production_calibration_self_knowledge.py",
    "production_calibration_simulation.py",
    "production_living_research_ui_records.py",
    "production_living_research_ui_read_model.py",
    "production_living_research_ui.py",
)


def audit_observation_imports(repo_root: Path) -> List[Tuple[str, str]]:
    root = repo_root / "modules/edge_research/opr_bridge"
    hits: List[Tuple[str, str]] = []
    for name in OBSERVATION_MODULES:
        path = root / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for frag in FORBIDDEN_IMPORT_FRAGMENTS:
                        if frag in alias.name.lower():
                            hits.append((name, alias.name))
            if isinstance(node, ast.ImportFrom) and node.module:
                for frag in FORBIDDEN_IMPORT_FRAGMENTS:
                    if frag in node.module.lower():
                        hits.append((name, node.module))
    return hits


def audit_observation_write_paths(repo_root: Path) -> List[Tuple[str, str]]:
    root = repo_root / "modules/edge_research/opr_bridge"
    hits: List[Tuple[str, str]] = []
    skip = {"production_observation_isolation.py"}
    for name in OBSERVATION_MODULES:
        if name in skip:
            continue
        path = root / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        blob = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_WRITE_PATHS:
            if forbidden in blob and any(
                isinstance(node, (ast.Call, ast.Constant))
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and forbidden in str(node.value)
            ):
                hits.append((name, forbidden))
    return hits


def run_trading_isolation_audit(repo_root: Path) -> Dict[str, Any]:
    import_hits = audit_observation_imports(repo_root)
    write_hits = audit_observation_write_paths(repo_root)
    return {
        "passed": not import_hits and not write_hits,
        "import_hits": [{"module": m, "target": t} for m, t in import_hits],
        "write_hits": [{"module": m, "path": p} for m, p in write_hits],
        "modules_audited": list(OBSERVATION_MODULES),
    }

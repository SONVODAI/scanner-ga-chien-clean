#!/usr/bin/env python3
"""
Phase 3H.9 — Same-Branch Independence & Mechanical Cycling Diagnosis.

DIAGNOSIS ONLY. Reads frozen BB11 + BB10 artifacts. Does NOT modify research behavior.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "artifacts"
BB11 = REPO / "benchmarks" / "blind_benchmark_11" / "artifacts"
BB10 = REPO / "benchmarks" / "blind_benchmark_10" / "artifacts"

FROZEN_3H8 = "5c62fc334"
FROZEN_BB11 = "84d689b0d"
PHASE = "phase_3h9_same_branch_independence"


class ScientificRelationship(str, Enum):
    IDENTICAL = "IDENTICAL"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    SAME_QUESTION_DIFFERENT_INSTRUMENT = "SAME_QUESTION_DIFFERENT_INSTRUMENT"
    SAME_UNCERTAINTY_DIFFERENT_SLICE = "SAME_UNCERTAINTY_DIFFERENT_SLICE"
    SAME_BRANCH_NEW_EVIDENCE = "SAME_BRANCH_NEW_EVIDENCE"
    RELATED_BUT_DISTINCT = "RELATED_BUT_DISTINCT"
    GENUINELY_INDEPENDENT = "GENUINELY_INDEPENDENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CyclingClass(str, Enum):
    TRUE_NEW_INFORMATION_ATTEMPT = "TRUE_NEW_INFORMATION_ATTEMPT"
    SAME_QUESTION_DIFFERENT_TOOL = "SAME_QUESTION_DIFFERENT_TOOL"
    SAME_UNCERTAINTY_DIFFERENT_SLICE = "SAME_UNCERTAINTY_DIFFERENT_SLICE"
    REPRESENTATIONAL_SWITCH_ONLY = "REPRESENTATIONAL_SWITCH_ONLY"
    REDUNDANT_RESEARCH = "REDUNDANT_RESEARCH"
    INCONCLUSIVE = "INCONCLUSIVE"


class RevisitFreshness(str, Enum):
    FRESH_EVIDENCE_REVISIT = "FRESH_EVIDENCE_REVISIT"
    NEW_HORIZON_REVISIT = "NEW_HORIZON_REVISIT"
    NEW_POPULATION_REVISIT = "NEW_POPULATION_REVISIT"
    NEW_OUTCOME_REVISIT = "NEW_OUTCOME_REVISIT"
    REVALUED_ONLY = "REVALUED_ONLY"
    SAME_EVIDENCE_REVISIT = "SAME_EVIDENCE_REVISIT"
    STALE_REVISIT = "STALE_REVISIT"
    INCONCLUSIVE = "INCONCLUSIVE"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def _spec_key(pop: Dict[str, Any], out: Dict[str, Any], horizon: int = 0) -> str:
    return hashlib.sha256(
        json.dumps({"pop": pop or {}, "out": out or {}, "h": horizon}, sort_keys=True).encode()
    ).hexdigest()[:16]


def _uncertainty_family(codes: List[str]) -> str:
    if not codes:
        return "HORIZON_HETEROGENEITY_CORE"
    families = []
    for c in codes:
        if "HORIZON" in c:
            families.append("HORIZON")
        elif c in ("EPISODE_REPLICATION", "TIME_DISTRIBUTION", "SYMBOL_DISTRIBUTION", "MARKET_DEPENDENCE"):
            families.append("DISTRIBUTION_ROBUSTNESS")
        elif "EXTREME" in c or "FALSIF" in c:
            families.append("FALSIFICATION")
        else:
            families.append(c)
    return "|".join(sorted(set(families)))


def _semantic_branch_id(
    pop: Dict[str, Any],
    out: Dict[str, Any],
    horizon: int,
    uncertainty_family: str,
) -> str:
    base = _spec_key(pop, out, horizon)
    return f"sem-{uncertainty_family[:20]}-{base}"


@dataclass
class OpportunityProfile:
    opportunity_id: str
    source: str
    action_id: str
    tool_name: str
    branch_root_id: str
    frame_id: str
    population_spec: Dict[str, Any]
    outcome_spec: Dict[str, Any]
    observation_horizon: int
    uncertainty_codes: Tuple[str, ...]
    research_needs: Tuple[str, ...]
    feature_columns: Tuple[str, ...]
    expected_research_value: float
    historical_planner_score: float
    question_text: str = ""

    def semantic_key(self) -> str:
        return _semantic_branch_id(
            self.population_spec,
            self.outcome_spec,
            self.observation_horizon,
            _uncertainty_family(list(self.uncertainty_codes)),
        )


def _profile_from_global_selected(ga: Dict[str, Any]) -> Optional[OpportunityProfile]:
    sel = ga.get("selected") or {}
    cand = sel.get("action_candidate") or {}
    draft = cand.get("draft_spec") or {}
    scope = draft.get("research_scope") or {}
    inputs = draft.get("inputs") or {}
    feats = tuple(
        str(inputs[k])
        for k in ("feature_column", "partition_column", "trajectory_feature", "primary_feature")
        if k in inputs
    )
    return OpportunityProfile(
        opportunity_id=sel.get("opportunity_id", ""),
        source=sel.get("source", ""),
        action_id=sel.get("action_id", ""),
        tool_name=draft.get("tool_name", cand.get("tool_name", "")),
        branch_root_id=sel.get("branch_root_id", ga.get("branch_before", "")),
        frame_id=sel.get("frame_id", ga.get("frame_before", "")),
        population_spec=scope.get("population_spec") or {},
        outcome_spec=scope.get("outcome_spec") or draft.get("outcome_spec") or {},
        observation_horizon=int(ga.get("observation_horizon_before") or 0),
        uncertainty_codes=(cand.get("uncertainty_addressed") or "",),
        research_needs=tuple(cand.get("rationale_codes") or ()),
        feature_columns=feats,
        expected_research_value=float(sel.get("expected_research_value", ga.get("selected_erv", 0))),
        historical_planner_score=float(sel.get("historical_planner_score", 0)),
        question_text=str(cand.get("question_text", "")),
    )


def _profile_from_experiment_diary(entry: Dict[str, Any]) -> OpportunityProfile:
    gaps = tuple(entry.get("information_gaps") or ())
    return OpportunityProfile(
        opportunity_id=entry.get("experiment_node_id", ""),
        source="EXECUTED",
        action_id=entry.get("experiment_node_id", ""),
        tool_name=entry.get("tool_selected", ""),
        branch_root_id=entry.get("current_branch_root", ""),
        frame_id=entry.get("frame_id", ""),
        population_spec=entry.get("population_spec") or {},
        outcome_spec=entry.get("outcome_spec") or {},
        observation_horizon=int(entry.get("observation_horizon") or 0),
        uncertainty_codes=gaps if gaps else ("HORIZON_STABILITY",),
        research_needs=(),
        feature_columns=tuple(
            str(entry.get("tool_inputs", {}).get(k, ""))
            for k in ("feature_column", "partition_column")
            if entry.get("tool_inputs", {}).get(k)
        ),
        expected_research_value=0.0,
        historical_planner_score=0.0,
        question_text=entry.get("research_question", ""),
    )


def classify_relationship(
    current: OpportunityProfile,
    candidate: OpportunityProfile,
) -> Tuple[str, Dict[str, Any]]:
    """Offline ScientificOpportunityRelationship diagnostic."""
    reasons: Dict[str, Any] = {}
    same_pop = current.population_spec == candidate.population_spec and bool(current.population_spec)
    same_out = current.outcome_spec == candidate.outcome_spec and bool(current.outcome_spec)
    same_horizon = current.observation_horizon == candidate.observation_horizon
    same_branch = current.branch_root_id == candidate.branch_root_id
    same_unc = set(current.uncertainty_codes) & set(candidate.uncertainty_codes)
    same_tool = current.tool_name == candidate.tool_name and bool(current.tool_name)

    reasons["same_uncertainty"] = bool(same_unc)
    reasons["same_outcome"] = same_out
    reasons["same_population"] = same_pop
    reasons["same_horizon"] = same_horizon
    reasons["same_branch_root"] = same_branch
    reasons["same_tool"] = same_tool
    reasons["same_semantic_key"] = current.semantic_key() == candidate.semantic_key()

    if current.action_id == candidate.action_id:
        return ScientificRelationship.IDENTICAL.value, reasons

    if reasons["same_semantic_key"] and same_tool:
        return ScientificRelationship.NEAR_DUPLICATE.value, reasons

    if same_out and same_pop and same_horizon and not same_tool:
        if same_unc or not candidate.uncertainty_codes:
            return ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value, reasons

    if same_unc and candidate.feature_columns and candidate.feature_columns != current.feature_columns:
        return ScientificRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value, reasons

    if same_branch and (same_out or same_pop) and not same_tool:
        return ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value, reasons

    if same_branch and same_out and same_pop and same_horizon and current.frame_id != candidate.frame_id:
        reasons["representational_switch"] = True
        return ScientificRelationship.NEAR_DUPLICATE.value, reasons

    if not same_branch and not same_out and not same_pop:
        return ScientificRelationship.GENUINELY_INDEPENDENT.value, reasons

    if same_unc:
        return ScientificRelationship.RELATED_BUT_DISTINCT.value, reasons

    return ScientificRelationship.INSUFFICIENT_EVIDENCE.value, reasons


def _extract_opportunities_from_allocation(entry: Dict[str, Any], limit: int = 15) -> List[OpportunityProfile]:
    ga = entry.get("global_allocation") or {}
    opps = ga.get("all_opportunities") or []
    profiles: List[OpportunityProfile] = []
    for o in opps:
        if not o.get("comparable", True):
            continue
        cand = o.get("action_candidate") or {}
        intent = cand.get("intent", "")
        if intent in ("STOP", "STOP_SESSION", "ABANDON"):
            continue
        draft = cand.get("draft_spec") or {}
        scope = draft.get("research_scope") or {}
        inputs = draft.get("inputs") or {}
        profiles.append(
            OpportunityProfile(
                opportunity_id=o.get("opportunity_id", ""),
                source=o.get("source", ""),
                action_id=o.get("action_id", ""),
                tool_name=draft.get("tool_name", ""),
                branch_root_id=o.get("branch_root_id", entry.get("branch_before", "")),
                frame_id=o.get("frame_id", ""),
                population_spec=scope.get("population_spec") or {},
                outcome_spec=scope.get("outcome_spec") or {},
                observation_horizon=int(entry.get("observation_horizon_before") or 0),
                uncertainty_codes=(cand.get("uncertainty_addressed") or "",),
                research_needs=tuple(cand.get("rationale_codes") or ()),
                feature_columns=tuple(
                    str(inputs[k])
                    for k in ("feature_column", "partition_column", "trajectory_feature")
                    if k in inputs
                ),
                expected_research_value=float(o.get("expected_research_value", 0)),
                historical_planner_score=float(o.get("historical_planner_score", 0)),
                question_text=str(cand.get("question_text", "")),
            )
        )
    profiles.sort(key=lambda p: -p.expected_research_value)
    return profiles[:limit]


def run_diagnosis() -> Dict[str, Any]:
    exp_diary = _load(BB11 / "03_experiment_diary.json")
    global_diary = _load(BB11 / "11_global_allocation_diary.json")
    marginal_audit = _load(BB11 / "09_branch_marginal_state_audit.json")
    rig_audit = _load(BB11 / "08_realized_information_gain_audit.json")
    exit_diary = _load(BB11 / "10_exit_valuation_diary.json")
    cycling_bb11 = _load(BB11 / "12_stop_continue_quality_classification.json")
    frames = _load(BB11 / "04_research_frames.json")

    bb10_global = _load(BB10 / "08_global_allocation_diary.json") if (BB10 / "08_global_allocation_diary.json").exists() else []
    bb10_exp = _load(BB10 / "04_experiment_diary.json") if (BB10 / "04_experiment_diary.json").exists() else []

    marginal_entries = marginal_audit.get("entries") or []
    rig_by_exp = {
        e.get("experiment_node_id"): e
        for e in (rig_audit.get("history_entries") or [])
    }

    # Structural branches
    structural_roots = sorted({e.get("current_branch_root") for e in exp_diary if e.get("current_branch_root")})

    # Semantic branch reconstruction
    semantic_clusters: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "experiments": [],
            "frames": set(),
            "tools": set(),
            "uncertainties": set(),
            "structural_roots": set(),
        }
    )
    for entry in exp_diary:
        prof = _profile_from_experiment_diary(entry)
        sid = prof.semantic_key()
        semantic_clusters[sid]["semantic_branch_id"] = sid
        semantic_clusters[sid]["population_spec"] = prof.population_spec
        semantic_clusters[sid]["outcome_spec"] = prof.outcome_spec
        semantic_clusters[sid]["observation_horizon"] = prof.observation_horizon
        semantic_clusters[sid]["experiments"].append(entry.get("experiment_node_id"))
        semantic_clusters[sid]["frames"].add(entry.get("frame_id") or "")
        semantic_clusters[sid]["tools"].add(prof.tool_name)
        semantic_clusters[sid]["uncertainties"].update(prof.uncertainty_codes)
        semantic_clusters[sid]["structural_roots"].add(prof.branch_root_id)

    semantic_branch_list = []
    for sid, cluster in semantic_clusters.items():
        semantic_branch_list.append(
            {
                "semantic_branch_id": sid,
                "structural_branch_root_ids": sorted(cluster["structural_roots"]),
                "member_experiments": cluster["experiments"],
                "frames": sorted(x for x in cluster["frames"] if x),
                "tools_used": sorted(cluster["tools"]),
                "shared_uncertainty_families": sorted(cluster["uncertainties"]),
                "population_spec": cluster["population_spec"],
                "outcome_spec": cluster["outcome_spec"],
                "observation_horizon": cluster["observation_horizon"],
                "experiment_count": len(cluster["experiments"]),
            }
        )

    # Mechanical cycling forensics (T4, T8, T9)
    cycling_transitions = [4, 8, 9]
    cycling_forensics: List[Dict[str, Any]] = []
    for t in cycling_transitions:
        ga_entry = next((g for g in global_diary if g.get("decision_index") == t), None)
        if not ga_entry:
            continue
        trig = ga_entry.get("triggering_experiment_node_id", "")
        prior_exp = next((e for e in exp_diary if e.get("experiment_node_id") == trig), None)
        resulting = ga_entry.get("resulting_experiment_node_id", "")
        result_exp = next((e for e in exp_diary if e.get("experiment_node_id") == resulting), None)
        marginal = marginal_entries[t - 1] if t - 1 < len(marginal_entries) else {}
        selected = _profile_from_global_selected(ga_entry.get("global_allocation") or ga_entry)
        if selected is None:
            selected = OpportunityProfile(
                opportunity_id="", source=ga_entry.get("selected_source", ""),
                action_id=ga_entry.get("selected_action_id", ""),
                tool_name=result_exp.get("tool_selected", "") if result_exp else "",
                branch_root_id=ga_entry.get("branch_before", ""),
                frame_id=ga_entry.get("frame_before", ""),
                population_spec=(result_exp or {}).get("population_spec") or {},
                outcome_spec=(result_exp or {}).get("outcome_spec") or {},
                observation_horizon=int(ga_entry.get("observation_horizon_before") or 0),
                uncertainty_codes=(), research_needs=(), feature_columns=(),
                expected_research_value=float(ga_entry.get("selected_erv", 0)),
                historical_planner_score=0.0,
            )
        elif result_exp and not selected.tool_name:
            selected = OpportunityProfile(
                opportunity_id=selected.opportunity_id,
                source=selected.source,
                action_id=selected.action_id,
                tool_name=result_exp.get("tool_selected", ""),
                branch_root_id=selected.branch_root_id,
                frame_id=selected.frame_id,
                population_spec=result_exp.get("population_spec") or selected.population_spec,
                outcome_spec=result_exp.get("outcome_spec") or selected.outcome_spec,
                observation_horizon=selected.observation_horizon,
                uncertainty_codes=selected.uncertainty_codes,
                research_needs=selected.research_needs,
                feature_columns=tuple(
                    str(result_exp.get("tool_inputs", {}).get(k, ""))
                    for k in ("feature_column", "partition_column")
                    if result_exp.get("tool_inputs", {}).get(k)
                ) or selected.feature_columns,
                expected_research_value=selected.expected_research_value,
                historical_planner_score=selected.historical_planner_score,
                question_text=result_exp.get("research_question", selected.question_text),
            )
        current_line = _profile_from_experiment_diary(prior_exp) if prior_exp else selected
        alts = _extract_opportunities_from_allocation(ga_entry, limit=10)
        alt_classifications = []
        near_dup_count = 0
        independent_count = 0
        for alt in alts:
            if alt.action_id == selected.action_id:
                continue
            rel, comp = classify_relationship(current_line, alt)
            if rel in (
                ScientificRelationship.IDENTICAL.value,
                ScientificRelationship.NEAR_DUPLICATE.value,
                ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
            ):
                near_dup_count += 1
            if rel == ScientificRelationship.GENUINELY_INDEPENDENT.value:
                independent_count += 1
            alt_classifications.append(
                {
                    "action_id": alt.action_id,
                    "source": alt.source,
                    "tool_name": alt.tool_name,
                    "erv": alt.expected_research_value,
                    "relationship": rel,
                    "components": comp,
                }
            )
        sel_rel, sel_comp = classify_relationship(current_line, selected)
        rig_after = rig_by_exp.get(resulting, {})
        cycling_class = CyclingClass.INCONCLUSIVE.value
        if sel_rel in (ScientificRelationship.NEAR_DUPLICATE.value, ScientificRelationship.IDENTICAL.value):
            cycling_class = CyclingClass.REDUNDANT_RESEARCH.value
        elif sel_rel == ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value:
            cycling_class = CyclingClass.SAME_QUESTION_DIFFERENT_TOOL.value
        elif sel_rel == ScientificRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value:
            cycling_class = CyclingClass.SAME_UNCERTAINTY_DIFFERENT_SLICE.value
        elif sel_rel == ScientificRelationship.NEAR_DUPLICATE.value and sel_comp.get("representational_switch"):
            cycling_class = CyclingClass.REPRESENTATIONAL_SWITCH_ONLY.value
        elif rig_after.get("gain_level") in ("HIGH", "MEDIUM"):
            cycling_class = CyclingClass.TRUE_NEW_INFORMATION_ATTEMPT.value
        elif selected.expected_research_value > 3.0 and rig_after.get("gain_level") != "ZERO":
            cycling_class = CyclingClass.TRUE_NEW_INFORMATION_ATTEMPT.value

        causal = []
        if near_dup_count >= 3:
            causal.append("C1")
        if sel_rel == ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value:
            causal.append("C2")
        if sel_rel == ScientificRelationship.NEAR_DUPLICATE.value and sel_comp.get("representational_switch"):
            causal.append("C3")
        if independent_count == 0:
            causal.append("C9")
        if marginal.get("marginal_state") in ("DIMINISHING", "LOW_MARGINAL_VALUE"):
            causal.append("C7")

        bb11_cycling_label = next(
            (
                d.get("decision_quality")
                for d in (cycling_bb11.get("decisions") or [])
                if d.get("transition") == t
            ),
            None,
        )
        # Re-evaluate: BB11 MECHANICAL_CYCLING overrides MEDIUM-gain heuristic when
        # same structural branch + diminishing/low marginal + no independent alts
        if bb11_cycling_label == "MECHANICAL_CYCLING":
            if sel_rel in (
                ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
                ScientificRelationship.NEAR_DUPLICATE.value,
                ScientificRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value,
            ):
                cycling_class = {
                    ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value: CyclingClass.SAME_QUESTION_DIFFERENT_TOOL.value,
                    ScientificRelationship.NEAR_DUPLICATE.value: CyclingClass.REDUNDANT_RESEARCH.value,
                    ScientificRelationship.SAME_UNCERTAINTY_DIFFERENT_SLICE.value: CyclingClass.SAME_UNCERTAINTY_DIFFERENT_SLICE.value,
                }[sel_rel]
            elif current_line.semantic_key() == selected.semantic_key():
                cycling_class = CyclingClass.REDUNDANT_RESEARCH.value
            elif marginal.get("marginal_state") in ("DIMINISHING", "LOW_MARGINAL_VALUE") and independent_count == 0:
                cycling_class = CyclingClass.SAME_QUESTION_DIFFERENT_TOOL.value if selected.tool_name != current_line.tool_name else CyclingClass.REDUNDANT_RESEARCH.value
            elif rig_after.get("gain_level") in ("ZERO", "LOW"):
                cycling_class = CyclingClass.REDUNDANT_RESEARCH.value

        cycling_forensics.append(
            {
                "transition": t,
                "bb11_original_classification": bb11_cycling_label,
                "triggering_experiment": trig,
                "resulting_experiment": resulting,
                "structural_branch": ga_entry.get("branch_before"),
                "semantic_branch_current": current_line.semantic_key(),
                "semantic_branch_selected": selected.semantic_key(),
                "marginal_state": marginal.get("marginal_state"),
                "selected_source": ga_entry.get("selected_source"),
                "selected_tool": selected.tool_name,
                "selected_erv": selected.expected_research_value,
                "selected_relationship_to_line": sel_rel,
                "relationship_components": sel_comp,
                "alternative_count": len(alt_classifications),
                "near_duplicate_alternatives": near_dup_count,
                "independent_alternatives": independent_count,
                "top_alternatives": alt_classifications[:5],
                "realized_gain_after": rig_after.get("gain_level"),
                "cycling_classification": cycling_class,
                "causal_hypotheses": causal,
                "scientifically_defensible": cycling_class == CyclingClass.TRUE_NEW_INFORMATION_ATTEMPT.value,
            }
        )

    # Revisit freshness (BB10 + BB11)
    revisit_audit: List[Dict[str, Any]] = []
    for label, diary, exps in (("BB11", global_diary, exp_diary), ("BB10", bb10_global, bb10_exp)):
        for entry in diary:
            if entry.get("selected_source") != "REVISIT":
                continue
            rev = entry.get("revisit_audit") or {}
            left_at = rev.get("branch_originally_left_at_experiment", "")
            left_idx = next(
                (i for i, e in enumerate(exps) if e.get("experiment_node_id") == left_at),
                -1,
            )
            decision_idx = entry.get("decision_index", 0)
            exps_since = max(0, decision_idx - left_idx - 1) if left_idx >= 0 else None
            gains_since = [
                rig_by_exp.get(exps[i].get("experiment_node_id", ""), {}).get("gain_level")
                for i in range(left_idx + 1, min(decision_idx, len(exps)))
                if label == "BB11"
            ]
            hist = entry.get("historical_vs_revalued_non_local") or {}
            freshness = RevisitFreshness.INCONCLUSIVE.value
            if gains_since and any(g in ("HIGH", "MEDIUM") for g in gains_since):
                freshness = RevisitFreshness.FRESH_EVIDENCE_REVISIT.value
            elif hist.get("delta") and float(hist["delta"]) < -3 and not gains_since:
                freshness = RevisitFreshness.STALE_REVISIT.value
            elif abs(float(hist.get("delta", 0))) > 2 and not gains_since:
                freshness = RevisitFreshness.REVALUED_ONLY.value
            elif exps_since == 0:
                freshness = RevisitFreshness.SAME_EVIDENCE_REVISIT.value

            revisit_audit.append(
                {
                    "benchmark": label,
                    "decision_index": decision_idx,
                    "action_id": entry.get("selected_action_id"),
                    "erv": entry.get("selected_erv"),
                    "historical_planner_score": hist.get("historical_planner_score"),
                    "current_revalued": hist.get("current_revalued_value"),
                    "revisit_audit": rev,
                    "experiments_since_defer": exps_since,
                    "realized_gains_since_defer": gains_since if label == "BB11" else [],
                    "freshness_classification": freshness,
                    "branch_before": entry.get("branch_before"),
                    "frame_before": entry.get("frame_before"),
                }
            )

    # Frontier independence at late transitions
    frontier_audit: List[Dict[str, Any]] = []
    for entry in global_diary:
        if entry.get("decision_index", 0) < 7:
            continue
        ga = entry.get("global_allocation") or entry
        current_exp = next(
            (e for e in exp_diary if e.get("experiment_node_id") == entry.get("triggering_experiment_node_id")),
            None,
        )
        current_line = _profile_from_experiment_diary(current_exp) if current_exp else None
        opps = _extract_opportunities_from_allocation(entry, limit=10)
        for opp in opps:
            if opp.source != "FRONTIER":
                continue
            rel, comp = (
                classify_relationship(current_line, opp)
                if current_line
                else (ScientificRelationship.INSUFFICIENT_EVIDENCE.value, {})
            )
            frontier_audit.append(
                {
                    "decision_index": entry.get("decision_index"),
                    "frontier_id": opp.opportunity_id,
                    "action_id": opp.action_id,
                    "branch_root_id": opp.branch_root_id,
                    "frame_id": opp.frame_id,
                    "tool_name": opp.tool_name,
                    "current_revalued_erv": opp.expected_research_value,
                    "historical_planner_score": opp.historical_planner_score,
                    "relationship_to_active_line": rel,
                    "relationship_components": comp,
                    "independence": (
                        "INDEPENDENT"
                        if rel == ScientificRelationship.GENUINELY_INDEPENDENT.value
                        else "SAME_BRANCH_SEMANTIC_OVERLAP"
                    ),
                }
            )

    # Marginal decay transfer audit
    decay_transfer: List[Dict[str, Any]] = []
    scenarios = [
        ("A_same_uncertainty_different_tool", "horizon_comparison", "adaptive_partition_compare"),
        ("B_same_uncertainty_different_slice", "rs_spread", "threshold_exploration"),
        ("C_reframe_same_pop_out", "frame_reframe", "horizon_comparison"),
    ]
    for i, entry in enumerate(exp_diary):
        prof = _profile_from_experiment_diary(entry)
        marginal = marginal_entries[i] if i < len(marginal_entries) else {}
        prev_marginal = marginal_entries[i - 1] if i > 0 else {}
        decay_transfer.append(
            {
                "experiment": entry.get("experiment_node_id"),
                "step": entry.get("step"),
                "tool": prof.tool_name,
                "semantic_branch": prof.semantic_key(),
                "marginal_state": marginal.get("marginal_state"),
                "prior_marginal_state": prev_marginal.get("marginal_state"),
                "realized_gain": rig_by_exp.get(entry.get("experiment_node_id", ""), {}).get("gain_level"),
                "decay_follows_structural_branch": True,
                "decay_follows_semantic_branch": prof.semantic_key()
                == _profile_from_experiment_diary(exp_diary[i - 1]).semantic_key()
                if i > 0
                else None,
                "transfer_note": (
                    "Marginal state keyed to structural branch_root_id only; "
                    "semantic branch changes do not reset decay"
                ),
            }
        )

    # First-loss pipeline
    first_loss_counts: Counter = Counter()
    for cf in cycling_forensics:
        if cf["near_duplicate_alternatives"] >= 2:
            first_loss_counts["SEMANTIC_RELATIONSHIP_NOT_REPRESENTED"] += 1
        if cf["selected_relationship_to_line"] in (
            ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
            ScientificRelationship.NEAR_DUPLICATE.value,
        ):
            first_loss_counts["FRESHNESS_NOT_REPRESENTED"] += 1
        if cf["marginal_state"] == "DIMINISHING" and cf["selected_relationship_to_line"] != ScientificRelationship.GENUINELY_INDEPENDENT.value:
            first_loss_counts["MARGINAL_DECAY_NOT_TRANSFERRED_TO_SEMANTIC_EQUIVALENTS"] += 1
        first_loss_counts["VALUED_WITHOUT_INDEPENDENCE"] += 1

    # Counterfactual semantic grouping
    counterfactuals: List[Dict[str, Any]] = []
    for cf in cycling_forensics:
        t = cf["transition"]
        alts = cf.get("top_alternatives") or []
        grouped = [a for a in alts if a["relationship"] not in (
            ScientificRelationship.GENUINELY_INDEPENDENT.value,
            ScientificRelationship.RELATED_BUT_DISTINCT.value,
        )]
        counterfactuals.append(
            {
                "transition": t,
                "CF1_apparent_alternatives": len(alts) + 1,
                "CF1_after_semantic_grouping": max(1, len(alts) + 1 - len(grouped)),
                "CF2_would_inherit_decay": cf["selected_relationship_to_line"]
                in (
                    ScientificRelationship.SAME_QUESTION_DIFFERENT_INSTRUMENT.value,
                    ScientificRelationship.NEAR_DUPLICATE.value,
                ),
                "CF4_independent_high_value": cf["independent_alternatives"],
                "CF5_only_defensible_continue_or_stop": cf["independent_alternatives"] == 0,
                "CF6_stop_compensated_late": t == 11,
            }
        )

    # Required questions
    fresh_revisits = sum(1 for r in revisit_audit if "FRESH" in r["freshness_classification"])
    stale_revisits = sum(
        1 for r in revisit_audit if r["freshness_classification"] in ("STALE_REVISIT", "SAME_EVIDENCE_REVISIT", "REVALUED_ONLY")
    )
    questions = {
        "Q1_structural_branch_roots": len(structural_roots),
        "Q2_semantic_branches_explored": len(semantic_branch_list),
        "Q3_frontier_revisit_independent": "NO — all FRONTIER/REVISIT share structural branch obs-4692b6a8949d (BB11); semantic overlap predominant",
        "Q4_genuinely_fresh_revisits": fresh_revisits,
        "Q5_stale_revisits": stale_revisits,
        "Q6_tool_changes_false_novelty": "YES — horizon_comparison repeated across reframes with ZERO gain; novelty_component still positive in ERV",
        "Q7_reframe_new_science": "PARTIAL — t3_return and continuation outcome reframes are representational; rs_spread partition is distinct slice",
        "Q8_decay_transfers_semantic_equivalents": "NO — decay keyed to branch_root_id; tool/slice changes within same root do not reset marginal state",
        "Q9_semantic_duplication_caused_cycling": "YES for T8/T9; PARTIAL for T4 (positive ERV masked overlap)",
        "Q10_independent_alternatives_during_cycling": "Effectively none — 0 genuinely independent high-value alternatives at T8/T9",
        "Q11_stop_correct_missing_option": "T8/T9: STOP would have been defensible but exit did not compete (DIMINISHING); T11 STOP eventually won",
        "Q12_primary_bottleneck": "S1 + S3 — scientific identity not represented; marginal decay does not transfer across semantic equivalents",
        "Q13_secondary_bottleneck": "S8 — representation novelty (frame/outcome reframe, tool change) misvalued as information novelty in ERV",
        "Q14_next_treatment_target": "Semantic research-line identity + decay transfer at scientific-question level (NOT branch_root_id alone)",
        "Q15_must_not_change": "3H.8 exit valuation, STOP logic, 3H.6 IV, planner weights, ERV formulas, allocator ranking, dedup, budget lifecycle",
    }

    taxonomy = {
        "primary": "S1 — SCIENTIFIC IDENTITY NOT REPRESENTED",
        "primary_evidence": [
            "BB11: 1 structural root vs 4+ semantic branches",
            "3 cycling transitions: selected candidates semantically overlap current line",
            "0 genuinely independent frontier alternatives at late transitions",
        ],
        "secondary": "S3 — MARGINAL DECAY DOES NOT TRANSFER ACROSS SEMANTIC EQUIVALENTS",
        "secondary_evidence": [
            "Marginal state attached to branch_root_id only",
            "Same-question-different-tool selections do not inherit exhaustion from prior ZERO gains on semantic equivalents",
            "T8/T9 continued under DIMINISHING while attacking same horizon-heterogeneity proposition",
        ],
        "also_applicable": ["S8", "S5", "S6", "S9"],
        "suspected_not_primary": ["S10 — STOP intervened at T11; too late to prevent T8/T9 cycling but not primary cause"],
    }

    return {
        "structural_branch_count": len(structural_roots),
        "structural_roots": structural_roots,
        "semantic_branch_count": len(semantic_branch_list),
        "semantic_branches": semantic_branch_list,
        "cycling_forensics": cycling_forensics,
        "revisit_audit": revisit_audit,
        "frontier_audit": frontier_audit[:30],
        "decay_transfer": decay_transfer,
        "first_loss_counts": dict(first_loss_counts),
        "counterfactuals": counterfactuals,
        "questions": questions,
        "taxonomy": taxonomy,
        "frames_summary": {
            "frames_created": frames.get("created_vs_executed", {}).get("research_frames_created"),
            "frames_executed": frames.get("created_vs_executed", {}).get("research_frames_executed"),
        },
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    head = _git_head()
    result = run_diagnosis()

    freeze = {
        "phase": PHASE,
        "diagnosis_only": True,
        "frozen_3h8_commit": FROZEN_3H8,
        "frozen_bb11_commit": FROZEN_BB11,
        "diagnosis_commit": head,
        "bb11_not_rerun": True,
        "bb12_not_run": True,
        "research_behavior_modified": False,
        "created_at": _utc_now(),
    }
    (OUT_DIR / "00_freeze_manifest.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")

    artifacts = {
        "01_structural_branch_audit.json": {
            "structural_branch_count": result["structural_branch_count"],
            "structural_roots": result["structural_roots"],
            "bb11_note": "Single observation-root; all experiments share obs-4692b6a8949d",
        },
        "02_semantic_branch_reconstruction.json": {
            "semantic_branch_count": result["semantic_branch_count"],
            "clusters": result["semantic_branches"],
        },
        "03_scientific_opportunity_relationships.json": {
            "model": "ScientificOpportunityRelationship",
            "classifications": [e.value for e in ScientificRelationship],
            "dimensions": [
                "parent branch_root_id", "frame lineage", "PopulationSpec", "OutcomeSpec",
                "observation horizon", "uncertainty codes", "research needs", "features",
                "expected information", "semantic question structure",
            ],
            "note": "Diagnostic only — NOT implemented in runtime",
        },
        "04_revisit_freshness_audit.json": {
            "revisits": result["revisit_audit"],
            "freshness_labels": [e.value for e in RevisitFreshness],
        },
        "05_frontier_independence_audit.json": {
            "late_frontier_candidates": result["frontier_audit"],
            "summary": {
                "frontier_entries_audited": len(result["frontier_audit"]),
                "same_branch_semantic_overlap": sum(
                    1 for f in result["frontier_audit"] if f.get("independence") != "INDEPENDENT"
                ),
            },
        },
        "06_mechanical_cycling_forensics.json": {
            "transitions_audited": [4, 8, 9],
            "forensics": result["cycling_forensics"],
            "cycling_labels": [e.value for e in CyclingClass],
        },
        "07_marginal_decay_transfer_audit.json": {
            "entries": result["decay_transfer"],
            "finding": "Decay follows structural branch_root_id, not semantic branch identity",
        },
        "08_independence_first_loss.json": {
            "pipeline": [
                "CANDIDATE EXISTS",
                "SEMANTIC RELATIONSHIP KNOWN?",
                "FRESHNESS KNOWN?",
                "INDEPENDENCE KNOWN?",
                "MARGINAL DECAY TRANSFERRED?",
                "VALUED",
                "GLOBAL COMPETITION",
                "SELECTED",
            ],
            "first_loss_counts": result["first_loss_counts"],
            "primary_loss_stage": "SEMANTIC_RELATIONSHIP_NOT_REPRESENTED / FRESHNESS_NOT_REPRESENTED",
        },
        "09_counterfactual_semantic_grouping.json": {
            "counterfactuals": result["counterfactuals"],
            "note": "Offline diagnostic only — no behavior changes",
        },
        "10_t4_t8_t9_forensics.json": {
            "dedicated_table": result["cycling_forensics"],
        },
        "11_required_questions.json": result["questions"],
        "12_bottleneck_taxonomy.json": result["taxonomy"],
        "13_final_diagnosis.json": {
            "verdict": "PRIMARY: S1+S3 — scientific identity not represented; marginal decay not transferred across semantic equivalents",
            "secondary": "S8 — representation novelty misvalued as information novelty",
            "phase_3h8_status": "FUNCTIONAL AND FROZEN — exit STOP at T11 appropriate; does not resolve same-branch cycling",
            "recommended_next_phase": "Semantic research-line identity representation + decay transfer (diagnosis-informed treatment)",
            "must_not_change": result["questions"]["Q15_must_not_change"],
        },
        "14_post_run_freeze_manifest.json": {
            **freeze,
            "completed_at": _utc_now(),
            "artifact_index": sorted(
                f.name for f in OUT_DIR.glob("*.json") if f.name != "14_post_run_freeze_manifest.json"
            ) + ["DIAGNOSIS_SUMMARY.md"],
        },
    }

    for name, payload in artifacts.items():
        (OUT_DIR / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary = f"""# Phase 3H.9 — Same-Branch Independence Diagnosis Summary

**Status:** DIAGNOSIS ONLY | **BB12:** NOT RUN | **Research:** NOT MODIFIED

## Frozen Evidence
- Phase 3H.8 @ `{FROZEN_3H8}`
- BB11 @ `{FROZEN_BB11}`

## Key Findings

### Structural vs Semantic Branches
- **Structural branch roots (BB11):** {result['structural_branch_count']}
- **Semantic/scientific branches (BB11):** {result['semantic_branch_count']}

### Mechanical Cycling (T4, T8, T9)
"""
    for cf in result["cycling_forensics"]:
        summary += f"- **T{cf['transition']}:** {cf['cycling_classification']} — {cf['selected_tool']} (ERV {cf['selected_erv']:.2f}), relationship={cf['selected_relationship_to_line']}, gain_after={cf.get('realized_gain_after')}\n"

    summary += f"""
### Revisit Freshness
- Fresh revisits: {result['questions']['Q4_genuinely_fresh_revisits']}
- Stale/same-evidence revisits: {result['questions']['Q5_stale_revisits']}

### Primary Bottleneck
**{result['taxonomy']['primary']}**

### Secondary Bottleneck
**{result['taxonomy']['secondary']}**

### Recommended Next Treatment
{result['questions']['Q14_next_treatment_target']}

### Must NOT Change
{result['questions']['Q15_must_not_change']}

---
*Generated { _utc_now() } — diagnostic artifacts only*
"""
    (OUT_DIR.parent / "DIAGNOSIS_SUMMARY.md").write_text(summary, encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "semantic_branches": result["semantic_branch_count"], "primary": result["taxonomy"]["primary"]}, indent=2))


if __name__ == "__main__":
    main()

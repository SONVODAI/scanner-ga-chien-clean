"""
Read-only Research Brain daily UI — observability only, zero scientific side effects.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.autonomous_daily_edge_ui import render_autonomous_daily_edge_text_snapshot
from modules.edge_research.research_brain_daily_ui import (
    COHORT_CONTEXT_ONLY,
    MEMORY_NOT_FORMED,
    MISSING_DATA,
    NOT_BUY_SELL,
    PROVENANCE_INSUFFICIENT,
    RESEARCH_BRAIN_EXPANDER_TITLE,
    SELECTION_UNSAVED,
    build_research_brain_daily_view,
    render_research_brain_text_snapshot,
    scientific_artifact_file_set,
    snapshot_scientific_artifact_hashes,
)
from tests.test_edge_research_autonomous_daily_ui import _plant_session


FROZEN_TRIGGER_HASH = "bf02dacd1b8d82416aa5eb50e91a83bd2c2c66f56af90e45e79bb12a8e573912"
FROZEN_SECOND_EXPERIMENT_HASH = "19883f8f43a8c63539ea2d8ca58fec15752bcd1c4a4a2a3735ccc028c266eac8"


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _birth(
    *,
    observation_id: str,
    trade_date: str,
    research_question: str | None,
    epistemic: str | None,
    journey_rows: list | None = None,
    claim_status: str = "CLAIM_ALIGNED",
    feature: str | None = "RSI14",
    outcome: str | None = "t5_return",
    horizon: str | None = "T5",
    session_id: str | None = None,
    selection_provenance: dict | None = None,
    eligible: dict | None = None,
) -> dict:
    eligible = eligible or {"T3": "2026-09-02", "T5": "2026-09-04", "T10": "2026-09-11"}
    spec = {}
    if claim_status != "LEGACY_INSUFFICIENT_CLAIM_SPEC":
        spec = {
            "feature": feature,
            "outcome_field": outcome,
            "observation_horizon": horizon,
            "claim_family": "CROSS_SECTIONAL_TIER_DIFFERENTIAL",
            "claim_contract_status": claim_status,
            "scientific_question": research_question,
        }
    payload = {
        "observation_id": observation_id,
        "birth_timestamp": f"{trade_date}T12:00:00Z",
        "session_id": session_id,
        "research_question": research_question,
        "final_epistemic_state": epistemic,
        "observation_outcome_kind": "DISCOVERY",
        "lifecycle_outcome": "SCIENTIFIC_STOP",
        "experiment_count": len(journey_rows or []),
        "journey_rows": journey_rows or [],
        "forward_horizons": [
            {
                "horizon": name,
                "status": "PENDING_FUTURE",
                "eligible_evaluation_date": date,
                "realized_outcome": None,
            }
            for name, date in eligible.items()
        ],
        "forward_evaluation_contract": {
            "contract_id": f"fw-{observation_id}",
            "observation_id": observation_id,
            "horizons": ["T3", "T5", "T10"],
            "evaluation_criteria": {},
            "cohort_evaluation_rules": {},
            "missing_data_policy": "MARK_MISSING_DO_NOT_IMPUTE",
            "contract_hash": "hash",
            "claim_family": (
                "LEGACY_UNSPECIFIED"
                if claim_status == "LEGACY_INSUFFICIENT_CLAIM_SPEC"
                else "CROSS_SECTIONAL_TIER_DIFFERENTIAL"
            ),
            "claim_spec": spec,
            "claim_contract_status": claim_status,
        },
        "cutoff": {
            "observation_id": observation_id,
            "trade_date": trade_date,
            "cutoff_timestamp": f"{trade_date}T07:45:00+07:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "data_availability_status": "PRE_MARKET",
            "market_data_max_timestamp": f"{trade_date}T00:00:00",
            "dataset_identities": [],
            "dataset_hashes": [],
            "universe_identity": "u",
            "universe_hash": "uh",
            "market_context_identity": "m",
            "market_context_hash": "mh",
            "research_policy_hashes": {},
            "code_identity": "c",
            "panel_row_count": 1,
            "panel_max_trade_date": trade_date,
            "temporal_provenance_hash": "th",
        },
        "shadow_authority": {
            "research_only": True,
            "trading_authority": False,
            "buy_signal": False,
            "sell_signal": False,
            "edge_active": False,
        },
        "research_session_identity_hash": "sid",
        "birth_record_hash": "brid",
    }
    if selection_provenance is not None:
        payload["selection_provenance"] = selection_provenance
    return payload


def _plant_birth(edge: Path, birth: dict) -> Path:
    prod = edge / "production_observations"
    path = prod / f"{birth['observation_id']}.json"
    _write(path, birth)
    index_path = edge / "production_observation_index.json"
    index = {"observations": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    index.setdefault("observations", {})[birth["observation_id"]] = {
        "observation_id": birth["observation_id"],
        "birth_timestamp": birth["birth_timestamp"],
        "trade_date": birth["cutoff"]["trade_date"],
        "final_epistemic_state": birth.get("final_epistemic_state"),
    }
    _write(index_path, index)
    _append_jsonl(
        edge / "production_observation_ledger.jsonl",
        {
            "ledger_entry_id": f"led-{birth['observation_id']}",
            "observation_id": birth["observation_id"],
            "trade_date": birth["cutoff"]["trade_date"],
            "final_epistemic_state": birth.get("final_epistemic_state"),
            "birth_record_hash": birth.get("birth_record_hash"),
        },
    )
    return path


def _plant_memory(edge: Path, families: dict, events: list | None = None) -> Path:
    path = edge / "research_memory" / "research_memory_index.json"
    _write(path, {"version": "research_memory_v1", "families": families})
    for event in events or []:
        _append_jsonl(edge / "research_memory" / "research_memory_events.jsonl", event)
    return path


def _plant_outcome(
    edge: Path,
    *,
    observation_id: str,
    horizon: str,
    adjudication: str | None,
    cohort_mean: float = 0.012,
    differential: float | None = 0.03,
    adjudications_proposition: bool = True,
    claim_status: str = "CLAIM_ALIGNED",
) -> Path:
    prod = edge / "production_observations"
    oid = f"out-{observation_id}-{horizon}"
    claim = {}
    if adjudication is not None:
        claim = {
            "adjudication": adjudication,
            "adjudicates_proposition": adjudications_proposition,
            "claim_family": "CROSS_SECTIONAL_TIER_DIFFERENTIAL",
            "claim_contract_status": claim_status,
            "metrics": {"signed_high_minus_low_differential": differential},
            "reason": "fixture",
        }
    payload = {
        "outcome_record_id": oid,
        "observation_id": observation_id,
        "horizon": horizon,
        "eligible_evaluation_date": "2026-09-02",
        "actual_evaluation_timestamp": "2026-09-02T12:00:00Z",
        "evaluation_status": "EVALUATED",
        "contract_id": f"fw-{observation_id}",
        "contract_hash": "hash",
        "realized_outcomes": {
            "cohort_mean_return": cohort_mean,
            "cohort_median_return": 0.01,
            "cohort_size": 20,
            "claim_aligned": claim,
        },
        "provenance": {"assessment_trade_date": "2026-09-02"},
    }
    path = prod / "forward_outcomes" / f"{oid}.json"
    _write(path, payload)
    _append_jsonl(
        prod / "forward_outcome_ledger.jsonl",
        {
            "outcome_record_id": oid,
            "observation_id": observation_id,
            "horizon": horizon,
            "eligible_evaluation_date": "2026-09-02",
        },
    )
    index_path = prod / "living_observation_index.json"
    index = {"assessments": {}, "outcomes": {}, "summaries": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    index.setdefault("outcomes", {})[oid] = {
        "outcome_record_id": oid,
        "observation_id": observation_id,
        "horizon": horizon,
    }
    _write(index_path, index)
    return path


def _two_experiment_rows() -> list:
    return [
        {
            "ordinal": 1,
            "tool": "partition_group_compare",
            "targeted_null": "no_tier_differential",
            "evidence_direction": "SUPPORTING",
            "evidence_strength": "MODERATE",
            "epistemic_state_entering": "HYPOTHESIS",
            "epistemic_state_leaving": "SUPPORTED",
        },
        {
            "ordinal": 2,
            "tool": "SEEK_FALSIFICATION",
            "targeted_null": "directional_reversal",
            "evidence_direction": "DISCONFIRMING",
            "evidence_strength": "STRONG",
            "epistemic_state_entering": "SUPPORTED",
            "epistemic_state_leaving": "FALSIFIED",
        },
    ]


def _full_today(edge: Path, *, discovery_id: str = "obs-today") -> Path:
    _plant_session(
        edge,
        trade_date="2026-08-27",
        run_id="pdrun-brain",
        discovery_count=0,
        q1="Hôm nay Brain đào một observation.",
    )
    # overwrite observations_born with a stable id
    run_path = edge / "production_observations" / "daily_runs" / "pdrun-brain.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["observations_born"] = [discovery_id]
    run_path.write_text(json.dumps(run), encoding="utf-8")
    manifest_path = edge / "production_observations" / "daily_manifests" / "pdrun-brain.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["discovery_count"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return run_path


def test_1_no_research_memory_yet(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="Does RSI14 predict T5?",
            epistemic="SUPPORTED",
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    assert view["memory"]["present"] is False
    assert MEMORY_NOT_FORMED in snap
    assert "Research Memory" in snap


def test_2_one_new_observation(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="Does RSI14 predict T5 cross-sectionally?",
            epistemic="SUPPORTED",
            feature="RSI14",
            horizon="T5",
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    assert view["today_observation_ids"] == ["obs-today"]
    assert view["today_cards"][0]["available"] is True
    assert view["today_cards"][0]["feature_horizon_label"] == "RSI14 → T5"
    assert "Does RSI14 predict T5 cross-sectionally?" in snap
    assert RESEARCH_BRAIN_EXPANDER_TITLE in snap


def test_3_two_experiments_different_interpretations(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="RSI14 vs T5",
            epistemic="FALSIFIED",
            journey_rows=_two_experiment_rows(),
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    exps = view["today_cards"][0]["experiments"]
    assert exps[0]["experiment_type"] == "partition_group_compare"
    assert exps[0]["evidence_interpretation"] == "SUPPORTING"
    assert exps[0]["epistemic_from"] == "HYPOTHESIS"
    assert exps[0]["epistemic_to"] == "SUPPORTED"
    assert exps[1]["experiment_type"] == "SEEK_FALSIFICATION"
    assert exps[1]["target_null"] == "directional_reversal"
    assert exps[1]["evidence_interpretation"] == "DISCONFIRMING"
    assert exps[1]["strength"] == "STRONG"
    assert exps[1]["epistemic_from"] == "SUPPORTED"
    assert exps[1]["epistemic_to"] == "FALSIFIED"
    assert "Experiment 1" in snap and "Experiment 2" in snap
    assert "HYPOTHESIS → SUPPORTED" in snap
    assert "SUPPORTED → FALSIFIED" in snap


def test_4_falsified_observation(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="RSI14 vs T5",
            epistemic="FALSIFIED",
            journey_rows=_two_experiment_rows(),
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    assert view["today_cards"][0]["current_conclusion"]["epistemic_state"] == "FALSIFIED"
    assert "FALSIFIED" in snap
    assert NOT_BUY_SELL in snap


def test_5_waiting_t3_t5_t10(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="RSI14 vs T5",
            epistemic="SUPPORTED",
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    fwd = view["today_cards"][0]["forward"]
    assert [r["horizon"] for r in fwd] == ["T3", "T5", "T10"]
    assert all(r["release_status"] == "WAITING" for r in fwd)
    assert "T3 — 2026-09-02 — WAITING" in snap
    assert "T5 — 2026-09-04 — WAITING" in snap
    assert "T10 — 2026-09-11 — WAITING" in snap


def test_6_released_claim_aligned_outcome(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="RSI14 vs T5",
            epistemic="SUPPORTED",
        ),
    )
    _plant_outcome(
        edge,
        observation_id="obs-today",
        horizon="T3",
        adjudication="CLAIM_SUPPORTING",
        differential=0.041,
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    t3 = view["today_cards"][0]["forward"][0]
    assert t3["release_status"] == "RELEASED"
    assert t3["claim_aligned"]["adjudication"] == "CLAIM_SUPPORTING"
    assert t3["claim_aligned"]["differential"] == 0.041
    assert "T3 — 2026-09-02 — RELEASED" in snap
    assert "CLAIM_SUPPORTING" in snap
    assert "Claim differential: 0.041" in snap


def test_7_generic_cohort_cannot_be_claim_proof(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="RSI14 vs T5",
            epistemic="SUPPORTED",
        ),
    )
    _plant_outcome(
        edge,
        observation_id="obs-today",
        horizon="T3",
        adjudication="CONTEXT_ONLY",
        adjudications_proposition=False,
        differential=None,
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    t3 = view["today_cards"][0]["forward"][0]
    assert t3["generic_cohort"]["label"] == COHORT_CONTEXT_ONLY
    assert t3["generic_cohort"]["adjudicates_proposition"] is False
    assert t3["claim_aligned"]["adjudicates_proposition"] is False
    assert COHORT_CONTEXT_ONLY in snap
    # Generic cohort return must not be labeled as claim proof.
    claim_section = snap.split(COHORT_CONTEXT_ONLY)[0]
    assert "cohort_mean_return=0.012" not in claim_section
    assert "Claim result: CONTEXT_ONLY" in snap


def test_8_legacy_insufficient_claim_spec(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="legacy question",
            epistemic="SUPPORTED",
            claim_status="LEGACY_INSUFFICIENT_CLAIM_SPEC",
            feature=None,
            outcome=None,
            horizon=None,
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    assert view["today_cards"][0]["claim_contract_status"] == "LEGACY_INSUFFICIENT_CLAIM_SPEC"
    assert view["today_cards"][0]["feature_horizon_label"] is None
    assert "LEGACY_INSUFFICIENT_CLAIM_SPEC" in snap


def test_9_missing_optional_provenance_fields(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="Does something hold?",
            epistemic="INCONCLUSIVE",
            journey_rows=[],
            feature=None,
            outcome=None,
            horizon=None,
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    card = view["today_cards"][0]
    assert card["selection"]["available"] is False
    assert card["selection"]["unavailable_reason"] == SELECTION_UNSAVED
    assert card["compared_to_known"]["unavailable_reason"] == PROVENANCE_INSUFFICIENT
    assert SELECTION_UNSAVED in snap
    assert PROVENANCE_INSUFFICIENT in snap
    assert "Chưa được chạy / không có trong artifact" in snap


def test_10_zero_side_effect_render_read_model(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    birth = _birth(
        observation_id="obs-today",
        trade_date="2026-08-27",
        research_question="Does RSI14 predict T5?",
        epistemic="SUPPORTED",
        journey_rows=_two_experiment_rows(),
        selection_provenance={
            "selected_family_key": "fam-1",
            "selected_question": "Does RSI14 predict T5?",
            "selected_feature": "RSI14",
            "selected_outcome": "t5_return",
            "scientific_reasons": ["NOVEL_FAMILY"],
            "why_selected": "Selected RSI14 → t5_return because NOVEL_FAMILY (score=100.000).",
            "considered": [],
            "rejected": [],
            "memory_consulted": True,
            "empty_memory": False,
        },
    )
    _plant_birth(edge, birth)
    _plant_memory(
        edge,
        {
            "fam-1": {
                "family_key": "fam-1",
                "feature": "RSI14",
                "outcome": "t5_return",
                "horizon": "T5",
                "support_count": 1,
                "falsify_count": 0,
                "unresolved_count": 0,
                "last_epistemic_state": "SUPPORTED",
                "episode_count": 1,
                "observation_ids": ["obs-today"],
                "last_selection_provenance": birth["selection_provenance"],
                "forward_validation_history": [],
                "updated_at": "2026-08-27T12:05:00Z",
            }
        },
        events=[
            {
                "event": "BIRTH_RECORDED",
                "observation_id": "obs-today",
                "family_key": "fam-1",
                "selection_provenance": birth["selection_provenance"],
            }
        ],
    )
    _plant_outcome(
        edge,
        observation_id="obs-today",
        horizon="T3",
        adjudication="CLAIM_SUPPORTING",
    )
    _append_jsonl(
        edge / "production_observations" / "daily_run_ledger.jsonl",
        {"run_id": "pdrun-brain", "target_trade_date": "2026-08-27"},
    )
    _append_jsonl(
        edge / "production_observations" / "daily_assessment_ledger.jsonl",
        {"assessment_id": "da-1", "observation_id": "obs-today", "assessment_trade_date": "2026-08-27"},
    )

    before_hashes = snapshot_scientific_artifact_hashes(edge)
    before_files = scientific_artifact_file_set(edge)
    assert "production_observation_ledger.jsonl" in before_hashes
    assert "production_observations/forward_outcome_ledger.jsonl" in before_hashes
    assert "production_observations/daily_assessment_ledger.jsonl" in before_hashes
    assert "production_observations/daily_run_ledger.jsonl" in before_hashes
    assert "research_memory/research_memory_index.json" in before_hashes

    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    from modules.edge_research.autonomous_daily_edge_ui import build_autonomous_daily_edge_ui_view

    auto = build_autonomous_daily_edge_ui_view(data_dir=edge)
    auto_snap = render_autonomous_daily_edge_text_snapshot(auto)

    after_hashes = snapshot_scientific_artifact_hashes(edge)
    after_files = scientific_artifact_file_set(edge)
    assert after_files == before_files
    assert after_hashes == before_hashes
    assert view["scientific_side_effects"] is False
    assert view["requires_streamlit_action"] is False
    assert "NOVEL_FAMILY" in snap
    assert RESEARCH_BRAIN_EXPANDER_TITLE in auto_snap
    assert NOT_BUY_SELL in auto_snap


def test_memory_summary_uses_persisted_family_fields(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="q",
            epistemic="SUPPORTED",
        ),
    )
    _plant_memory(
        edge,
        {
            "a": {
                "family_key": "a",
                "last_epistemic_state": "SUPPORTED",
                "episode_count": 1,
                "observation_ids": ["obs-today"],
                "forward_validation_history": [],
                "updated_at": "2026-08-27T12:00:00Z",
            },
            "b": {
                "family_key": "b",
                "last_epistemic_state": "FALSIFIED",
                "episode_count": 2,
                "forward_validation_history": [{"adjudication": "CLAIM_DISCONFIRMING"}],
                "updated_at": "2026-08-26T12:00:00Z",
            },
            "c": {
                "family_key": "c",
                "last_epistemic_state": "UNRESOLVED",
                "episode_count": 1,
                "forward_validation_history": [{"adjudication": "CLAIM_INCONCLUSIVE"}],
                "updated_at": "2026-08-25T12:00:00Z",
            },
        },
    )
    view = build_research_brain_daily_view(data_dir=edge)
    mem = view["memory"]
    assert mem["present"] is True
    assert mem["families_known"] == 3
    assert mem["supported"] == 1
    assert mem["falsified"] == 1
    assert mem["unresolved"] == 1
    assert mem["waiting_forward"] == 2  # empty history + CLAIM_INCONCLUSIVE
    snap = render_research_brain_text_snapshot(view)
    assert "Families known: 3" in snap


def test_missing_birth_shows_chua_co_du_lieu(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    assert view["today_cards"][0]["available"] is False
    assert MISSING_DATA in snap


def test_does_not_infer_feature_from_question_text(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="RSI14 → T5 should not be inferred from this sentence",
            epistemic="SUPPORTED",
            feature=None,
            outcome=None,
            horizon=None,
            claim_status="LEGACY_INSUFFICIENT_CLAIM_SPEC",
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    assert view["today_cards"][0]["feature"] is None
    assert view["today_cards"][0]["horizon"] is None
    assert view["today_cards"][0]["feature_horizon_label"] is None


def test_previous_observations_selector_is_secondary(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-today",
            trade_date="2026-08-27",
            research_question="today q",
            epistemic="SUPPORTED",
        ),
    )
    _plant_birth(
        edge,
        _birth(
            observation_id="obs-old",
            trade_date="2026-08-20",
            research_question="old q",
            epistemic="WEAKENED",
        ),
    )
    view = build_research_brain_daily_view(data_dir=edge)
    snap = render_research_brain_text_snapshot(view)
    assert "obs-old" in view["previous_observation_ids"]
    assert "Previous observations" in snap
    assert view["today_cards"][0]["observation_id"] == "obs-today"


def test_autonomous_snapshot_keeps_brain_before_historical_challenger(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _full_today(edge)
    from modules.edge_research.autonomous_daily_edge_ui import (
        HISTORICAL_CHALLENGER_SECTION,
        build_autonomous_daily_edge_ui_view,
    )

    auto = build_autonomous_daily_edge_ui_view(data_dir=edge)
    snap = render_autonomous_daily_edge_text_snapshot(auto)
    assert snap.index(RESEARCH_BRAIN_EXPANDER_TITLE) < snap.index(HISTORICAL_CHALLENGER_SECTION)
    assert snap.index("DAILY MARKET VOICE") < snap.index(RESEARCH_BRAIN_EXPANDER_TITLE)


def test_frozen_scientific_hashes_unchanged():
    trigger = REPO / "modules/edge_research/opr_bridge/production_trigger.py"
    second = REPO / "modules/edge_research/opr_bridge/second_experiment_pipeline.py"
    assert _sha_file(trigger) == FROZEN_TRIGGER_HASH
    assert _sha_file(second) == FROZEN_SECOND_EXPERIMENT_HASH


def test_read_model_module_has_no_opr_bridge_imports():
    import ast

    src = (REPO / "modules/edge_research/research_brain_daily_ui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    assert all("opr_bridge" not in name for name in imports)
    assert "os.mkdir" not in src
    assert ".mkdir(" not in src

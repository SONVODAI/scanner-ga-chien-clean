"""
Regression: Streamlit Edge Research must surface autonomous daily production,
not stale Challenger candidate Research Voice.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.autonomous_daily_edge_ui import (
    AUTONOMOUS_DAILY_SECTION,
    HISTORICAL_CHALLENGER_SECTION,
    build_autonomous_daily_edge_ui_view,
    render_autonomous_daily_edge_text_snapshot,
)
from modules.edge_research.opr_bridge.production_living_observation_persistence import (
    session_voice_path,
)
from modules.edge_research.storage import resolve_production_runs_root


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plant_session(
    edge: Path,
    *,
    trade_date: str,
    run_id: str,
    discovery_count: int,
    q1: str,
) -> Path:
    prod = edge / "production_observations"
    (prod / "daily_runs").mkdir(parents=True, exist_ok=True)
    (prod / "daily_manifests").mkdir(parents=True, exist_ok=True)
    (prod / "daily_voices").mkdir(parents=True, exist_ok=True)

    index_path = prod / "daily_run_index.json"
    index = {"runs": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    index["runs"][run_id] = {
        "run_id": run_id,
        "target_trade_date": trade_date,
        "run_disposition": "SUCCESS",
        "run_mode": "LIVE_FORWARD",
    }
    index_path.write_text(json.dumps(index), encoding="utf-8")

    run_payload = {
        "run_id": run_id,
        "target_trade_date": trade_date,
        "run_mode": "LIVE_FORWARD",
        "run_disposition": "SUCCESS",
        "run_identity_hash": f"hash-{run_id}",
        "run_started_at": f"{trade_date}T12:00:00Z",
        "run_completed_at": f"{trade_date}T12:05:00Z",
        "counts_as_forward_evidence": True,
        "observations_born": [f"obs-{i}" for i in range(discovery_count)],
        "observations_reassessed": ["obs-prior"],
        "forward_outcomes_released": [],
        "daily_summary_id": f"sum-{trade_date}",
        "current_phase": "RUN_FINALIZED",
        "phase_history": [],
        "failure_or_skip_reason": None,
        "source_dataset_identity": "fixture",
        "source_dataset_hash": "abc",
        "source_max_trade_date": trade_date,
        "policy_hash_bundle": "pol",
        "shadow_authority": {
            "research_only": True,
            "trading_authority": False,
            "buy_signal": False,
            "sell_signal": False,
            "edge_active": False,
        },
        "frozen": True,
    }
    (prod / "daily_runs" / f"{run_id}.json").write_text(
        json.dumps(run_payload), encoding="utf-8"
    )

    manifest = {
        "run_id": run_id,
        "trade_date": trade_date,
        "run_mode": "LIVE_FORWARD",
        "run_disposition": "SUCCESS",
        "bot_spoke_today": True,
        "discovery_count": discovery_count,
        "silence_or_no_discovery": discovery_count == 0,
        "summary_id": f"sum-{trade_date}",
    }
    (prod / "daily_manifests" / f"{run_id}.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    voice = {
        "observation_id": "SESSION_MARKET_VOICE",
        "assessment_trade_date": trade_date,
        "voice_kind": "SESSION_MARKET_VOICE",
        "q1_today_i_see_vi": q1,
        "q2_vs_prior_session_vi": f"Market context (structured): market_real=8.4 for {trade_date}.",
        "q3_market_change_vi": "Market delta đáng chú ý: regime:MATURE->ROLLOVER.",
        "q4_new_evidence_vi": "Forward evidence mới: 1 outcome(s).",
        "q5_belief_changed_vi": "Belief changes: 0; unchanged reassessments: 2.",
        "q9_waiting_for_vi": "Waiting for T3 eligible.",
    }
    voice_path = prod / "daily_voices" / f"session_{trade_date}.json"
    voice_path.write_text(json.dumps(voice, ensure_ascii=False), encoding="utf-8")
    return voice_path


def _plant_stale_challenger(edge: Path) -> None:
    """Older Challenger artifacts that previously masqueraded as Research Voice."""
    edge.mkdir(parents=True, exist_ok=True)
    (edge / "latest_challenger_run.json").write_text(
        json.dumps(
            {
                "run_id": "chal-old",
                "discovery_run_id": "disc-old",
                "robustness_pass": 0,
                "robustness_fragile": 3,
                "robustness_reject": 17,
                "candidates_entered": 20,
            }
        ),
        encoding="utf-8",
    )
    (edge / "latest_discovery_run.json").write_text(
        json.dumps(
            {
                "run_id": "disc-old",
                "coverage_start": "2026-07-23",
                "coverage_end": "2026-08-20",
                "candidates_discovered": 20,
            }
        ),
        encoding="utf-8",
    )


def test_autonomous_daily_ui_surfaces_session_not_challenger(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    voice_path = _plant_session(
        edge,
        trade_date="2026-08-27",
        run_id="pdrun-6dd458c5a406a6ec",
        discovery_count=1,
        q1="Hôm nay (2026-08-27) — nhật ký research session. Có 1 observation mới được sinh hôm nay.",
    )
    _plant_stale_challenger(edge)
    before = _sha(voice_path)

    view = build_autonomous_daily_edge_ui_view(data_dir=edge)
    snap = render_autonomous_daily_edge_text_snapshot(view)

    # 1–5: latest autonomous session + voice + disposition + discovery
    assert view["session_date"] == "2026-08-27"
    assert view["run_disposition"] == "SUCCESS"
    assert view["discovery_count"] == 1
    assert view["daily_market_voice_exists"] is True
    assert view["session_voice_observation_id"] == "SESSION_MARKET_VOICE"
    assert "Hôm nay (2026-08-27)" in (view["session_voice_questions"].get("q1_today_i_see_vi") or "")
    assert "SESSION_MARKET_VOICE" in snap
    assert AUTONOMOUS_DAILY_SECTION in snap
    assert "Discovery today: 1" in snap

    # 6: old challenger voice must NOT substitute
    assert "EDGE-000001" not in snap
    assert "RESEARCH ONLY — NOT VALIDATED" not in snap
    assert view["challenger_voice_substituted"] is False

    # 7: historical challenger remains separately labeled
    assert HISTORICAL_CHALLENGER_SECTION in snap
    assert (edge / "latest_challenger_run.json").exists()

    # 9: UI read does not mutate production artifacts
    assert _sha(voice_path) == before
    assert view["requires_streamlit_action"] is False
    assert view["view_only"] is True

    # 11: no double-nest
    assert view["double_nested"] is False
    assert resolve_production_runs_root(edge).name == "production_observations"
    assert resolve_production_runs_root(edge).parent.name != "production_observations"
    assert Path(view["canonical_root"]).name == "production_observations"


def test_zero_discovery_success_still_shows_market_voice(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _plant_session(
        edge,
        trade_date="2026-08-28",
        run_id="pdrun-zero",
        discovery_count=0,
        q1="Hôm nay (2026-08-28) — không có stock edge / observation mới hôm nay.",
    )
    view = build_autonomous_daily_edge_ui_view(data_dir=edge)
    assert view["session_date"] == "2026-08-28"
    assert view["discovery_count"] == 0
    assert view["daily_market_voice_exists"] is True
    assert view["session_voice_observation_id"] == "SESSION_MARKET_VOICE"
    assert "không có stock edge" in (view["session_voice_questions"]["q1_today_i_see_vi"])


def test_newer_successful_session_automatically_becomes_current(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    _plant_session(
        edge,
        trade_date="2026-08-27",
        run_id="pdrun-old",
        discovery_count=1,
        q1="session 2026-08-27 voice",
    )
    _plant_session(
        edge,
        trade_date="2026-08-28",
        run_id="pdrun-new",
        discovery_count=2,
        q1="session 2026-08-28 voice — newer",
    )
    view = build_autonomous_daily_edge_ui_view(data_dir=edge)
    assert view["session_date"] == "2026-08-28"
    assert view["run_id"] == "pdrun-new"
    assert view["discovery_count"] == 2
    assert "2026-08-28" in view["session_voice_questions"]["q1_today_i_see_vi"]


def test_explicit_older_date_still_resolvable_without_mutation(tmp_path: Path):
    edge = tmp_path / "data" / "edge_research"
    v27 = _plant_session(
        edge,
        trade_date="2026-08-27",
        run_id="pdrun-27",
        discovery_count=1,
        q1="voice-27",
    )
    _plant_session(
        edge,
        trade_date="2026-08-28",
        run_id="pdrun-28",
        discovery_count=0,
        q1="voice-28",
    )
    before = _sha(v27)
    view = build_autonomous_daily_edge_ui_view(trade_date="2026-08-27", data_dir=edge)
    assert view["session_date"] == "2026-08-27"
    assert view["discovery_count"] == 1
    assert _sha(v27) == before
    assert session_voice_path("2026-08-27", edge).exists()


def test_ui_py_precedence_labels_challenger_not_as_research_voice():
    """Static contract: Edge panel labels Challenger voice distinctly."""
    src = (REPO / "modules" / "edge_research" / "ui.py").read_text(encoding="utf-8")
    assert "build_autonomous_daily_edge_ui_view" in src
    assert "render_autonomous_daily_edge_block" in src
    assert "Challenger candidate voice (historical)" in src
    assert 'with st.expander("Research Voice"' not in src
    assert "HISTORICAL_CHALLENGER_SECTION" in src

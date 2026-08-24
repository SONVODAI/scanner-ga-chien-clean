"""
Tests for autonomous research lifecycle heartbeat (production wiring repair).

Covers required cases T1–T9. RESEARCH ONLY — no trading coupling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.edge_research.autonomous_heartbeat import (
    DECISION_CONTINUE_EXISTING_EXPERIMENT,
    DECISION_IDEMPOTENT_REPLAY,
    DECISION_NO_RESEARCH_NO_STATE_CHANGE,
    DECISION_OPEN_NEW_EXPERIMENT,
    DECISION_RESEARCH_REVIEW_WARRANTED,
    DECISION_WAIT_FOR_OUTCOME_MATURITY,
    PRODUCTION_COUPLING,
    assert_no_hidden_examiner_reference,
    get_autonomous_status_snapshot,
    load_active_experiments,
    load_heartbeat_state,
    observe_new_data_cycle,
    run_autonomous_research_heartbeat,
)
from modules.edge_research.storage import read_status
from modules.edge_research.ui import (
    execution_in_progress_from_session,
    queue_research_action,
)


def _write_earning_fixture(earning_dir: Path, trade_date: str, *, market_real: float = 9.6) -> None:
    earning_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "observation_id": [f"obs-{trade_date}-1", f"obs-{trade_date}-2"],
            "decision_id": ["d1", "d2"],
            "decision_status": ["OK", "OK"],
            "trade_date": [trade_date, trade_date],
            "recorded_at": ["2026-08-24T18:00:00", "2026-08-24T18:00:00"],
            "module_version": ["4.0.0", "4.0.0"],
            "brain_generation": ["g", "g"],
            "feature_version": ["f", "f"],
        }
    ).to_csv(earning_dir / "t0_observation_freeze.csv", index=False)
    pd.DataFrame(
        {
            "trade_date": [trade_date],
            "entity": ["VNINDEX"],
            "session_slot": ["AFTER_CLOSE"],
            "snapshot_version": ["1"],
            "captured_at": ["2026-08-24T18:12:00"],
            "market_real": [market_real],
            "market_live": [10.2],
            "market_forecast": [9.0],
            "date": [trade_date],
        }
    ).to_csv(earning_dir / "market_daily_t0.csv", index=False)
    pd.DataFrame(
        {
            "observation_id": [f"o-{trade_date}"],
            "trade_date": [trade_date],
            "recorded_at": ["2026-08-24T18:00:00"],
            "module_version": ["4.0.0"],
            "symbol": ["AAA"],
            "price": [10.0],
            "health_group": ["A"],
            "health_score": [1.0],
        }
    ).to_csv(earning_dir / "observations.csv", index=False)
    (earning_dir / "status.json").write_text(
        json.dumps({"ok": True, "trade_date": trade_date, "module_version": "4.0.0"}),
        encoding="utf-8",
    )


def test_t1_new_eod_produces_exactly_one_heartbeat(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")

    d1 = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    assert d1.idempotent_replay is False
    assert d1.data_cutoff == "2026-08-24"
    assert d1.decision_code != "NONE"
    assert d1.production_coupling == PRODUCTION_COUPLING

    decisions_path = data_dir / "autonomous_lifecycle" / "heartbeat_decisions.jsonl"
    lines = [ln for ln in decisions_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1

    status = read_status(data_dir)
    assert status.get("last_research_event", "NONE") != "NONE"
    assert "AUTONOMOUS HEARTBEAT" in status["last_research_event"]


def test_t2_no_novelty_records_deliberate_no_research(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")

    # Seed prior state with same transition on previous cutoff
    run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-24",
        data_dir=data_dir,
        earning_dir=earning,
    )
    # Force new identity via market_real change but same transition / no lag
    _write_earning_fixture(earning, "2026-08-24", market_real=9.7)
    d2 = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-24",
        data_dir=data_dir,
        earning_dir=earning,
        force=True,
    )
    assert d2.decision_code in {
        DECISION_NO_RESEARCH_NO_STATE_CHANGE,
        "NO_RESEARCH_INSUFFICIENT_NOVELTY",
    }
    assert "NO_RESEARCH" in d2.decision_code
    assert d2.research_ran is False


def test_t3_research_worthy_opens_experiment(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")

    d = run_autonomous_research_heartbeat(
        research_market_state="RECOVERY",
        research_market_transition="STRESS -> RECOVERY",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
        force_open_experiment=True,
        open_maturity_trade_date="2026-08-29",
    )
    assert d.decision_code == DECISION_OPEN_NEW_EXPERIMENT
    assert d.active_experiment_id
    experiments = load_active_experiments(data_dir)
    assert any(e.get("experiment_id") == d.active_experiment_id for e in experiments)
    assert experiments[0]["status"] == "WAITING_FOR_OUTCOME_MATURITY"
    assert experiments[0]["production_coupling"] == "NONE"


def test_t4_idempotent_streamlit_reruns(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")

    d1 = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    d2 = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    d3 = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    assert d1.data_identity == d2.data_identity == d3.data_identity
    assert d2.idempotent_replay is True
    assert d3.idempotent_replay is True
    assert d2.decision_code == DECISION_IDEMPOTENT_REPLAY
    lines = [
        ln
        for ln in (data_dir / "autonomous_lifecycle" / "heartbeat_decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    assert len(lines) == 1


def test_t5_outcome_waiting_not_prematurely_rerun(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")

    opened = run_autonomous_research_heartbeat(
        research_market_state="RECOVERY",
        research_market_transition="STRESS -> RECOVERY",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
        force_open_experiment=True,
        open_maturity_trade_date="2026-08-29",
    )
    assert opened.decision_code == DECISION_OPEN_NEW_EXPERIMENT

    # New data identity before maturity
    _write_earning_fixture(earning, "2026-08-25", market_real=9.8)
    waiting = run_autonomous_research_heartbeat(
        research_market_state="RECOVERY",
        research_market_transition="STRESS -> RECOVERY",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    assert waiting.decision_code == DECISION_WAIT_FOR_OUTCOME_MATURITY
    assert waiting.waiting_for_outcomes is True
    assert waiting.active_experiment_id == opened.active_experiment_id
    # Still waiting — not re-opened
    experiments = load_active_experiments(data_dir)
    assert sum(1 for e in experiments if e.get("status") == "WAITING_FOR_OUTCOME_MATURITY") == 1


def test_t6_persistence_across_reload(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")

    d1 = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    state = load_heartbeat_state(data_dir)
    snap = get_autonomous_status_snapshot(data_dir)
    status = read_status(data_dir)

    assert state["last_decision_code"] == d1.decision_code
    assert snap["last_autonomous_decision"] == d1.decision_code
    assert status["last_research_event"] == d1.voice_line()
    assert "NONE" not in status["last_research_event"] or "NO_RESEARCH" in status["last_research_event"]


def test_t7_manual_controls_do_not_conflict(tmp_path: Path) -> None:
    session: dict = {}
    assert queue_research_action(session, "discovery") is True
    assert execution_in_progress_from_session(session) is True
    # Heartbeat UI path skips while busy; core heartbeat still safe separately
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")
    d = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    assert d.decision_code
    # Manual pending remains intact
    assert session.get("edge_research_pending") == "discovery"


def test_t8_production_isolation() -> None:
    from modules.edge_research import autonomous_heartbeat as hb

    text = Path(hb.__file__).read_text(encoding="utf-8")
    assert hb.PRODUCTION_COUPLING == "NONE"
    assert hb.ACTION_MODE == "RESEARCH ONLY"
    assert "build_final_decision" not in text
    assert "apply_learning_experience" not in text
    assert "Position Guardian" not in text
    # No trading execution hooks
    assert "execute_buy" not in text.lower()
    assert "execute_sell" not in text.lower()


def test_t9_hidden_examiner_isolation() -> None:
    assert_no_hidden_examiner_reference()
    root = Path(__file__).resolve().parents[1]
    needle = "HIDDEN" + "_EXAMINER_RESEARCH"
    for rel in (
        "modules/edge_research/autonomous_heartbeat.py",
        "modules/edge_research/ui.py",
        "modules/edge_research/engine.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        # Docstring may mention the prohibition; ban Path/open usage constructions.
        runtime_hits = []
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if needle not in s:
                continue
            if "Does NOT" in s or s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
                continue
            if "open(" in s or "Path(" in s or "read_text" in s or "read_csv" in s:
                runtime_hits.append(f"{rel}:{i}:{s}")
        assert not runtime_hits, runtime_hits


def test_stale_coverage_triggers_review(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")
    d = run_autonomous_research_heartbeat(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    assert d.decision_code == DECISION_RESEARCH_REVIEW_WARRANTED
    assert d.research_ran is False


def test_observe_identity_stable_for_same_inputs(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    _write_earning_fixture(earning, "2026-08-24")
    a = observe_new_data_cycle(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        earning_dir=earning,
    )
    b = observe_new_data_cycle(
        research_market_state="MATURE",
        research_market_transition="MATURE -> MATURE",
        research_coverage_end="2026-08-18",
        earning_dir=earning,
    )
    assert a.data_identity == b.data_identity
    assert a.data_cutoff == "2026-08-24"


def test_continue_after_maturity(tmp_path: Path) -> None:
    earning = tmp_path / "earning"
    data_dir = tmp_path / "edge"
    _write_earning_fixture(earning, "2026-08-24")
    run_autonomous_research_heartbeat(
        research_market_state="RECOVERY",
        research_market_transition="STRESS -> RECOVERY",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
        force_open_experiment=True,
        open_maturity_trade_date="2026-08-25",
    )
    _write_earning_fixture(earning, "2026-08-25", market_real=9.9)
    d = run_autonomous_research_heartbeat(
        research_market_state="RECOVERY",
        research_market_transition="STRESS -> RECOVERY",
        research_coverage_end="2026-08-18",
        data_dir=data_dir,
        earning_dir=earning,
    )
    assert d.decision_code == DECISION_CONTINUE_EXISTING_EXPERIMENT

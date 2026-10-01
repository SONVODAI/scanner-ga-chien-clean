"""Phase 3J.14A — Lifecycle silence closure patch tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.opr_bridge.bb_production_autonomy_01_fixtures import _anomaly_panel
from modules.edge_research.opr_bridge.bounded_lifecycle_controller import (
    _is_execution_eligible_package,
    run_bounded_lifecycle_loop,
)
from modules.edge_research.opr_bridge.bounded_lifecycle_records import (
    ResearchBudget,
    STOP_LIFECYCLE_DESIGN_SILENCE,
)
from modules.edge_research.opr_bridge.bounded_lifecycle_state import build_experiment_history
from modules.edge_research.opr_bridge.production_bounded_lifecycle import run_bounded_autonomous_research
from modules.edge_research.opr_bridge.production_persistence import read_opr_session
from modules.edge_research.opr_bridge.production_trigger import detect_production_opportunity


def _policy_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_seed77_ord3_silence(tmp: Path):
    panel = _anomaly_panel(seed=77)
    det = detect_production_opportunity(panel, data_cutoff_date="2026-02-15")
    if det.outcome != "OPPORTUNITY_DETECTED":
        pytest.skip("No opportunity on seed 77")
    return run_bounded_autonomous_research(
        det.proposition_record,
        panel,
        data_cutoff_date="2026-02-15",
        data_dir=tmp,
        budget=ResearchBudget(max_experiment_iterations=4),
        bootstrap_new_session=True,
    )


def test_a_no_execution_on_no_faithful_ordinal_ge3():
    """A. ordinal >=3 NO_FAITHFUL_EXPERIMENT → no execution call."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _run_seed77_ord3_silence(Path(tmp))
        assert r.lifecycle is not None
        assert r.lifecycle.outcome == "DESIGN_SILENCE"
        history = build_experiment_history(r.session_record) if r.session_record else []
        ord3 = next((e for e in history if e.ordinal == 3), None)
        assert ord3 is not None
        assert (ord3.package or {}).get("disposition") == "NO_FAITHFUL_EXPERIMENT"
        assert ord3.execution is None


def test_b_no_toolresult_created():
    """B. no ToolResult is created for design silence."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _run_seed77_ord3_silence(Path(tmp))
        history = build_experiment_history(r.session_record) if r.session_record else []
        executed = [e for e in history if e.execution]
        assert len(executed) == 2
        ord3 = next((e for e in history if e.ordinal == 3), None)
        assert ord3 is not None
        assert ord3.execution is None


def test_c_terminates_at_design_boundary():
    """C. lifecycle terminates durably at the correct boundary."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _run_seed77_ord3_silence(Path(tmp))
        assert r.lifecycle.outcome == "DESIGN_SILENCE"
        assert r.lifecycle.termination_reason.startswith(STOP_LIFECYCLE_DESIGN_SILENCE)
        assert "NO_FAITHFUL_EXPERIMENT" in r.lifecycle.termination_reason
        assert STOP_LIFECYCLE_DESIGN_SILENCE in r.stop_boundaries
        assert r.session_record.lifecycle_phase == "STOPPED"


def test_d_replay_idempotent():
    """D. replay is idempotent — no second execution attempt."""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        r1 = _run_seed77_ord3_silence(data_dir)
        session_id = r1.session_record.session_id
        panel = _anomaly_panel(seed=77)
        prop = r1.session_record.proposition_record
        record = read_opr_session(session_id, data_dir=data_dir)
        execute_calls = {"count": 0}
        original = __import__(
            "modules.edge_research.opr_bridge.bounded_lifecycle_controller",
            fromlist=["_run_follow_on_execute"],
        )._run_follow_on_execute

        def _counting_execute(*args, **kwargs):
            execute_calls["count"] += 1
            return original(*args, **kwargs)

        with patch(
            "modules.edge_research.opr_bridge.bounded_lifecycle_controller._run_follow_on_execute",
            side_effect=_counting_execute,
        ):
            r2 = run_bounded_lifecycle_loop(
                prop,
                panel,
                record,
                budget=ResearchBudget(max_experiment_iterations=4),
                data_dir=data_dir,
            )
        assert r2.outcome == "DESIGN_SILENCE"
        assert execute_calls["count"] == 0


def test_e_selected_still_executes():
    """E. SELECTED disposition still executes normally."""
    assert _is_execution_eligible_package({"disposition": "SELECTED"}) is True
    assert _is_execution_eligible_package({"disposition": "NO_FAITHFUL_EXPERIMENT"}) is False
    with tempfile.TemporaryDirectory() as tmp:
        panel = _anomaly_panel(seed=42)
        det = detect_production_opportunity(panel, data_cutoff_date="2026-02-15")
        if det.outcome != "OPPORTUNITY_DETECTED":
            pytest.skip("No opportunity")
        r = run_bounded_autonomous_research(
            det.proposition_record,
            panel,
            data_cutoff_date="2026-02-15",
            data_dir=Path(tmp),
            budget=ResearchBudget(max_experiment_iterations=2),
            bootstrap_new_session=True,
        )
        history = build_experiment_history(r.session_record) if r.session_record else []
        executed = [e for e in history if e.execution]
        assert len(executed) >= 1


def test_f_malformed_selected_still_fail_closed():
    """F. execution fail-closed remains active for malformed SELECTED packages."""
    from modules.edge_research.opr_bridge.bb_second_experiment_execution_01_fixtures import (
        run_cf_se_counterfactuals,
    )

    cf = run_cf_se_counterfactuals()
    assert cf["all_passed"], cf


def test_g_blind_seeds_no_unnecessary_continuation():
    """G. seeds 501/502/601/602 no longer FAILED_CLOSED on ord-3 silence execution."""
    import sys

    zone_c = REPO / "benchmarks/bb_blind_exam_01/zone_c_examiner"
    sys.path.insert(0, str(zone_c))
    from panel_generator import generate_blind_panel_for_seed

    from modules.edge_research.opr_bridge.blind_research_examination_runner import (
        run_blind_research_examination,
    )

    for seed in (501, 502, 601, 602):
        with tempfile.TemporaryDirectory() as tmp:
            panel, _gt = generate_blind_panel_for_seed(seed)
            frozen = run_blind_research_examination(
                panel,
                anonymous_case_id=f"CASE-{seed:04d}",
                data_cutoff_date="2026-02-15",
                data_dir=Path(tmp),
                budget=ResearchBudget(max_experiment_iterations=4),
            )
            assert frozen.lifecycle_outcome == "DESIGN_SILENCE", (
                f"seed {seed}: expected DESIGN_SILENCE, got {frozen.lifecycle_outcome} "
                f"({frozen.termination_reason})"
            )
            assert "experiment_3_execution_failed" not in str(frozen.termination_reason)
            assert frozen.experiments_completed == 2


def test_h_no_research_policy_hash_changes():
    """H. no research-policy/hash changes outside bounded lifecycle controller."""
    root = REPO / "modules/edge_research/opr_bridge"
    unchanged = [
        "follow_on_experiment_candidates.py",
        "follow_on_experiment_history_context.py",
        "follow_on_experiment_selector.py",
        "second_experiment_pipeline.py",
        "first_experiment_research_decider.py",
        "second_experiment_research_decider.py",
    ]
    from diagnostics.phase_3j14_research_capability_gap_audit.run_phase_3j14 import (
        _hidden_answer_audit,
    )

    frozen = json.loads(
        (
            REPO
            / "diagnostics/phase_3j14_research_capability_gap_audit/artifacts/00_frozen_policy_hashes.json"
        ).read_text()
    )["policy_hashes"]
    for name in unchanged:
        path = root / name
        if path.exists() and name in frozen:
            assert _policy_hash(path) == frozen[name], f"unexpected hash change: {name}"
    assert _hidden_answer_audit()["passed"] is True


def test_3j14_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j14.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3j13_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j13.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3j12_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j12.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3j11_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j11.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3j10_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3j10.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

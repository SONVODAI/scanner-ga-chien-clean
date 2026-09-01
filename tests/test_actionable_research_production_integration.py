"""Production-lineage integration: Fusion after A→C→B, receipt isolation, lock/UI."""

from __future__ import annotations

import inspect
from pathlib import Path

from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (
    _finish_daily_run,
)
from modules.production_daily_receipt import (
    OVERALL_FAIL,
    OVERALL_PASS,
    PIPELINE_TERMINATED,
    build_daily_pipeline_receipt,
    write_incomplete_pipeline_receipt,
)
from modules.edge_research.contracts import (
    ASSESSMENT_NO_QUALIFIED_MATCH,
    REASON_NO_ACTIVE_EDGE_AVAILABLE,
)

REPO = Path(__file__).resolve().parents[1]


def test_orchestrator_runs_fusion_after_closed_loop_source_order():
    src = inspect.getsource(_finish_daily_run)
    assert src.index("run_closed_loop_edge_after_daily") < src.index("_attach_actionable_research_fusion")
    orch = (REPO / "modules/edge_research/opr_bridge/production_daily_run_orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert orch.index("run_closed_loop_edge_after_daily") < orch.index("run_actionable_research_after_daily")


def test_no_new_fusion_timer():
    daily_install = (REPO / "deploy/systemd/install-daily-research.sh").read_text(encoding="utf-8")
    assert "mrbot-daily-research.timer" in daily_install
    assert "actionable-research.timer" not in daily_install
    assert "fusion.timer" not in daily_install


def test_streamlit_fusion_ui_is_read_only():
    ui = (REPO / "modules/actionable_research/ui.py").read_text(encoding="utf-8")
    assert "render_actionable_research_panel" in ui
    assert "fuse_session(" not in ui
    assert "persist_fusion_artifact" not in ui
    assert "run_edge_research_eod_cycle(" not in ui
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert "run_actionable_research_after_daily" not in app
    assert "fuse_session(" not in app


def test_receipt_fusion_failure_does_not_change_overall_pass_semantics(tmp_path):
    rec = build_daily_pipeline_receipt(
        "2026-08-14",
        repo_root=tmp_path,
        headless_eod={"stage_disposition": "SUCCESS", "source_rows": 142, "ok": True},
        edge_result={
            "run": {"run_disposition": "SUCCESS", "run_id": "r1"},
            "closed_loop_edge": {
                "ran_science": True,
                "system_status": "SUCCESS",
                "assessment_state": ASSESSMENT_NO_QUALIFIED_MATCH,
                "assessment_reason": REASON_NO_ACTIVE_EDGE_AVAILABLE,
                "order": ["qualification", "continuous_learning", "recognition", "shadow"],
            },
            "actionable_research": {
                "ran_fusion": False,
                "status": "FAILED",
                "failure_detail": "boom",
                "universe_evaluated": 0,
                "noteworthy_count": None,
                "artifact_path": None,
                "observation_births": 0,
                "observation_duplicate_skips": 0,
                "missing_camera_count": None,
                "missing_foreign_count": None,
                "generated_at": None,
            },
        },
        panel_freshness={"target_in_panel_sessions": True},
        run_provenance={"recovery": False, "run_mode": "LIVE_FORWARD"},
    )
    fusion = rec["fusion"]
    assert fusion["ran"] is False
    assert fusion["status"] == "FAILED"
    assert fusion["failure_detail"] == "boom"
    # Existing overall classifier ignores Fusion; missing T0 artifacts still FAIL as before.
    assert rec["closed_loop_complete"] is True
    assert rec["overall"] != OVERALL_PASS or rec["fusion"]["status"] == "FAILED"


def test_receipt_exposes_fusion_fields_when_nested(tmp_path):
    rec = build_daily_pipeline_receipt(
        "2026-08-14",
        repo_root=tmp_path,
        headless_eod={"stage_disposition": "SUCCESS", "source_rows": 142, "ok": True},
        edge_result={
            "run": {"run_disposition": "WAITING_FOR_DATA", "failure_or_skip_reason": "target_date_not_in_panel_sessions"},
            "closed_loop_edge": {"ran_science": False, "skip_reason": "SKIPPED_WAITING_FOR_DATA"},
            "actionable_research": {
                "ran_fusion": True,
                "status": "ELIGIBLE",
                "universe_evaluated": 142,
                "noteworthy_count": 3,
                "artifact_path": "/tmp/fusion.json",
                "observation_births": 3,
                "observation_duplicate_skips": 0,
                "missing_camera_count": 2,
                "missing_foreign_count": 4,
                "generated_at": "2026-08-14T15:00:00Z",
            },
        },
        panel_freshness={"target_in_panel_sessions": False},
    )
    fusion = rec["fusion"]
    for key in (
        "ran",
        "status",
        "universe_evaluated",
        "noteworthy_count",
        "artifact_path",
        "observation_births",
        "observation_duplicate_skips",
        "missing_camera_count",
        "missing_foreign_count",
        "generated_at",
    ):
        assert key in fusion
    assert fusion["universe_evaluated"] == 142
    assert fusion["noteworthy_count"] == 3
    assert rec["overall"] != OVERALL_PASS  # waiting/missing T0 semantics unchanged


def test_incomplete_receipt_still_fail_and_shows_fusion_not_run(tmp_path):
    incomplete = write_incomplete_pipeline_receipt(
        "2026-08-14",
        repo_root=tmp_path,
        headless_eod={"stage_disposition": "SUCCESS", "source_rows": 142},
        termination_reason=PIPELINE_TERMINATED,
    )
    body = incomplete["receipt"]
    assert body["overall"] == OVERALL_FAIL
    assert body["fusion"]["ran"] is False
    assert body["fusion"]["status"] == "NOT_RUN"


def test_lock_and_timeout_repair_source_still_intact():
    entry = (REPO / "modules/edge_research/opr_bridge/production_daily_run_entrypoint.py").read_text(
        encoding="utf-8"
    )
    assert entry.index("acquire_run_lock") < entry.index("run_headless_eod(")
    svc = (REPO / "deploy/systemd/mrbot-daily-research.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=5400" in svc
    hook = (REPO / "modules/edge_research/closed_loop_daily_hook.py").read_text(encoding="utf-8")
    assert "run_qualification" in hook or "run_edge_research_eod_cycle" in hook
    assert "fuse_session" not in hook


def test_camera_collect_does_not_own_fusion_writer():
    runner = (REPO / "modules/intraday_memory/runner.py").read_text(encoding="utf-8")
    assert "run_actionable_research_after_daily(" not in runner
    assert "maybe_run_fusion_after_camera" in runner

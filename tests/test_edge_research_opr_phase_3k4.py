"""Phase 3K.4 — Living Research UI tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.bb_living_research_ui_01_fixtures import (
    generate_ui_preview_snapshots,
    run_ui_read_model_fixtures,
)
from modules.edge_research.opr_bridge.production_living_research_ui import (
    audit_ui_forbidden_terms,
    render_living_research_ui_text_snapshot,
)
from modules.edge_research.opr_bridge.production_living_research_ui_read_model import (
    build_living_research_ui_read_model,
    build_observation_timeline_read_model,
)
from modules.edge_research.opr_bridge.production_living_research_ui_records import (
    STOP_LIVING_RESEARCH_UI_READY,
)
from modules.edge_research.opr_bridge.production_observation_isolation import run_trading_isolation_audit


def test_ui_read_model_fixtures():
    fx = run_ui_read_model_fixtures(REPO)
    assert fx["all_passed"], fx


def test_stop_boundary_constant():
    assert STOP_LIVING_RESEARCH_UI_READY == "STOP_LIVING_RESEARCH_UI_READY"


def test_empty_read_model_honest():
    with tempfile.TemporaryDirectory() as tmp:
        rm = build_living_research_ui_read_model(data_dir=Path(tmp))
    assert rm["authority_badge"] == "RESEARCH ONLY"
    snap = render_living_research_ui_text_snapshot(rm)
    assert not audit_ui_forbidden_terms(snap)
    assert "BUY" not in snap.upper() or "KHÔNG" in snap.upper()


def test_ui_preview_snapshots():
    preview = generate_ui_preview_snapshots(REPO)
    assert preview["fixtures_pass"] is True
    assert "normal_speaking_day" in preview["previews"]
    assert preview["previews"]["counts_as_forward_evidence"] is False


def test_no_forbidden_trading_terms():
    with tempfile.TemporaryDirectory() as tmp:
        rm = build_living_research_ui_read_model(data_dir=Path(tmp))
    snap = render_living_research_ui_text_snapshot(rm)
    forbidden = audit_ui_forbidden_terms(snap)
    assert not forbidden, forbidden


def test_trading_isolation_audit():
    audit = run_trading_isolation_audit(REPO)
    assert audit["passed"], audit
    assert "production_living_research_ui.py" in audit.get("modules_audited", [])


def test_hidden_answer_audit():
    root = REPO / "modules/edge_research/opr_bridge"
    forbidden = ["ground_truth", "seed_to_blind_class", "blind-a"]
    hits = []
    for name in [
        "production_living_research_ui.py",
        "production_living_research_ui_read_model.py",
    ]:
        path = root / name
        if path.exists():
            blob = path.read_text(encoding="utf-8").lower()
            for tok in forbidden:
                if tok in blob:
                    hits.append((name, tok))
    assert not hits


def test_3k3_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k3.py", "-q", "--tb=no", "-k", "not regression"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3k2_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k2.py", "-q", "--tb=no", "-k", "not regression"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3k1_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k1.py", "-q", "--tb=no", "-k", "not regression"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_3k0_regression():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_edge_research_opr_phase_3k0.py", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

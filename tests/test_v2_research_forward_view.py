"""Fixture-only forward status. No durable store and no Guardian session file."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from research.approximate_returns.contract import (
    PRICE_BASIS,
    STATUS_AVAILABLE,
    STATUS_NOT_YET,
    STATUS_T0_MISSING,
    STATUS_TARGET_MISSING,
    STATUS_TRUNCATED,
)
from research.v2_research_ledger.forward_view import evaluate_forward_status

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "research" / "v2_research_ledger" / "forward_view.py"
IDENTITIES = ROOT / "research" / "v2_research_ledger" / "durable" / "identities.jsonl"
GUARDIAN_SESSION = ROOT / "data" / "guardian_research" / "sessions" / "2026-11-13.json"
FORBIDDEN = (
    "research.guardian_research",
    "modules.learning_t0_capture",
    "research.guardian_research.close_job",
    "research.guardian_research.scan_archive",
    "research.guardian_research.freeze_witness",
    "modules.live_candidate_v2_action",
    "close_job",
    "scan_archive",
    "freeze_witness",
    "learning_t0_capture",
)


def _store(sessions: list[str], bars: list[tuple[str, str, float, str]]) -> dict:
    return {
        "as_of": sessions[-1],
        "discontinuities": [],
        "price_basis": PRICE_BASIS,
        "rows": [
            {"clock": clock, "close": close, "session": session, "symbol": symbol}
            for symbol, session, close, clock in bars
        ],
        "trading_sessions": list(sessions),
    }


def _row(**overrides) -> dict:
    row = {
        "candidate_first_seen_ts": "2026-11-10T19:49:09+07:00",
        "row_id": "sidecar|2026-11-10|HPG|2026-11-10T19:49:09+07:00",
        "source": "brain_a_scan_setup",
        "source_attribution": "brain_a_scan_setup",
        "symbol": "HPG",
        "t0_date": "2026-11-10",
        "t0_price": 27000,
        "t0_price_provenance": "fixture-sealed-observation",
    }
    row.update(overrides)
    return row


def test_valid_reference_uses_the_session_close_not_the_sealed_price(tmp_path: Path):
    sealed_before = IDENTITIES.read_bytes()
    source = _row()
    snapshot = json.dumps(source, sort_keys=True)
    store = _store(
        ["2026-11-10", "2026-11-11", "2026-11-12"],
        [
            ("HPG", "2026-11-10", 100, "14:45"),
            ("HPG", "2026-11-11", 110, "14:50"),
            ("HPG", "2026-11-12", 120, "14:55"),
        ],
    )
    report = evaluate_forward_status([source], store)
    written = tmp_path / "forward_status.json"
    written.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    loaded = json.loads(written.read_text(encoding="utf-8"))
    cell = loaded["rows"][0]["horizons"]["T+1"]
    assert loaded["official_pnl"] is False
    assert loaded["price_basis"] == PRICE_BASIS
    assert loaded["reference_file_assumed"] is False
    assert loaded["rows"][0]["t0_price"] == 27000
    assert loaded["rows"][0]["t0_price_provenance"] == "fixture-sealed-observation"
    assert loaded["rows"][0]["t0_price_used_as_denominator"] is False
    assert loaded["rows"][0]["reference_t0_price"] == 100
    assert cell["status"] == STATUS_AVAILABLE
    assert cell["included_in_primary"] is True
    assert cell["target_session"] == "2026-11-11"
    assert cell["return_pct"] == 10.0
    assert cell["return_pct"] != round((110 / 27000 - 1) * 100, 6)
    assert json.dumps(source, sort_keys=True) == snapshot
    assert IDENTITIES.read_bytes() == sealed_before
    assert not GUARDIAN_SESSION.exists()


def test_missing_reference_future_session_and_early_clock_are_not_primary():
    missing = evaluate_forward_status([_row()], _store(["2026-11-10", "2026-11-11"], []))
    missing_cell = missing["rows"][0]["horizons"]["T+1"]
    assert missing_cell["status"] == STATUS_T0_MISSING
    assert missing_cell["return_pct"] is None
    assert missing_cell["included_in_primary"] is False

    future = evaluate_forward_status(
        [_row()],
        _store(["2026-11-10"], [("HPG", "2026-11-10", 100, "14:45")]),
    )
    future_cell = future["rows"][0]["horizons"]["T+1"]
    assert future_cell["status"] == STATUS_NOT_YET
    assert future_cell["return_pct"] is None
    assert future_cell["included_in_primary"] is False

    absent_target = evaluate_forward_status(
        [_row()],
        _store(
            ["2026-11-10", "2026-11-11"],
            [("HPG", "2026-11-10", 100, "14:45")],
        ),
    )
    target_cell = absent_target["rows"][0]["horizons"]["T+1"]
    assert target_cell["status"] == STATUS_TARGET_MISSING
    assert target_cell["return_pct"] is None
    assert target_cell["included_in_primary"] is False

    early = evaluate_forward_status(
        [_row()],
        _store(
            ["2026-11-10", "2026-11-11"],
            [
                ("HPG", "2026-11-10", 100, "14:40"),
                ("HPG", "2026-11-11", 110, "14:45"),
            ],
        ),
    )
    early_cell = early["rows"][0]["horizons"]["T+1"]
    assert early_cell["status"] == STATUS_TRUNCATED
    assert early_cell["return_pct"] is None
    assert early_cell["included_in_primary"] is False
    assert early["rows"][0]["t0_price"] == 27000
    assert early["rows"][0]["t0_price_used_as_denominator"] is False


def test_repeated_evaluation_is_deterministic_and_leaves_t0_unchanged():
    source = _row()
    store = _store(
        ["2026-11-10", "2026-11-11"],
        [
            ("HPG", "2026-11-10", 100, "14:45"),
            ("HPG", "2026-11-11", 110, "14:50"),
        ],
    )
    first = evaluate_forward_status([source], store)
    second = evaluate_forward_status([source], store)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert source["t0_price"] == 27000
    assert first["rows"][0]["candidate_first_seen_ts"] == "2026-11-10T19:49:09+07:00"


def test_module_does_not_import_guardian_or_production_writers():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert imported
    for name in imported:
        assert not any(name == item or name.startswith(item + ".") or item in name for item in FORBIDDEN)
    text = MODULE.read_text(encoding="utf-8")
    assert "horizons.json" not in text
    assert "identities.jsonl" not in text

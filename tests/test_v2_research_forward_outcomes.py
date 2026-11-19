"""Derived Ledger T+ generations stay outside the sealed store."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from research.approximate_returns.reference import build_reference_store
from research.guardian_research.reference_export import _digest
from research.v2_research_ledger.board_view import apply_filters, horizon_text
from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.forward_outcomes import (
    STAGE2_LEDGER_HASHES,
    ForwardBuildError,
    attachable_outcomes,
    build_forward_document,
    publish_forward_document,
)
from research.v2_research_ledger.panel_board import HORIZON_STATUS, load_row_panel

ROOT = Path(__file__).resolve().parents[1]
DURABLE = ROOT / "research" / "v2_research_ledger" / "durable"
GUARDIAN = ROOT / "research" / "guardian_research" / "forward.py"
SESSIONS = ["2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]


def _identity(identity_id: str, role: str, symbol: str, t0_date: str) -> dict:
    return {
        "identity_id": identity_id,
        "record_role": role,
        "symbol": symbol,
        "t0_date": t0_date,
    }


def _write_ledger(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    identities = [
        _identity("sidecar|AAA", "sidecar_identity", "AAA", "2026-11-11"),
        _identity("sidecar|BBB", "sidecar_identity", "BBB", "2026-11-11"),
        _identity("sweet|CCC", "sweetspot_identity", "CCC", "2026-11-11"),
        _identity("sweet|BLANK", "sweetspot_identity", "", "2026-11-11"),
        _identity("sidecar|JUMP", "sidecar_identity", "JUMP", "2026-11-11"),
        _identity("sidecar|TRUN", "sidecar_identity", "TRUN", "2026-11-11"),
        _identity("sidecar|GAP", "sidecar_identity", "GAP", "2026-11-11"),
    ]
    links = [{"identity_id": "sidecar|AAA", "link_id": "nomination|sidecar|AAA", "status": "NOMINATED"}]
    conflicts: list[dict] = []
    manifest = {
        "conflict_count": 0,
        "identity_count": len(identities),
        "link_count": len(links),
        "schema": "v2_research_row_store_manifest.v1",
    }
    _jsonl(directory / "identities.jsonl", identities)
    _jsonl(directory / "links.jsonl", links)
    _jsonl(directory / "conflicts.jsonl", conflicts)
    (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _bars() -> list[dict]:
    rows = []
    for index, day in enumerate(SESSIONS):
        rows.append({"symbol": "AAA", "session": day, "close": 10000 + index * 10, "clock": "14:50"})
        rows.append({"symbol": "CCC", "session": day, "close": 100, "clock": "14:50"})
        rows.append({"symbol": "TRUN", "session": day, "close": 11000 + index, "clock": "14:30"})
        close = 13000 if index == 1 else 10000 + index
        rows.append({"symbol": "JUMP", "session": day, "close": close, "clock": "14:50"})
    rows.append({"symbol": "GAP", "session": SESSIONS[0], "close": 13000, "clock": "14:50"})
    return rows


def _write_reference(path: Path, sessions: list[str] | None = None, extra: dict | None = None) -> str:
    calendar = list(sessions or SESSIONS)
    frame = pd.DataFrame(_bars())
    frame = frame[frame["session"].isin(calendar)]
    store = build_reference_store(frame, calendar, as_of=calendar[-1])
    if extra:
        store.update(extra)
    store["content_sha256"] = _digest(store)
    path.write_text(json.dumps(store, sort_keys=True) + "\n", encoding="utf-8")
    return str(store["content_sha256"])


def _hashes(directory: Path) -> dict[str, str]:
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ("identities.jsonl", "links.jsonl", "conflicts.jsonl", "manifest.json")}


def _build(tmp_path: Path, sessions: list[str] | None = None):
    ledger = tmp_path / "durable"
    reference = tmp_path / "reference_store.json"
    output = tmp_path / "outcomes"
    _write_ledger(ledger)
    digest = _write_reference(reference, sessions)
    before = {name: (ledger / name).read_bytes() for name in _hashes(ledger)}
    document = build_forward_document(
        ledger,
        reference,
        expected_ledger_hashes=_hashes(ledger),
        expected_reference_sha256=digest,
    )
    published = publish_forward_document(document, output, ledger)
    assert {name: (ledger / name).read_bytes() for name in before} == before
    return ledger, output, document, published


def test_builder_keeps_statuses_populations_and_zero_distinct(tmp_path: Path):
    ledger, output, document, published = _build(tmp_path)
    by_id = {row["identity_id"]: row for row in document["rows"]}
    assert published["file_status"] == "written"
    assert by_id["sidecar|AAA"]["population"] == "brain_linked"
    assert by_id["sidecar|BBB"]["population"] == "brain_unlinked"
    assert by_id["sweet|CCC"]["population"] == "sweetspot"
    assert by_id["sweet|BLANK"]["population"] == "sweetspot_blank"
    assert by_id["sweet|CCC"]["horizons"]["T+1"]["status"] == "APPROX_AVAILABLE"
    assert by_id["sweet|CCC"]["horizons"]["T+1"]["return_pct"] == 0
    assert by_id["sidecar|BBB"]["horizons"]["T+1"]["status"] == "T0_REFERENCE_MISSING"
    assert by_id["sidecar|BBB"]["horizons"]["T+1"]["return_pct"] is None
    assert by_id["sweet|BLANK"]["horizons"]["T+1"]["return_pct"] is None
    assert by_id["sidecar|GAP"]["horizons"]["T+1"]["status"] == "TARGET_MISSING"
    assert by_id["sidecar|GAP"]["horizons"]["T+1"]["return_pct"] is None
    assert by_id["sidecar|AAA"]["horizons"]["T+5"]["status"] == "APPROX_AVAILABLE"
    assert by_id["sidecar|AAA"]["horizons"]["T+5"]["target_session"] == "2026-11-18"
    assert by_id["sidecar|AAA"]["horizons"]["T+10"]["status"] == "NOT_YET_OBSERVED"
    assert by_id["sidecar|AAA"]["horizons"]["T+10"]["return_pct"] is None
    assert by_id["sidecar|JUMP"]["horizons"]["T+1"]["status"] == "DISCONTINUITY"
    assert by_id["sidecar|JUMP"]["horizons"]["T+1"]["included_in_primary"] is False
    assert by_id["sidecar|TRUN"]["horizons"]["T+1"]["status"] == "TRUNCATED_SESSION"
    assert all(row["t0_price_used_as_denominator"] is False for row in document["rows"])
    assert "blended" not in document["coverage"]
    assert set(document["coverage"]) == {"brain_linked", "brain_unlinked", "sweetspot", "sweetspot_blank"}
    panel = load_row_panel(DurableRowStore(ledger), outcomes_root=output)
    displayed = {row["row_id"]: row for row in panel["rows"]}
    assert horizon_text(displayed["sweet|CCC"]["horizons"]["T+1"]) == "0.00%"
    assert horizon_text(displayed["sidecar|BBB"]["horizons"]["T+1"]) == "T0_REFERENCE_MISSING"
    assert horizon_text(displayed["sidecar|JUMP"]["horizons"]["T+1"]) == "DISCONTINUITY"
    assert displayed["sidecar|JUMP"]["horizons"]["T+1"]["return_pct"] is None
    linked = apply_filters(panel["rows"], population="brain_linked")
    unlinked = apply_filters(panel["rows"], population="brain_unlinked")
    assert [row["row_id"] for row in linked] == ["sidecar|AAA"]
    assert "sidecar|AAA" not in {row["row_id"] for row in unlinked}
    assert panel["forward_outcomes"]["status"] == "attached"
    assert panel["t_plus_recomputed"] is False


def test_republish_is_unchanged_and_a_later_as_of_keeps_the_old_generation(tmp_path: Path):
    ledger, output, document, first = _build(tmp_path)
    original = Path(first["path"]).read_bytes()
    again = publish_forward_document(document, output, ledger)
    assert again["file_status"] == "unchanged"
    assert Path(first["path"]).read_bytes() == original
    longer = SESSIONS + ["2026-11-19"]
    digest = _write_reference(tmp_path / "later.json", longer)
    later = build_forward_document(
        ledger,
        tmp_path / "later.json",
        expected_ledger_hashes=_hashes(ledger),
        expected_reference_sha256=digest,
    )
    second = publish_forward_document(later, output, ledger)
    assert second["generation_id"] != first["generation_id"]
    assert Path(first["path"]).read_bytes() == original
    assert later["as_of"] == "2026-11-19"
    attached = attachable_outcomes(ledger, output)
    assert attached is not None
    assert attached["as_of"] == "2026-11-19"


def test_conflicting_generation_and_bad_inputs_are_refused(tmp_path: Path):
    ledger, output, _document, first = _build(tmp_path)
    path = Path(first["path"])
    path.write_bytes(path.read_bytes().replace(b"APPROX_AVAILABLE", b"APPROX_ALTERED!!"))
    with pytest.raises(ForwardBuildError) as refused:
        publish_forward_document(_rebuild(ledger, tmp_path), output, ledger)
    assert refused.value.reason == "REFUSE_OVERWRITE"
    with pytest.raises(ForwardBuildError) as mismatch:
        build_forward_document(
            ledger,
            tmp_path / "reference_store.json",
            expected_ledger_hashes=STAGE2_LEDGER_HASHES,
            expected_reference_sha256="0" * 64,
        )
    assert mismatch.value.reason == "LEDGER_HASH_MISMATCH"
    store = json.loads((tmp_path / "reference_store.json").read_text(encoding="utf-8"))
    store["rows"].append({"symbol": "AAA", "session": "2026-11-19", "close": 1, "clock": "14:50"})
    store["content_sha256"] = _digest(store)
    planted = tmp_path / "lookahead.json"
    planted.write_text(json.dumps(store, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ForwardBuildError) as lookahead:
        build_forward_document(
            ledger,
            planted,
            expected_ledger_hashes=_hashes(ledger),
            expected_reference_sha256=store["content_sha256"],
        )
    assert lookahead.value.reason == "LOOKAHEAD_ROW"


def _rebuild(ledger: Path, tmp_path: Path) -> dict:
    return build_forward_document(
        ledger,
        tmp_path / "reference_store.json",
        expected_ledger_hashes=_hashes(ledger),
        expected_reference_sha256=json.loads((tmp_path / "reference_store.json").read_text(encoding="utf-8"))["content_sha256"],
    )


def test_loader_falls_closed(tmp_path: Path):
    ledger, output, _document, _published = _build(tmp_path)
    assert load_row_panel(DurableRowStore(ledger), outcomes_root=tmp_path / "missing")["forward_outcomes"]["status"] == HORIZON_STATUS
    index = output / "index.json"
    loaded = json.loads(index.read_text(encoding="utf-8"))
    loaded["generations"][0]["ledger_hashes"]["identities.jsonl"] = "0" * 64
    index.write_text(json.dumps(loaded, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    panel = load_row_panel(DurableRowStore(ledger), outcomes_root=output)
    assert panel["forward_outcomes"]["status"] == HORIZON_STATUS
    assert all(row["horizons"]["T+1"]["status"] == HORIZON_STATUS for row in panel["rows"])


def test_stage2_ledger_and_guardian_forward_stay_byte_stable():
    import subprocess

    for name, digest in STAGE2_LEDGER_HASHES.items():
        assert hashlib.sha256((DURABLE / name).read_bytes()).hexdigest() == digest
    committed = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:research/guardian_research/forward.py"])
    assert hashlib.sha256(GUARDIAN.read_bytes()).digest() == hashlib.sha256(committed).digest()

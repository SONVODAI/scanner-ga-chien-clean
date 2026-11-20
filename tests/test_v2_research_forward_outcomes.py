"""Derived Ledger T+ generations stay outside the sealed store."""

from __future__ import annotations

import datetime
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
    STAGE2_REFERENCE_SHA256,
    ForwardBuildError,
    attachable_outcomes,
    build_forward_document,
    main,
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


OUTCOMES_GENERATION_SHA256 = "14aeba749aee6d3d4811ab68257ea2819a75c85aa1f3b253a1fa34287cc80dc6"
OUTCOMES_GENERATION = (
    ROOT
    / "research"
    / "v2_research_ledger"
    / "outcomes"
    / "generations"
    / "2026-11-18_41f36ca0cad9_a90e163943d8.json"
)
PUBLISHED_GENERATION_SHA256 = "5329e539635ce7393400b83ef7d5cc507184fc152f4aad657db4d257df59f1a5"
PUBLISHED_GENERATION = (
    ROOT
    / "research"
    / "v2_research_ledger"
    / "outcomes"
    / "generations"
    / "2026-11-19_41f36ca0cad9_63b98229a9f9.json"
)
UNTOUCHED = (
    "app.py",
    "modules/v2_research_ledger_panel/ui.py",
    "research/guardian_research/forward.py",
    "research/guardian_research/reference_export.py",
    ".github/workflows/guardian-close.yml",
    ".github/workflows/post-close-research.yml",
    "modules/live_candidate_v2_camera/sidecar.py",
)


def test_stage2_ledger_and_guardian_forward_stay_byte_stable():
    import subprocess

    for name, digest in STAGE2_LEDGER_HASHES.items():
        assert hashlib.sha256((DURABLE / name).read_bytes()).hexdigest() == digest
    committed = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:research/guardian_research/forward.py"])
    assert hashlib.sha256(GUARDIAN.read_bytes()).digest() == hashlib.sha256(committed).digest()
    index = json.loads((ROOT / "research" / "v2_research_ledger" / "outcomes" / "index.json").read_text(encoding="utf-8"))
    assert index["schema"] == "v2_research_forward_index.v1"
    assert [item["generation_id"] for item in index["generations"]] == [
        "2026-11-18_41f36ca0cad9_a90e163943d8",
        "2026-11-19_41f36ca0cad9_63b98229a9f9",
    ]
    assert hashlib.sha256(OUTCOMES_GENERATION.read_bytes()).hexdigest() == OUTCOMES_GENERATION_SHA256
    assert hashlib.sha256(PUBLISHED_GENERATION.read_bytes()).hexdigest() == PUBLISHED_GENERATION_SHA256


def test_newer_price_book_derives_as_of_without_stage2_pins(tmp_path: Path):
    source = (ROOT / "research" / "v2_research_ledger" / "forward_outcomes.py").read_text(encoding="utf-8")
    assert "date.today" not in source
    assert "datetime.now" not in source
    ledger = tmp_path / "durable"
    reference = tmp_path / "later.json"
    _write_ledger(ledger)
    before = {name: (ledger / name).read_bytes() for name in STAGE2_LEDGER_HASHES}
    calendar = SESSIONS + ["2026-11-19"]
    digest = _write_reference(reference, calendar)
    document = build_forward_document(ledger, reference)
    assert document["as_of"] == "2026-11-19"
    assert document["trading_sessions"][-1] == "2026-11-19"
    assert document["reference_sha256"] == digest
    assert document["price_basis"] == "APPROX_LAST_5M_CLOSE"
    assert document["reference_source"] == "vnstock4_kbs"
    assert document["ledger_hashes"] == _hashes(ledger)
    assert document["ledger_hashes"] != STAGE2_LEDGER_HASHES
    assert {name: (ledger / name).read_bytes() for name in before} == before
    published = publish_forward_document(document, tmp_path / "outcomes", ledger)
    panel = load_row_panel(DurableRowStore(ledger), outcomes_root=tmp_path / "outcomes")
    assert published["file_status"] == "written"
    assert panel["forward_outcomes"]["status"] == "attached"
    assert panel["forward_outcomes"]["as_of"] == "2026-11-19"
    assert panel["t_plus_recomputed"] is False
    displayed = {row["row_id"]: row for row in panel["rows"]}
    assert horizon_text(displayed["sidecar|BBB"]["horizons"]["T+1"]) == "T0_REFERENCE_MISSING"
    assert displayed["sidecar|BBB"]["horizons"]["T+1"]["return_pct"] is None
    assert displayed["sidecar|AAA"]["t0_date"] == "2026-11-11"


def test_unchanged_inputs_do_not_duplicate_a_generation(tmp_path: Path):
    ledger, output, document, first = _build(tmp_path)
    again = publish_forward_document(document, output, ledger)
    index = json.loads((output / "index.json").read_text(encoding="utf-8"))
    assert again["file_status"] == "unchanged"
    assert again["index_status"] == "unchanged"
    assert len(index["generations"]) == 1
    assert list((output / "generations").glob("*.json")) == [Path(first["path"])]


def test_invalid_reference_calendar_and_manifest_block_publication(tmp_path: Path):
    ledger, output, _document, _published = _build(tmp_path)
    index_bytes = (output / "index.json").read_bytes()
    generation = next((output / "generations").glob("*.json"))
    generation_bytes = generation.read_bytes()
    reference = tmp_path / "reference_store.json"
    store = json.loads(reference.read_text(encoding="utf-8"))

    broken_checksum = tmp_path / "checksum.json"
    checksum = dict(store)
    checksum["rows"][0]["close"] = 1
    broken_checksum.write_text(json.dumps(checksum, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ForwardBuildError) as checksum_error:
        build_forward_document(ledger, broken_checksum)
    assert checksum_error.value.reason == "REFERENCE_CHECKSUM_MISMATCH"

    broken_basis = tmp_path / "basis.json"
    basis = dict(store)
    basis["price_basis"] = "NOMINATION_PRICE"
    basis["content_sha256"] = _digest(basis)
    broken_basis.write_text(json.dumps(basis, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ForwardBuildError) as basis_error:
        build_forward_document(ledger, broken_basis)
    assert basis_error.value.reason == "REFERENCE_BASIS_MISMATCH"

    broken_calendar = tmp_path / "calendar.json"
    calendar = dict(store)
    calendar["trading_sessions"] = list(reversed(calendar["trading_sessions"]))
    calendar["content_sha256"] = _digest(calendar)
    broken_calendar.write_text(json.dumps(calendar, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ForwardBuildError) as calendar_error:
        build_forward_document(ledger, broken_calendar)
    assert calendar_error.value.reason == "CALENDAR_INVALID"

    manifest_path = ledger / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["identity_count"] = 0
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ForwardBuildError) as manifest_error:
        build_forward_document(ledger, reference)
    assert manifest_error.value.reason == "MANIFEST_COUNT_MISMATCH"

    with pytest.raises(ForwardBuildError) as pinned:
        build_forward_document(
            ledger,
            reference,
            expected_ledger_hashes=STAGE2_LEDGER_HASHES,
            expected_reference_sha256=STAGE2_REFERENCE_SHA256,
        )
    assert pinned.value.reason == "LEDGER_HASH_MISMATCH"
    assert (output / "index.json").read_bytes() == index_bytes
    assert generation.read_bytes() == generation_bytes
    assert len(list((output / "generations").glob("*.json"))) == 1


def test_failed_publication_preserves_the_last_indexed_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger, output, _document, first = _build(tmp_path)
    index = output / "index.json"
    original_index = index.read_bytes()
    original_generation = Path(first["path"]).read_bytes()
    digest = _write_reference(tmp_path / "later.json", SESSIONS + ["2026-11-19"])
    later = build_forward_document(
        ledger,
        tmp_path / "later.json",
        expected_reference_sha256=digest,
    )
    real_write = publish_forward_document.__globals__["_atomic_write"]

    def _fail_index(path: Path, payload: bytes) -> None:
        if path.name == "index.json":
            raise OSError("index write failed")
        real_write(path, payload)

    monkeypatch.setattr("research.v2_research_ledger.forward_outcomes._atomic_write", _fail_index)
    with pytest.raises(OSError, match="index write failed"):
        publish_forward_document(later, output, ledger)
    assert index.read_bytes() == original_index
    assert Path(first["path"]).read_bytes() == original_generation
    assert not (output / "generations" / f"{_generation_name(later)}").exists()
    attached = attachable_outcomes(ledger, output)
    assert attached is not None
    assert attached["as_of"] == "2026-11-18"


def test_corrupt_index_is_not_replaced(tmp_path: Path):
    ledger, output, _document, first = _build(tmp_path)
    index = output / "index.json"
    index.write_text("{", encoding="utf-8")
    corrupt = index.read_bytes()
    generation = Path(first["path"]).read_bytes()
    digest = _write_reference(tmp_path / "later.json", SESSIONS + ["2026-11-19"])
    later = build_forward_document(ledger, tmp_path / "later.json", expected_reference_sha256=digest)
    with pytest.raises(ForwardBuildError) as refused:
        publish_forward_document(later, output, ledger)
    assert refused.value.reason == "INDEX_INVALID"
    assert index.read_bytes() == corrupt
    assert Path(first["path"]).read_bytes() == generation
    assert not (output / "generations" / f"{_generation_name(later)}").exists()


def test_cli_dry_run_writes_nothing_and_publish_is_explicit(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    ledger = tmp_path / "durable"
    reference = tmp_path / "reference_store.json"
    output = tmp_path / "outcomes"
    _write_ledger(ledger)
    _write_reference(reference)
    code = main(["--ledger", str(ledger), "--reference", str(reference), "--output-root", str(output)])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["ok"] is True
    assert report["mode"] == "dry_run"
    assert report["as_of"] == "2026-11-18"
    assert report["file_status"] == "would_write"
    assert not output.exists()
    code = main(["--ledger", str(ledger), "--reference", str(reference), "--output-root", str(output), "--publish"])
    published = json.loads(capsys.readouterr().out)
    assert code == 0
    assert published["mode"] == "publish"
    assert published["file_status"] == "written"
    code = main(["--ledger", str(ledger), "--reference", str(reference), "--output-root", str(output), "--publish"])
    repeat = json.loads(capsys.readouterr().out)
    assert code == 0
    assert repeat["file_status"] == "unchanged"
    assert repeat["index_status"] == "unchanged"
    assert len(list((output / "generations").glob("*.json"))) == 1


def test_repository_publication_requires_a_separate_approval(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    ledger = tmp_path / "durable"
    reference = tmp_path / "reference_store.json"
    _write_ledger(ledger)
    _write_reference(reference)
    outcomes = ROOT / "research" / "v2_research_ledger" / "outcomes"
    index = outcomes / "index.json"
    before_index = index.read_bytes()
    before_generation = OUTCOMES_GENERATION.read_bytes()
    dry = main(["--ledger", str(ledger), "--reference", str(reference), "--output-root", str(outcomes)])
    assert dry == 0
    refused = main(
        ["--ledger", str(ledger), "--reference", str(reference), "--output-root", str(outcomes), "--publish"]
    )
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert refused == 1
    assert report["reason"] == "REPOSITORY_PUBLICATION_NOT_APPROVED"
    assert index.read_bytes() == before_index
    assert OUTCOMES_GENERATION.read_bytes() == before_generation
    assert hashlib.sha256((DURABLE / "identities.jsonl").read_bytes()).hexdigest() == STAGE2_LEDGER_HASHES["identities.jsonl"]


def test_cli_dry_run_does_not_overwrite_existing_outcomes(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    ledger, output, _document, first = _build(tmp_path)
    before = {path: path.read_bytes() for path in output.rglob("*") if path.is_file()}
    same = main(["--ledger", str(ledger), "--reference", str(tmp_path / "reference_store.json"), "--output-root", str(output)])
    same_report = json.loads(capsys.readouterr().out)
    assert same == 0
    assert same_report["mode"] == "dry_run"
    assert same_report["file_status"] == "unchanged"
    assert same_report["index_status"] == "unchanged"
    assert same_report["generation_id"] == first["generation_id"]
    assert {path: path.read_bytes() for path in output.rglob("*") if path.is_file()} == before
    _write_reference(tmp_path / "later.json", SESSIONS + ["2026-11-19"])
    newer = main(["--ledger", str(ledger), "--reference", str(tmp_path / "later.json"), "--output-root", str(output)])
    newer_report = json.loads(capsys.readouterr().out)
    assert newer == 0
    assert newer_report["mode"] == "dry_run"
    assert newer_report["as_of"] == "2026-11-19"
    assert newer_report["file_status"] == "would_write"
    assert newer_report["index_status"] == "would_write"
    assert newer_report["generation_id"] != first["generation_id"]
    assert {path: path.read_bytes() for path in output.rglob("*") if path.is_file()} == before
    assert not (output / "generations" / f"{newer_report['generation_id']}.json").exists()
    broken = tmp_path / "broken.json"
    store = json.loads((tmp_path / "reference_store.json").read_text(encoding="utf-8"))
    store["rows"][0]["close"] = 1
    broken.write_text(json.dumps(store, sort_keys=True) + "\n", encoding="utf-8")
    refused = main(["--ledger", str(ledger), "--reference", str(broken), "--output-root", str(output)])
    refusal = json.loads(capsys.readouterr().out)
    assert refused == 1
    assert refusal["ok"] is False
    assert refusal["reason"] == "REFERENCE_CHECKSUM_MISMATCH"
    assert {path: path.read_bytes() for path in output.rglob("*") if path.is_file()} == before


def test_publication_change_leaves_scan_guardian_camera_and_ledger_ui(tmp_path: Path):
    import subprocess

    for relative in UNTOUCHED:
        committed = subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{relative}"])
        assert (ROOT / relative).read_bytes() == committed
    workflow = (ROOT / ".github" / "workflows" / "ledger-forward-outcomes.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "validate-only" in workflow
    assert "schedule:" not in workflow
    assert "cron:" not in workflow
    assert "pull_request:" not in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "LEDGER_FORWARD_OUTCOMES_ENABLED" in workflow
    assert "--publish" not in workflow
    assert "--approve-repository-write" not in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow
    assert "research/v2_research_ledger/outcomes" in workflow
    assert "research/v2_research_ledger/durable" in workflow
    assert "REFERENCE_NOT_VALIDATED" in workflow
    assert "CALENDAR_INVALID" in workflow
    assert "missing_return_violations" in workflow
    assert "git diff --exit-code" in workflow
    assert "git status --porcelain --untracked-files=all" in workflow
    assert "json.dumps(store" not in workflow
    assert 'store["rows"]' not in workflow
    assert "os.environ[" not in workflow.replace('os.environ.get("GUARDIAN_REFERENCE_URL", "")', "").replace('os.environ.get("GUARDIAN_REFERENCE_TOKEN", "")', "")


def _generation_name(document: dict) -> str:
    from research.v2_research_ledger.forward_outcomes import _generation_id

    return f"{_generation_id(document)}.json"


def _publish_namespace() -> dict:
    import textwrap

    workflow = (ROOT / ".github" / "workflows" / "ledger-forward-publish.yml").read_text(encoding="utf-8")
    begin = "# BEGIN LEDGER_FORWARD_PUBLISH\n"
    start = workflow.index(begin) + len(begin)
    stop = workflow.index("# END LEDGER_FORWARD_PUBLISH", start)
    namespace = {"__name__": "ledger_forward_publish"}
    exec(compile(textwrap.dedent(workflow[start:stop]), "ledger-forward-publish.yml", "exec"), namespace)
    return namespace


def _git(repo: Path, *args: str) -> str:
    import subprocess

    completed = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout


def _origin_bytes(origin: Path, relative: str) -> bytes:
    import subprocess

    return subprocess.check_output(["git", "--git-dir", str(origin), "show", f"main:{relative}"])


def _seed_repository(tmp_path: Path, namespace: dict) -> tuple[Path, Path, dict[str, object]]:
    import subprocess

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True, text=True)
    repo = tmp_path / "publisher"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    durable = repo / "research" / "v2_research_ledger" / "durable"
    durable.mkdir(parents=True)
    for name in namespace["DURABLE_FILES"]:
        (durable / name).write_text(name + "\n", encoding="utf-8")
    historical = repo / namespace["HISTORICAL_GENERATION"]
    historical.parent.mkdir(parents=True, exist_ok=True)
    historical.write_text("historical\n", encoding="utf-8")
    (repo / "research" / "v2_research_ledger" / "outcomes" / "index.json").write_text('{"generations":[]}\n', encoding="utf-8")
    guardian = repo / "research" / "guardian_research" / "outcomes.json"
    guardian.parent.mkdir(parents=True)
    guardian.write_text('{"guardian":true}\n', encoding="utf-8")
    (repo / "pattern_history.csv").write_text("symbol\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "origin", "HEAD:main")
    baseline = {
        "durable": namespace["durable_hashes"](repo),
        "history": namespace["historical_digest"](repo),
        "guardian": guardian.read_bytes(),
    }
    return origin, repo, baseline


def _stage_candidate(repo: Path, namespace: dict, baseline: dict) -> str:
    generation_id = "2026-11-19_abc123abc123_def456def456"
    path = repo / namespace["allowed_paths"](generation_id)[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"as_of": "2026-11-19", "ledger_hashes": baseline["durable"], "official_pnl": False},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    index = repo / "research" / "v2_research_ledger" / "outcomes" / "index.json"
    index.write_text(json.dumps({"generations": [generation_id]}, sort_keys=True) + "\n", encoding="utf-8")
    return generation_id


def _other_clone(tmp_path: Path, origin: Path) -> Path:
    import subprocess

    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(origin), str(other)], check=True, capture_output=True, text=True)
    _git(other, "config", "user.name", "test")
    _git(other, "config", "user.email", "test@example.com")
    return other


def test_publish_workflow_is_manual_and_the_dry_run_workflow_is_unchanged():
    import subprocess

    dry = ROOT / ".github" / "workflows" / "ledger-forward-outcomes.yml"
    committed = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:.github/workflows/ledger-forward-outcomes.yml"])
    assert dry.read_bytes() == committed
    workflow = (ROOT / ".github" / "workflows" / "ledger-forward-publish.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "cron:" not in workflow
    assert "pull_request:" not in workflow
    assert "\n  push:" not in workflow
    assert "contents: write" in workflow
    assert "contents: read" not in workflow
    assert "LEDGER_FORWARD_PUBLISH_ENABLED == 'true'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "publish-2026-11-19" in workflow
    assert "fetch-depth: 0" in workflow
    assert "ref: main" in workflow
    assert "cancel-in-progress: false" in workflow
    assert '"push", "origin", "HEAD:main"' in workflow
    assert 'push", "--force"' not in workflow
    assert "git push --force" not in workflow
    assert "+HEAD" not in workflow
    assert '"--force", "--force-with-lease", "--force-if-includes"' in workflow
    assert "git clean" not in workflow
    assert "checkout --" not in workflow
    assert "--approve-repository-write" in workflow
    body = workflow[workflow.index("def publish_main"):workflow.index("if __name__")]
    assert body.index("publication_action") < body.index("commit_publication") < body.index("push_fast_forward")
    assert "already_published" in body
    builder = workflow[workflow.index("def _run_builder"):workflow.index("def publish_main")]
    assert '"--publish"' in builder
    assert '"--approve-repository-write"' in builder
    namespace = _publish_namespace()
    assert hashlib.sha256(OUTCOMES_GENERATION.read_bytes()).hexdigest() == namespace["HISTORICAL_SHA256"]


def test_dispatch_and_price_book_fail_closed(tmp_path: Path):
    namespace = _publish_namespace()
    namespace["require_dispatch_context"]("true", "publish-2026-11-19", "refs/heads/main")
    refused = (
        (None, "publish-2026-11-19", "refs/heads/main", "PUBLICATION_DISABLED"),
        ("true", "validate-only", "refs/heads/main", "CONFIRMATION_REFUSED"),
        ("true", "publish-2026-11-19", "refs/heads/other", "BRANCH_REFUSED"),
    )
    for enabled, confirm, ref, reason in refused:
        with pytest.raises(namespace["PublicationRefusal"]) as error:
            namespace["require_dispatch_context"](enabled, confirm, ref)
        assert error.value.reason == reason
    good = tmp_path / "good.json"
    _write_reference(good, SESSIONS + ["2026-11-19"])
    store = namespace["validated_store"](good)
    receipt = namespace["safe_receipt"](store)
    assert receipt == {
        "as_of": "2026-11-19",
        "content_sha256": store["content_sha256"],
        "first_session": "2026-11-11",
        "last_session": "2026-11-19",
        "price_basis": "APPROX_LAST_5M_CLOSE",
        "session_count": 7,
        "source": "vnstock4_kbs",
    }
    assert "rows" not in receipt
    current = tmp_path / "current.json"
    _write_reference(current)
    with pytest.raises(namespace["PublicationRefusal"]) as as_of_error:
        namespace["validated_store"](current)
    assert as_of_error.value.reason == "AS_OF_REFUSED"
    broken = tmp_path / "broken.json"
    payload = json.loads(good.read_text(encoding="utf-8"))
    payload["rows"][0]["close"] = 1
    broken.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(namespace["PublicationRefusal"]) as checksum_error:
        namespace["validated_store"](broken)
    assert checksum_error.value.reason == "REFERENCE_NOT_VALIDATED"
    calendar = json.loads(good.read_text(encoding="utf-8"))
    calendar["trading_sessions"] = list(reversed(calendar["trading_sessions"]))
    calendar["content_sha256"] = _digest(calendar)
    reversed_path = tmp_path / "reversed.json"
    reversed_path.write_text(json.dumps(calendar, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(namespace["PublicationRefusal"]) as calendar_error:
        namespace["validated_store"](reversed_path)
    assert calendar_error.value.reason == "CALENDAR_INVALID"


def test_publication_action_requires_a_new_generation_and_repeat_is_idle():
    namespace = _publish_namespace()
    generation_id = "2026-11-19_aaaaaaaaaaaa_bbbbbbbbbbbb"
    report = {
        "as_of": "2026-11-19",
        "file_status": "would_write",
        "generation_id": generation_id,
        "index_status": "would_write",
        "mode": "dry_run",
        "ok": True,
    }
    assert namespace["publication_action"](report, 0) == "publish"
    namespace["require_publish_result"]({**report, "file_status": "written", "index_status": "written", "mode": "publish"}, generation_id)
    repeat = {**report, "file_status": "unchanged", "index_status": "unchanged"}
    assert namespace["publication_action"](repeat, 0) == "already_published"
    with pytest.raises(namespace["PublicationRefusal"]) as violations:
        namespace["publication_action"](report, 2)
    assert violations.value.reason == "MISSING_RETURN_NOT_NULL"
    with pytest.raises(namespace["PublicationRefusal"]) as mismatch:
        namespace["publication_action"]({**report, "index_status": "unchanged"}, 0)
    assert mismatch.value.reason == "DRY_RUN_STATUS_REFUSED"
    with pytest.raises(namespace["PublicationRefusal"]) as old_book:
        namespace["publication_action"]({**report, "as_of": "2026-11-18", "generation_id": "2026-11-18_41f36ca0cad9_a90e163943d8"}, 0)
    assert old_book.value.reason == "AS_OF_REFUSED"
    with pytest.raises(namespace["PublicationRefusal"]) as republish:
        namespace["require_publish_result"]({**repeat, "mode": "publish"}, generation_id)
    assert republish.value.reason == "PUBLISH_FAILED"
    assert namespace["paths_block_publication"](["pattern_history.csv", "research/guardian_research/outcomes.json"]) is False
    assert namespace["paths_block_publication"](["research/v2_research_ledger/durable/identities.jsonl"]) is True
    assert namespace["paths_block_publication"](["research/v2_research_ledger/outcomes/index.json"]) is True


def test_commit_allowlist_refuses_guardian_and_force_push(tmp_path: Path):
    namespace = _publish_namespace()
    _origin, repo, baseline = _seed_repository(tmp_path, namespace)
    generation_id = _stage_candidate(repo, namespace, baseline)
    (repo / "research" / "guardian_research" / "outcomes.json").write_text('{"guardian":false}\n', encoding="utf-8")
    with pytest.raises(namespace["PublicationRefusal"]) as refused:
        namespace["commit_publication"](repo, generation_id, baseline["durable"], baseline["history"])
    assert refused.value.reason == "ALLOWLIST_REFUSED"
    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"
    assert _origin_bytes(_origin, "research/guardian_research/outcomes.json") == b'{"guardian":true}\n'
    with pytest.raises(namespace["PublicationRefusal"]) as force:
        namespace["_git"](repo, "push", "--force", "origin", "HEAD:main")
    assert force.value.reason == "FORCE_PUSH_REFUSED"
    with pytest.raises(namespace["PublicationRefusal"]) as lease:
        namespace["_git"](repo, "push", "--force-with-lease", "origin", "HEAD:main")
    assert lease.value.reason == "FORCE_PUSH_REFUSED"


def test_fast_forward_publishes_two_paths_and_rebases_an_unrelated_snapshot(tmp_path: Path):
    namespace = _publish_namespace()
    origin, repo, baseline = _seed_repository(tmp_path, namespace)
    generation_id = _stage_candidate(repo, namespace, baseline)
    namespace["commit_publication"](repo, generation_id, baseline["durable"], baseline["history"])
    other = _other_clone(tmp_path, origin)
    pattern = other / "pattern_history.csv"
    pattern.write_text("symbol\nAAA\n", encoding="utf-8")
    _git(other, "add", "pattern_history.csv")
    _git(other, "commit", "-m", "Update pattern history")
    _git(other, "push", "origin", "HEAD:main")
    pushed = namespace["push_fast_forward"](repo, generation_id, baseline["durable"], baseline["history"])
    assert pushed["rebases"] == 1
    names = _git(repo, "diff", "--name-only", "HEAD^", "HEAD").splitlines()
    assert sorted(names) == sorted(namespace["allowed_paths"](generation_id))
    assert _origin_bytes(origin, "pattern_history.csv") == b"symbol\nAAA\n"
    assert _origin_bytes(origin, "research/guardian_research/outcomes.json") == baseline["guardian"]
    assert _origin_bytes(origin, namespace["HISTORICAL_GENERATION"]) == b"historical\n"
    assert _origin_bytes(origin, "research/v2_research_ledger/durable/identities.jsonl") == b"identities.jsonl\n"
    published = json.loads(_origin_bytes(origin, namespace["allowed_paths"](generation_id)[0]))
    assert published["as_of"] == "2026-11-19"
    assert published["official_pnl"] is False
    repeat = namespace["push_fast_forward"](repo, generation_id, baseline["durable"], baseline["history"])
    assert repeat["commit"] == pushed["commit"]
    assert _git(origin, "rev-list", "--count", "main").strip() == "3"


def test_upstream_durable_or_outcomes_change_is_not_pushed(tmp_path: Path):
    namespace = _publish_namespace()
    origin, repo, baseline = _seed_repository(tmp_path, namespace)
    generation_id = _stage_candidate(repo, namespace, baseline)
    namespace["commit_publication"](repo, generation_id, baseline["durable"], baseline["history"])
    other = _other_clone(tmp_path, origin)
    durable = other / "research" / "v2_research_ledger" / "durable" / "identities.jsonl"
    durable.write_text("changed\n", encoding="utf-8")
    _git(other, "add", "research/v2_research_ledger/durable/identities.jsonl")
    _git(other, "commit", "-m", "Append ledger identity")
    _git(other, "push", "origin", "HEAD:main")
    with pytest.raises(namespace["PublicationRefusal"]) as durable_error:
        namespace["push_fast_forward"](repo, generation_id, baseline["durable"], baseline["history"])
    assert durable_error.value.reason == "UPSTREAM_LEDGER_CHANGED"
    origin_files = _git(origin, "ls-tree", "-r", "--name-only", "main")
    assert f"research/v2_research_ledger/outcomes/generations/{generation_id}.json" not in origin_files
    assert _origin_bytes(origin, "research/v2_research_ledger/durable/identities.jsonl") == b"changed\n"

    outcomes_origin, outcomes_repo, outcomes_baseline = _seed_repository(tmp_path / "outcomes", namespace)
    outcomes_id = _stage_candidate(outcomes_repo, namespace, outcomes_baseline)
    namespace["commit_publication"](outcomes_repo, outcomes_id, outcomes_baseline["durable"], outcomes_baseline["history"])
    outcomes_other = _other_clone(tmp_path / "outcomes", outcomes_origin)
    (outcomes_other / "research" / "v2_research_ledger" / "outcomes" / "index.json").write_text('{"generations":["upstream"]}\n', encoding="utf-8")
    _git(outcomes_other, "add", "research/v2_research_ledger/outcomes/index.json")
    _git(outcomes_other, "commit", "-m", "Replace outcomes index")
    _git(outcomes_other, "push", "origin", "HEAD:main")
    with pytest.raises(namespace["PublicationRefusal"]) as outcomes_error:
        namespace["push_fast_forward"](outcomes_repo, outcomes_id, outcomes_baseline["durable"], outcomes_baseline["history"])
    assert outcomes_error.value.reason == "UPSTREAM_LEDGER_CHANGED"
    assert _origin_bytes(outcomes_origin, "research/v2_research_ledger/outcomes/index.json") == b'{"generations":["upstream"]}\n'
    assert not (outcomes_origin / "rebase-merge").exists()


def test_extra_local_history_and_immutable_files_fail_closed(tmp_path: Path):
    namespace = _publish_namespace()
    origin, repo, baseline = _seed_repository(tmp_path, namespace)
    generation_id = _stage_candidate(repo, namespace, baseline)
    namespace["commit_publication"](repo, generation_id, baseline["durable"], baseline["history"])
    (repo / "pattern_history.csv").write_text("symbol\nextra\n", encoding="utf-8")
    _git(repo, "add", "pattern_history.csv")
    _git(repo, "commit", "-m", "local snapshot")
    with pytest.raises(namespace["PublicationRefusal"]) as history:
        namespace["push_fast_forward"](repo, generation_id, baseline["durable"], baseline["history"])
    assert history.value.reason == "HISTORY_REFUSED"
    assert _git(origin, "rev-list", "--count", "main").strip() == "1"

    fresh_origin, fresh, fresh_baseline = _seed_repository(tmp_path / "immutable", namespace)
    (fresh / namespace["HISTORICAL_GENERATION"]).write_text("rewritten\n", encoding="utf-8")
    with pytest.raises(namespace["PublicationRefusal"]) as historical:
        namespace["assert_immutable"](fresh, fresh_baseline["durable"], fresh_baseline["history"])
    assert historical.value.reason == "HISTORICAL_GENERATION_CHANGED"
    (fresh / "research" / "v2_research_ledger" / "durable" / "manifest.json").write_text("rewritten\n", encoding="utf-8")
    with pytest.raises(namespace["PublicationRefusal"]) as durable:
        namespace["assert_immutable"](fresh, fresh_baseline["durable"], fresh_baseline["history"])
    assert durable.value.reason == "DURABLE_CHANGED"
    assert _git(fresh_origin, "rev-list", "--count", "main").strip() == "1"


def test_real_publication_commits_one_generation_and_a_repeat_does_not(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    import subprocess

    namespace = _publish_namespace()
    origin = tmp_path / "origin.git"
    repo = tmp_path / "publisher"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    ledger = repo / "research" / "v2_research_ledger" / "durable"
    output = repo / "research" / "v2_research_ledger" / "outcomes"
    _write_ledger(ledger)
    first_reference = tmp_path / "reference_store.json"
    _write_reference(first_reference)
    document = build_forward_document(ledger, first_reference)
    first = publish_forward_document(document, output, ledger)
    historical = repo / namespace["HISTORICAL_GENERATION"]
    historical.parent.mkdir(parents=True, exist_ok=True)
    historical.write_text("sealed-history\n", encoding="utf-8")
    assert Path(first["path"]).name != historical.name
    guardian = repo / "research" / "guardian_research" / "outcomes.json"
    guardian.parent.mkdir(parents=True)
    guardian.write_text('{"guardian":true}\n', encoding="utf-8")
    before_first = Path(first["path"]).read_bytes()
    before_durable = {name: (ledger / name).read_bytes() for name in namespace["DURABLE_FILES"]}
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "origin", "HEAD:main")
    baseline_durable = namespace["durable_hashes"](repo)
    baseline_history = namespace["historical_digest"](repo)
    later = tmp_path / "later.json"
    _write_reference(later, SESSIONS + ["2026-11-19"])
    code = main(
        [
            "--ledger",
            str(ledger),
            "--reference",
            str(later),
            "--output-root",
            str(output),
            "--publish",
            "--approve-repository-write",
        ]
    )
    published = json.loads(capsys.readouterr().out)
    assert code == 0
    assert published["mode"] == "publish"
    assert published["as_of"] == "2026-11-19"
    assert published["file_status"] == "written"
    assert published["index_status"] == "written"
    generation_id = published["generation_id"]
    assert generation_id.startswith("2026-11-19_")
    namespace["commit_publication"](repo, generation_id, baseline_durable, baseline_history)
    pushed = namespace["push_fast_forward"](repo, generation_id, baseline_durable, baseline_history)
    assert pushed["rebases"] == 0
    assert sorted(_git(repo, "diff", "--name-only", "HEAD^", "HEAD").splitlines()) == sorted(namespace["allowed_paths"](generation_id))
    assert {name: _origin_bytes(origin, f"research/v2_research_ledger/durable/{name}") for name in before_durable} == before_durable
    assert _origin_bytes(origin, namespace["HISTORICAL_GENERATION"]) == b"sealed-history\n"
    assert _origin_bytes(origin, str(Path(first["path"]).relative_to(repo))) == before_first
    assert _origin_bytes(origin, "research/guardian_research/outcomes.json") == b'{"guardian":true}\n'
    origin_index = json.loads(_origin_bytes(origin, "research/v2_research_ledger/outcomes/index.json"))
    assert [item["generation_id"] for item in origin_index["generations"]] == [first["generation_id"], generation_id]
    dry = main(["--ledger", str(ledger), "--reference", str(later), "--output-root", str(output)])
    repeat = json.loads(capsys.readouterr().out)
    assert dry == 0
    assert namespace["publication_action"](repeat, namespace["missing_return_violations"](build_forward_document(ledger, later))) == "already_published"
    assert len(list((output / "generations").glob("*.json"))) == 3
    assert _git(origin, "rev-parse", "main").strip() == pushed["commit"]


DAILY_TRACKED = {"HPG", "VCB", "SSI"}


def _daily_namespace() -> dict:
    import textwrap

    workflow = (ROOT / ".github" / "workflows" / "ledger-forward-daily.yml").read_text(encoding="utf-8")
    begin = "# BEGIN LEDGER_FORWARD_DAILY\n"
    start = workflow.index(begin) + len(begin)
    stop = workflow.index("# END LEDGER_FORWARD_DAILY", start)
    namespace = {"__name__": "ledger_forward_daily"}
    exec(compile(textwrap.dedent(workflow[start:stop]), "ledger-forward-daily.yml", "exec"), namespace)
    return namespace


def _utc(day: str, hour: int, minute: int) -> datetime.datetime:
    year, month, day_number = (int(part) for part in day.split("-"))
    return datetime.datetime(year, month, day_number, hour, minute, tzinfo=datetime.timezone.utc)


def _daily_store(sessions: list[str], rows: list[dict], rejections: list[dict] | None = None, tracked_count: int = 3) -> dict:
    store = build_reference_store(pd.DataFrame(rows), sessions, as_of=sessions[-1])
    store["rejections"] = [] if rejections is None else rejections
    store["coverage"] = {"tracked_count": tracked_count}
    store["content_sha256"] = _digest(store)
    return store


def _closes(sessions: list[str], *, omit: set[tuple[str, str]] | None = None, truncated: set[tuple[str, str]] | None = None, extra: list[dict] | None = None) -> list[dict]:
    skipped = omit or set()
    early = truncated or set()
    rows = []
    for day in sessions:
        for index, symbol in enumerate(("HPG", "VCB", "SSI")):
            if (symbol, day) in skipped:
                continue
            rows.append({
                "symbol": symbol,
                "session": day,
                "close": 1000 + index * 10,
                "clock": "14:30" if (symbol, day) in early else "14:50",
            })
    rows.extend(extra or [])
    return rows


def _prior(sessions: list[str], sha: str) -> dict:
    return {
        "as_of": sessions[-1],
        "generation_id": f"{sessions[-1]}_aaaaaaaaaaaa_bbbbbbbbbbbb",
        "reference_sha256": sha,
        "trading_sessions": list(sessions),
    }


def _assess(namespace: dict, store: dict, prior: dict, moment: datetime.datetime, mode: str = "schedule", tracked: set[str] | None = None) -> dict:
    ict_day = moment.astimezone(namespace["ICT"]).date().isoformat()
    return namespace["assess_publication"](
        store,
        prior,
        today_ict=ict_day,
        mode=mode,
        tracked=DAILY_TRACKED if tracked is None else tracked,
        moment=moment,
    )


def test_daily_workflow_keeps_the_manual_workflows_and_maps_four_slots():
    import subprocess

    namespace = _daily_namespace()
    workflow = (ROOT / ".github" / "workflows" / "ledger-forward-daily.yml").read_text(encoding="utf-8")
    assert workflow.count("cron:") == 4
    for slot in namespace["SCHEDULED_SLOTS"]:
        assert workflow.count(f'cron: "{slot["cron"]}"') == 1
    assert "workflow_dispatch:" in workflow
    assert "publish-next-session" in workflow
    assert "publish-holiday-gap" in workflow
    assert "pull_request:" not in workflow
    assert "\n  push:" not in workflow
    assert "contents: write" in workflow
    assert "LEDGER_FORWARD_DAILY_ENABLED == 'true'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "group: ledger-forward-publish" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "fetch-depth: 0" in workflow
    assert "ref: main" in workflow
    assert '"push", "origin", "HEAD:main"' in workflow
    assert '"--force", "--force-with-lease", "--force-if-includes"' in workflow
    assert "git push --force" not in workflow
    assert 'push", "--force"' not in workflow
    assert "git clean" not in workflow
    assert "checkout --" not in workflow
    assert "--approve-repository-write" in workflow
    assert "json.dumps(store" not in workflow
    assert "gh variable" not in workflow
    assert "LEDGER_FORWARD_PUBLISH_ENABLED" not in workflow
    for relative in (".github/workflows/ledger-forward-publish.yml", ".github/workflows/ledger-forward-outcomes.yml"):
        committed = subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{relative}"])
        assert (ROOT / relative).read_bytes() == committed
        text = committed.decode("utf-8")
        assert "LEDGER_FORWARD_DAILY_ENABLED" not in text
        assert "publish-next-session" not in text
        assert "cron:" not in text
    monday = datetime.date(2026, 11, 16)
    for slot in namespace["SCHEDULED_SLOTS"]:
        for offset in range(5):
            day = monday + datetime.timedelta(days=offset)
            assert day.isoweekday() == offset + 1
            moment = datetime.datetime(day.year, day.month, day.day, slot["utc_hour"], slot["utc_minute"], tzinfo=datetime.timezone.utc)
            ict = moment.astimezone(namespace["ICT"])
            assert (ict.hour, ict.minute) == (slot["ict_hour"], slot["ict_minute"])
            if slot["kind"] == "morning":
                assert ict.date() == day + datetime.timedelta(days=1)
                assert ict.isoweekday() == offset + 2
            else:
                assert ict.date() == day
                assert ict.isoweekday() == offset + 1
    thursday_morning = _utc("2026-11-18", 23, 40)
    assert thursday_morning.astimezone(namespace["ICT"]) == datetime.datetime(2026, 11, 19, 6, 40, tzinfo=namespace["ICT"])
    assert namespace["unchanged_disposition"]("2026-11-17", thursday_morning) == "PRICE_BOOK_NOT_ADVANCED"
    assert namespace["unchanged_disposition"]("2026-11-18", thursday_morning) == "already_published"
    saturday_morning = _utc("2026-11-20", 23, 40)
    assert saturday_morning.astimezone(namespace["ICT"]) == datetime.datetime(2026, 11, 21, 6, 40, tzinfo=namespace["ICT"])
    assert namespace["unchanged_disposition"]("2026-11-20", saturday_morning) == "already_published"
    assert namespace["unchanged_disposition"]("2026-11-19", saturday_morning) == "PRICE_BOOK_NOT_ADVANCED"
    current_evening = _utc("2026-11-18", 12, 10)
    assert namespace["unchanged_disposition"]("2026-11-18", current_evening) == "already_published"


def test_daily_slots_wait_or_alert_without_inventing_a_session():
    namespace = _daily_namespace()
    sessions = ["2026-11-17"]
    store = _daily_store(sessions, _closes(sessions))
    prior = _prior(sessions, store["content_sha256"])
    before = list(store["trading_sessions"])
    for hour, minute, expected in ((12, 10, "waiting_for_price_book"), (13, 40, "waiting_for_price_book"), (16, 10, "waiting_for_price_book")):
        decision = _assess(namespace, store, prior, _utc("2026-11-18", hour, minute))
        assert decision == {"action": expected, "as_of": "2026-11-17"}
    with pytest.raises(namespace["PublicationRefusal"]) as morning:
        _assess(namespace, store, prior, _utc("2026-11-18", 23, 40))
    assert morning.value.reason == "PRICE_BOOK_NOT_ADVANCED"
    current = _daily_store(["2026-11-18"], _closes(["2026-11-18"]))
    current_prior = _prior(["2026-11-18"], current["content_sha256"])
    assert _assess(namespace, current, current_prior, _utc("2026-11-18", 23, 40))["action"] == "already_published"
    assert store["trading_sessions"] == before
    assert namespace["weekday_gaps"]("2026-11-20", "2026-11-23") == []
    assert "2026-11-21" not in namespace["weekday_gaps"]("2026-11-19", "2026-11-23")
    assert "2026-11-22" not in namespace["weekday_gaps"]("2026-11-19", "2026-11-23")


def test_daily_dispatch_holiday_gap_and_missing_symbols_fail_closed():
    namespace = _daily_namespace()
    namespace["require_dispatch_context"]("true", "publish-next-session", "refs/heads/main", "workflow_dispatch")
    assert namespace["require_dispatch_context"]("true", "publish-holiday-gap", "refs/heads/main", "schedule") == "schedule"
    assert namespace["require_dispatch_context"]("true", "publish-holiday-gap", "refs/heads/main", "workflow_dispatch") == "holiday"
    refused = (
        (None, "publish-next-session", "refs/heads/main", "schedule", "PUBLICATION_DISABLED"),
        ("true", "validate-only", "refs/heads/main", "workflow_dispatch", "CONFIRMATION_REFUSED"),
        ("true", "publish-next-session", "refs/heads/other", "workflow_dispatch", "BRANCH_REFUSED"),
        ("true", "publish-next-session", "refs/heads/main", "push", "EVENT_REFUSED"),
    )
    for enabled, confirm, ref, event, reason in refused:
        with pytest.raises(namespace["PublicationRefusal"]) as error:
            namespace["require_dispatch_context"](enabled, confirm, ref, event)
        assert error.value.reason == reason

    def book(previous: str, current: str, **kwargs) -> tuple[dict, dict]:
        sessions = [previous, current]
        store = _daily_store(sessions, _closes(sessions, **kwargs))
        return store, _prior([previous], "previous-book")

    weekend, weekend_prior = book("2026-11-20", "2026-11-21")
    with pytest.raises(namespace["PublicationRefusal"]) as weekend_error:
        _assess(namespace, weekend, weekend_prior, _utc("2026-11-23", 12, 10))
    assert weekend_error.value.reason == "WEEKEND_SESSION"

    future, future_prior = book("2026-11-19", "2026-11-20")
    with pytest.raises(namespace["PublicationRefusal"]) as future_error:
        namespace["assess_publication"](future, future_prior, today_ict="2026-11-19", mode="schedule", tracked=DAILY_TRACKED, moment=_utc("2026-11-19", 12, 10))
    assert future_error.value.reason == "FUTURE_SESSION"

    stale = _daily_store(["2026-11-18", "2026-11-19"], _closes(["2026-11-18", "2026-11-19"]))
    with pytest.raises(namespace["PublicationRefusal"]) as stale_error:
        _assess(namespace, stale, _prior(["2026-11-19", "2026-11-20"], "later"), _utc("2026-11-20", 12, 10))
    assert stale_error.value.reason == "STALE_PRICE_BOOK"

    revised = _daily_store(["2026-11-19", "2026-11-20"], _closes(["2026-11-19", "2026-11-20"]))
    revised_prior = _prior(["2026-11-19", "2026-11-20"], revised["content_sha256"])
    revised["rows"][0]["close"] = 1
    revised["content_sha256"] = _digest(revised)
    with pytest.raises(namespace["PublicationRefusal"]) as revised_error:
        _assess(namespace, revised, revised_prior, _utc("2026-11-20", 12, 10))
    assert revised_error.value.reason == "PRICE_BOOK_REVISED"

    holiday_store, holiday_prior = book("2026-11-19", "2026-11-23")
    holiday_before = list(holiday_store["trading_sessions"])
    assert namespace["weekday_gaps"]("2026-11-19", "2026-11-23") == ["2026-11-20"]
    with pytest.raises(namespace["PublicationRefusal"]) as gap_error:
        _assess(namespace, holiday_store, holiday_prior, _utc("2026-11-23", 12, 10), mode="schedule")
    assert gap_error.value.reason == "CALENDAR_GAP"
    assert holiday_store["trading_sessions"] == holiday_before
    assert "2026-11-20" not in holiday_store["trading_sessions"]
    assert _assess(namespace, holiday_store, holiday_prior, _utc("2026-11-23", 12, 10), mode="holiday")["action"] == "publish"
    national, national_prior = book("2026-08-28", "2026-09-03")
    assert namespace["weekday_gaps"]("2026-08-28", "2026-09-03") == ["2026-08-31", "2026-09-01", "2026-09-02"]
    with pytest.raises(namespace["PublicationRefusal"]) as national_error:
        _assess(namespace, national, national_prior, _utc("2026-09-03", 12, 10))
    assert national_error.value.reason == "CALENDAR_GAP"
    assert _assess(namespace, national, national_prior, _utc("2026-09-03", 12, 10), mode="holiday")["action"] == "publish"

    monday_store, monday_prior = book("2026-11-20", "2026-11-23")
    with pytest.raises(namespace["PublicationRefusal"]) as absent_gap:
        _assess(namespace, monday_store, monday_prior, _utc("2026-11-23", 12, 10), mode="holiday")
    assert absent_gap.value.reason == "GAP_ABSENT"
    published = _assess(namespace, monday_store, monday_prior, _utc("2026-11-23", 12, 10))
    assert published == {"action": "publish", "as_of": "2026-11-23", "skipped_rejections": []}
    assert monday_store["trading_sessions"] == ["2026-11-20", "2026-11-23"]

    halted, halted_prior = book("2026-11-20", "2026-11-23", omit={("SSI", "2026-11-23")})
    with pytest.raises(namespace["PublicationRefusal"]) as halted_error:
        _assess(namespace, halted, halted_prior, _utc("2026-11-23", 12, 10))
    assert halted_error.value.reason == "PRICE_BOOK_INCOMPLETE"
    holiday_halted, holiday_halted_prior = book("2026-11-19", "2026-11-23", omit={("SSI", "2026-11-23")})
    with pytest.raises(namespace["PublicationRefusal"]) as holiday_halted_error:
        _assess(namespace, holiday_halted, holiday_halted_prior, _utc("2026-11-23", 12, 10), mode="holiday")
    assert holiday_halted_error.value.reason == "PRICE_BOOK_INCOMPLETE"
    rejected, rejected_prior = book("2026-11-20", "2026-11-23")
    rejected["rejections"] = [{"session": "2026-11-23", "symbol": "SSI", "reason": "SYMBOL_ABSENT", "clock": ""}]
    rejected["content_sha256"] = _digest(rejected)
    with pytest.raises(namespace["PublicationRefusal"]) as rejected_error:
        _assess(namespace, rejected, rejected_prior, _utc("2026-11-23", 12, 10))
    assert rejected_error.value.reason == "PRICE_BOOK_INCOMPLETE"
    truncated, truncated_prior = book("2026-11-20", "2026-11-23", truncated={("VCB", "2026-11-23")})
    with pytest.raises(namespace["PublicationRefusal"]) as truncated_error:
        _assess(namespace, truncated, truncated_prior, _utc("2026-11-23", 12, 10))
    assert truncated_error.value.reason == "PRICE_BOOK_INCOMPLETE"
    earlier_truncation, earlier_prior = book("2026-11-20", "2026-11-23", truncated={("SSI", "2026-11-20")})
    assert _assess(namespace, earlier_truncation, earlier_prior, _utc("2026-11-23", 12, 10))["action"] == "publish"
    outside, outside_prior = book("2026-11-20", "2026-11-23", extra=[{"symbol": "FPT", "session": "2026-11-23", "close": 50, "clock": "14:50"}])
    with pytest.raises(namespace["PublicationRefusal"]) as outside_error:
        _assess(namespace, outside, outside_prior, _utc("2026-11-23", 12, 10))
    assert outside_error.value.reason == "PRICE_BOOK_INCOMPLETE"
    jumped = _daily_store(["2026-11-19", "2026-11-20", "2026-11-23"], _closes(["2026-11-19", "2026-11-20", "2026-11-23"]))
    with pytest.raises(namespace["PublicationRefusal"]) as jumped_error:
        _assess(namespace, jumped, _prior(["2026-11-19"], "old"), _utc("2026-11-23", 12, 10))
    assert jumped_error.value.reason == "CALENDAR_INVALID"
    mismatched = _daily_store(["2026-11-20", "2026-11-23"], _closes(["2026-11-20", "2026-11-23"]), tracked_count=2)
    with pytest.raises(namespace["PublicationRefusal"]) as universe_error:
        _assess(namespace, mismatched, _prior(["2026-11-20"], "old"), _utc("2026-11-23", 12, 10))
    assert universe_error.value.reason == "UNIVERSE_MISMATCH"


def test_daily_retired_symbol_does_not_block_the_tracked_book():
    namespace = _daily_namespace()
    sessions = ["2026-11-19", "2026-11-20"]
    moment = _utc("2026-11-20", 12, 10)
    prior = _prior(["2026-11-19"], "previous-book")

    def gate(store):
        return _assess(namespace, store, prior, moment)

    retired = _daily_store(
        sessions,
        _closes(sessions),
        rejections=[
            {"session": "2026-11-19", "symbol": "F88", "reason": "SYMBOL_ABSENT", "clock": ""},
            {"session": "2026-11-20", "symbol": "F88", "reason": "SYMBOL_ABSENT", "clock": ""},
        ],
        tracked_count=4,
    )
    decision = gate(retired)
    assert decision["action"] == "publish"
    assert decision["skipped_rejections"] == [
        {"clock": "", "reason": "SYMBOL_ABSENT", "session": "2026-11-20", "symbol": "F88"},
    ]

    blocked = _daily_store(
        sessions,
        _closes(sessions, omit={("HPG", "2026-11-20")}),
        rejections=[
            {"session": "2026-11-20", "symbol": "F88", "reason": "SYMBOL_ABSENT", "clock": ""},
            {"session": "2026-11-20", "symbol": "HPG", "reason": "SYMBOL_ABSENT", "clock": ""},
        ],
        tracked_count=4,
    )
    with pytest.raises(namespace["PublicationRefusal"]) as missing:
        gate(blocked)
    assert missing.value.reason == "PRICE_BOOK_INCOMPLETE"
    assert missing.value.skipped_rejections[0]["symbol"] == "F88"

    duplicated = _daily_store(sessions, _closes(sessions), tracked_count=3)
    duplicated["rows"].append(dict(duplicated["rows"][0]))
    duplicated["content_sha256"] = _digest(duplicated)
    with pytest.raises(namespace["PublicationRefusal"]) as duplicate:
        gate(duplicated)
    assert duplicate.value.reason == "PRICE_BOOK_INCOMPLETE"

    invalid = _daily_store(
        sessions,
        _closes(sessions, truncated={("VCB", "2026-11-20")}),
        rejections=[{"session": "2026-11-20", "symbol": "F88", "reason": "SYMBOL_ABSENT", "clock": "14:44"}],
        tracked_count=4,
    )
    with pytest.raises(namespace["PublicationRefusal"]) as truncated:
        gate(invalid)
    assert truncated.value.reason == "PRICE_BOOK_INCOMPLETE"
    assert truncated.value.skipped_rejections == [
        {"clock": "14:44", "reason": "SYMBOL_ABSENT", "session": "2026-11-20", "symbol": "F88"},
    ]

    historical_ok = _daily_store(
        sessions,
        _closes(sessions, extra=[{"symbol": "F88", "session": "2026-11-19", "close": 47000, "clock": "14:50"}]),
        tracked_count=3,
    )
    assert gate(historical_ok)["action"] == "publish"
    assert gate(historical_ok)["skipped_rejections"] == []

    priced_again = _daily_store(
        sessions,
        _closes(sessions, extra=[{"symbol": "F88", "session": "2026-11-20", "close": 47400, "clock": "14:50"}]),
        tracked_count=3,
    )
    with pytest.raises(namespace["PublicationRefusal"]) as returned:
        gate(priced_again)
    assert returned.value.reason == "PRICE_BOOK_INCOMPLETE"

    unexplained = _daily_store(sessions, _closes(sessions), tracked_count=5)
    with pytest.raises(namespace["PublicationRefusal"]) as mismatch:
        gate(unexplained)
    assert mismatch.value.reason == "UNIVERSE_MISMATCH"


def test_daily_pins_published_generations_and_the_live_watchlist():
    from research.guardian_research.universe import load_tracked_symbols

    namespace = _daily_namespace()
    namespace["assert_pinned_history"](ROOT)
    assert namespace["PINNED_GENERATIONS"][namespace["HISTORICAL_GENERATION"]] == OUTCOMES_GENERATION_SHA256
    assert namespace["PINNED_GENERATIONS"][namespace["PUBLISHED_GENERATION"]] == PUBLISHED_GENERATION_SHA256
    prior = namespace["load_prior"](ROOT)
    assert prior["as_of"] == "2026-11-19"
    assert prior["generation_id"] == "2026-11-19_41f36ca0cad9_63b98229a9f9"
    assert prior["trading_sessions"][-2:] == ["2026-11-18", "2026-11-19"]
    assert len(namespace["require_universe"](load_tracked_symbols())) == 142
    assert "F88" not in load_tracked_symbols()
    with pytest.raises(namespace["PublicationRefusal"]) as short:
        namespace["require_universe"](tuple(f"S{index:03d}" for index in range(141)))
    assert short.value.reason == "UNIVERSE_MISMATCH"
    receipt = namespace["safe_receipt"](_daily_store(["2026-11-20", "2026-11-23"], _closes(["2026-11-20", "2026-11-23"])))
    assert receipt["new_session_ok"] == 3
    assert receipt["new_session_rejections"] == 0
    assert "rows" not in receipt


def test_daily_publication_action_and_commit_allowlist(tmp_path: Path):
    namespace = _daily_namespace()
    generation_id = "2026-11-23_aaaaaaaaaaaa_bbbbbbbbbbbb"
    report = {
        "as_of": "2026-11-23",
        "file_status": "would_write",
        "generation_id": generation_id,
        "index_status": "would_write",
        "mode": "dry_run",
        "ok": True,
        "trading_sessions": ["2026-11-20", "2026-11-23"],
    }
    assert namespace["publication_action"](report, 0, "2026-11-23") == "publish"
    repeat = {**report, "file_status": "unchanged", "index_status": "unchanged"}
    assert namespace["publication_action"](repeat, 0, "2026-11-23") == "already_published"
    with pytest.raises(namespace["PublicationRefusal"]) as violations:
        namespace["publication_action"](report, 2, "2026-11-23")
    assert violations.value.reason == "MISSING_RETURN_NOT_NULL"
    with pytest.raises(namespace["PublicationRefusal"]) as pinned:
        namespace["publication_action"]({**report, "generation_id": "2026-11-19_41f36ca0cad9_63b98229a9f9", "as_of": "2026-11-19", "trading_sessions": ["2026-11-19"]}, 0, "2026-11-19")
    assert pinned.value.reason == "GENERATION_REFUSED"
    with pytest.raises(namespace["PublicationRefusal"]) as changed:
        namespace["confirm_unchanged"]({**report, "generation_id": "other"}, {"generation_id": "2026-11-19_41f36ca0cad9_63b98229a9f9"})
    assert changed.value.reason == "LEDGER_CHANGED"
    assert namespace["paths_block_publication"](["pattern_history.csv", "research/guardian_research/outcomes.json"]) is False
    assert namespace["paths_block_publication"](["research/v2_research_ledger/outcomes/index.json"]) is True

    origin, repo, seeded = _seed_repository(tmp_path, namespace)
    generations = namespace["generation_snapshot"](repo)
    generation_id = _stage_candidate(repo, namespace, seeded)
    (repo / "research" / "guardian_research" / "outcomes.json").write_text('{"guardian":false}\n', encoding="utf-8")
    with pytest.raises(namespace["PublicationRefusal"]) as allowlist:
        namespace["commit_publication"](repo, generation_id, "2026-11-19", seeded["durable"], generations)
    assert allowlist.value.reason == "ALLOWLIST_REFUSED"
    assert _origin_bytes(origin, "research/guardian_research/outcomes.json") == b'{"guardian":true}\n'
    with pytest.raises(namespace["PublicationRefusal"]) as force:
        namespace["_git"](repo, "push", "--force", "origin", "HEAD:main")
    assert force.value.reason == "FORCE_PUSH_REFUSED"
    with pytest.raises(namespace["PublicationRefusal"]) as lease:
        namespace["_git"](repo, "push", "--force-with-lease", "origin", "HEAD:main")
    assert lease.value.reason == "FORCE_PUSH_REFUSED"
    with pytest.raises(namespace["PublicationRefusal"]) as pinned_history:
        namespace["assert_pinned_history"](repo)
    assert pinned_history.value.reason == "HISTORICAL_GENERATION_CHANGED"


def test_daily_fast_forward_keeps_history_and_refuses_ledger_races(tmp_path: Path):
    namespace = _daily_namespace()
    origin, repo, seeded = _seed_repository(tmp_path, namespace)
    generations = namespace["generation_snapshot"](repo)
    generation_id = _stage_candidate(repo, namespace, seeded)
    namespace["commit_publication"](repo, generation_id, "2026-11-19", seeded["durable"], generations)
    assert _git(repo, "log", "-1", "--format=%s").strip() == "Publish Research Ledger T+ generation 2026-11-19"
    other = _other_clone(tmp_path, origin)
    pattern = other / "pattern_history.csv"
    pattern.write_text("symbol\nAAA\n", encoding="utf-8")
    _git(other, "add", "pattern_history.csv")
    _git(other, "commit", "-m", "Update pattern history")
    _git(other, "push", "origin", "HEAD:main")
    pushed = namespace["push_fast_forward"](repo, generation_id, "2026-11-19", seeded["durable"], generations)
    assert pushed["rebases"] == 1
    names = _git(repo, "diff", "--name-only", "HEAD^", "HEAD").splitlines()
    assert sorted(names) == sorted(namespace["allowed_paths"](generation_id))
    assert _origin_bytes(origin, "pattern_history.csv") == b"symbol\nAAA\n"
    assert _origin_bytes(origin, namespace["HISTORICAL_GENERATION"]) == b"historical\n"
    assert _origin_bytes(origin, "research/v2_research_ledger/durable/identities.jsonl") == b"identities.jsonl\n"
    repeat = namespace["push_fast_forward"](repo, generation_id, "2026-11-19", seeded["durable"], generations)
    assert repeat["commit"] == pushed["commit"]
    assert _git(origin, "rev-list", "--count", "main").strip() == "3"

    durable_origin, durable_repo, durable_seed = _seed_repository(tmp_path / "durable", namespace)
    durable_generations = namespace["generation_snapshot"](durable_repo)
    durable_id = _stage_candidate(durable_repo, namespace, durable_seed)
    namespace["commit_publication"](durable_repo, durable_id, "2026-11-19", durable_seed["durable"], durable_generations)
    durable_other = _other_clone(tmp_path / "durable", durable_origin)
    identity = durable_other / "research" / "v2_research_ledger" / "durable" / "identities.jsonl"
    identity.write_text("changed\n", encoding="utf-8")
    _git(durable_other, "add", "research/v2_research_ledger/durable/identities.jsonl")
    _git(durable_other, "commit", "-m", "Append ledger identity")
    _git(durable_other, "push", "origin", "HEAD:main")
    with pytest.raises(namespace["PublicationRefusal"]) as durable_error:
        namespace["push_fast_forward"](durable_repo, durable_id, "2026-11-19", durable_seed["durable"], durable_generations)
    assert durable_error.value.reason == "UPSTREAM_LEDGER_CHANGED"
    assert _origin_bytes(durable_origin, "research/v2_research_ledger/durable/identities.jsonl") == b"changed\n"
    assert f"research/v2_research_ledger/outcomes/generations/{durable_id}.json" not in _git(durable_origin, "ls-tree", "-r", "--name-only", "main")

    fresh_origin, fresh, fresh_seed = _seed_repository(tmp_path / "immutable", namespace)
    fresh_generations = namespace["generation_snapshot"](fresh)
    (fresh / namespace["HISTORICAL_GENERATION"]).write_text("rewritten\n", encoding="utf-8")
    with pytest.raises(namespace["PublicationRefusal"]) as historical:
        namespace["assert_immutable"](fresh, fresh_seed["durable"], fresh_generations)
    assert historical.value.reason == "HISTORICAL_GENERATION_CHANGED"
    assert _git(fresh_origin, "rev-list", "--count", "main").strip() == "1"

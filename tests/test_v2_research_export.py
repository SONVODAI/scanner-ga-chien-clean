"""Offline checks for the research export. No network and no VPS writes."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

from research.v2_research_ledger.export_delivery import (
    EXPORTED,
    RECOVERED,
    REDACTED,
    REFUSED,
    UNCHANGED,
    current_target,
    export_once,
    main,
    recover,
)

ROOT = Path(__file__).resolve().parents[1]
SECRET = "super-secret-value"


def _board(symbol: str = "HPG", secret: str | None = None) -> dict:
    body = {
        "as_of": "2026-10-29",
        "coverage": {"rows": 1, "by_source": {"brain_a_scan_setup": 1}},
        "freshness": {
            "artifact_as_of": "2026-10-29",
            "latest_action_bar": "2026-10-29T14:45:00+07:00",
            "latest_action_session": "2026-10-29",
            "latest_publication_session": "2026-10-29",
            "latest_t0": "2026-10-28",
            "reasons": ["MISSING_SOURCE:sidecar"],
            "status": "STALE_DATA",
        },
        "price_book": "absent",
        "rows": [
            {
                "action_state": "WAIT",
                "horizons": {"T+1": {"return_pct": None, "status": "MISSING_PRICE"}},
                "source": "brain_a_scan_setup",
                "symbol": symbol,
                "t0_date": "2026-10-28",
            }
        ],
    }
    if secret is not None:
        body["api_token"] = secret
    return body


def _write_trio(
    directory: Path,
    symbol: str = "HPG",
    *,
    secret: str | None = None,
    manifest_rows: int | None = None,
    final_buy: bool = False,
    board_sha: str | None = None,
    corrupt_manifest: bool = False,
    skip: str | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    board = (json.dumps(_board(symbol, secret)) + "\n").encode("utf-8")
    clock = (
        json.dumps(
            {"evidence": None, "schema": "v2_research_ledger_source_clock.v1", "sidecar": None, "sweet": None}
        )
        + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(board).hexdigest()
    manifest = {
        "board_bytes": len(board),
        "board_sha256": board_sha or digest,
        "clock_sha256": hashlib.sha256(clock).hexdigest(),
        "final_buy_enabled": final_buy,
        "generation_id": board_sha or digest,
        "rows": 1 if manifest_rows is None else manifest_rows,
        "schema": "v2_research_publisher_manifest.v1",
    }
    files = {
        "board.json": board,
        "source_clock.json": clock,
        "manifest.json": b"{not-json}\n" if corrupt_manifest else (json.dumps(manifest) + "\n").encode("utf-8"),
    }
    for name, payload in files.items():
        if name != skip:
            (directory / name).write_bytes(payload)


def _generation(store: Path) -> Path:
    dirs = [path for path in (store / "generations").iterdir() if path.is_dir() and not path.name.startswith(".")]
    assert len(dirs) == 1
    return dirs[0]


def test_export_publishes_one_generation_and_second_run_is_unchanged(tmp_path):
    source = tmp_path / "source"
    store = tmp_path / "store"
    _write_trio(source)
    first = export_once(source, store)
    assert first.status == EXPORTED
    assert first.rows == 1
    assert current_target(store) == first.generation_id
    board = json.loads(
        (store / "generations" / first.generation_id / "board.json").read_text(encoding="utf-8")
    )
    assert board["freshness"]["latest_t0"] == "2026-10-28"
    assert board["freshness"]["latest_action_session"] == "2026-10-29"
    assert board["rows"][0]["horizons"]["T+1"]["return_pct"] is None
    before = (store / "generations" / first.generation_id / "board.json").read_bytes()
    second = export_once(source, store)
    assert second.status == UNCHANGED
    assert second.generation_id == first.generation_id
    assert (store / "generations" / first.generation_id / "board.json").read_bytes() == before
    assert len(list((store / "generations").iterdir())) == 1


def test_refuses_corrupt_missing_hash_row_and_oversize_without_publishing(tmp_path):
    store = tmp_path / "store"
    missing = tmp_path / "missing"
    _write_trio(missing, skip="source_clock.json")
    assert export_once(missing, store).reason == "missing"
    assert not store.exists()

    corrupt = tmp_path / "corrupt"
    _write_trio(corrupt, corrupt_manifest=True)
    assert export_once(corrupt, tmp_path / "store-corrupt").reason == "corrupt"

    mismatch = tmp_path / "mismatch"
    _write_trio(mismatch, board_sha="0" * 64)
    assert export_once(mismatch, tmp_path / "store-mismatch").reason == "board_checksum"

    counted = tmp_path / "counted"
    _write_trio(counted, manifest_rows=951)
    assert export_once(counted, tmp_path / "store-counted").reason == "row_count"

    oversized = tmp_path / "oversized"
    _write_trio(oversized)
    assert export_once(oversized, tmp_path / "store-over", max_board_bytes=8).reason == "board_bounds"
    assert not (tmp_path / "store-over").exists()


def test_concurrent_replacement_writes_nothing(tmp_path):
    source = tmp_path / "source"
    store = tmp_path / "store"
    _write_trio(source)

    def _replace() -> None:
        _write_trio(source, symbol="FPT")

    result = export_once(source, store, before_second_read=_replace)
    assert result.status == REFUSED
    assert result.reason == "concurrent"
    assert not store.exists()


def test_failed_promotion_and_directory_current_keep_last_good(tmp_path):
    source_a = tmp_path / "a"
    source_b = tmp_path / "b"
    store = tmp_path / "store"
    _write_trio(source_a, symbol="HPG")
    _write_trio(source_b, symbol="FPT")
    first = export_once(source_a, store)
    good = (store / "generations" / first.generation_id / "board.json").read_bytes()
    last_good = (store / "last_good.json").read_bytes()

    def _boom(src, dst):
        raise OSError("promotion")

    failed = export_once(source_b, store, replace=_boom)
    assert failed.reason == "promotion_failed"
    assert current_target(store) == first.generation_id
    assert (store / "generations" / first.generation_id / "board.json").read_bytes() == good
    assert (store / "last_good.json").read_bytes() == last_good

    blocked = tmp_path / "blocked"
    (blocked / "current").mkdir(parents=True)
    (blocked / "current" / "keep.txt").write_text("keep", encoding="utf-8")
    _write_trio(tmp_path / "fresh")
    refused = export_once(tmp_path / "fresh", blocked)
    assert refused.reason == "current_directory"
    assert (blocked / "current" / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_restart_recovers_from_last_good_without_the_source(tmp_path):
    source = tmp_path / "source"
    store = tmp_path / "store"
    _write_trio(source)
    digest = hashlib.sha256((source / "board.json").read_bytes()).hexdigest()
    partial = store / "generations" / f".{digest}.partial"
    partial.mkdir(parents=True)
    (partial / "junk").write_text("partial", encoding="utf-8")
    exported = export_once(source, store)
    assert exported.status == EXPORTED
    assert not partial.exists()
    os.unlink(store / "current")
    shutil_source = source
    for child in shutil_source.iterdir():
        child.unlink()
    source.rmdir()
    restored = recover(store)
    assert restored.status == RECOVERED
    assert restored.generation_id == digest
    assert current_target(store) == digest
    manifest = json.loads(
        (store / "generations" / digest / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["final_buy_enabled"] is False


def test_secret_value_is_not_in_the_refusal(tmp_path, capsys):
    source = tmp_path / "source"
    _write_trio(source, secret=SECRET)
    result = export_once(source, tmp_path / "store")
    assert result.status == REFUSED
    assert result.reason == "secret_key"
    assert SECRET not in result.public_line()
    assert REDACTED != SECRET
    code = main(["--source", str(source), "--store", str(tmp_path / "cli")])
    printed = capsys.readouterr().out
    assert code == 2
    assert SECRET not in printed
    assert "secret_key" in printed


def test_exporter_does_not_import_network_or_production_modules():
    source = (ROOT / "research" / "v2_research_ledger" / "export_delivery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    banned = ("urllib", "requests", "socket", "subprocess", "artifact_server", "live_shadow")
    assert not any(any(word in name.split(".") for word in banned) for name in imported)

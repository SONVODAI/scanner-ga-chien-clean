"""Serving-pointer publication. Uses temporary directories only."""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from research.v2_research_ledger.export_delivery import EXPORTED, REFUSED, UNCHANGED, current_target
from research.v2_research_ledger.serve_generation import (
    SERVING_POINTER_NOT_UPDATED,
    diagnose_generations,
    publish_serving,
)

PUBLISHER = "e43c152e3561b2904baf70a11c5860edf8e532a0504c46aba8ccafffb288aa9f"
SERVING = "d2a0d3ab6a8015773747f955623c52f4afa95f36a1f68d25b8add6454615754d"
STAMP = datetime(2026, 10, 30, 22, 40, tzinfo=timezone.utc)


def _row(
    ident: str,
    source: str = "brain_a_scan_setup",
    t0: str = "2026-10-28",
    symbol: str = "HPG",
    cohort: str = "nomination",
) -> dict:
    return {
        "action_state": "WAIT",
        "cohort": cohort,
        "horizons": {"T+1": {"return_pct": None, "status": "MISSING_PRICE"}},
        "row_id": ident,
        "source": source,
        "symbol": symbol,
        "t0_date": t0,
        "t0_price": None,
    }


def _write_trio(directory: Path, rows: list[dict], *, final_buy: bool = False) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    board = {
        "as_of": "2026-10-29",
        "coverage": {"rows": len(rows)},
        "freshness": {"artifact_as_of": "2026-10-29", "reasons": ["MISSING_SOURCE:sidecar"]},
        "price_book": "absent",
        "rows": rows,
    }
    board_bytes = (json.dumps(board, sort_keys=True) + "\n").encode("utf-8")
    clock = (
        json.dumps(
            {"evidence": None, "schema": "v2_research_ledger_source_clock.v1", "sidecar": None, "sweet": None},
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(board_bytes).hexdigest()
    manifest = {
        "board_bytes": len(board_bytes),
        "board_sha256": digest,
        "clock_sha256": hashlib.sha256(clock).hexdigest(),
        "final_buy_enabled": final_buy,
        "generation_id": digest,
        "rows": len(rows),
        "schema": "v2_research_publisher_manifest.v1",
        "source_health": {
            "action_evidence": {"status": "PRESENT"},
            "sidecar": {"status": "MISSING"},
            "sweetspot": {"status": "MISSING"},
        },
    }
    (directory / "board.json").write_bytes(board_bytes)
    (directory / "source_clock.json").write_bytes(clock)
    (directory / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"))


def test_known_generation_mismatch_is_a_stale_serving_pointer():
    found = diagnose_generations(PUBLISHER, SERVING)
    assert found["reason"] == SERVING_POINTER_NOT_UPDATED
    assert found["publisher_generation"] == PUBLISHER
    assert found["serving_generation"] == SERVING
    assert diagnose_generations(SERVING, SERVING)["reason"] == "aligned"


def test_publish_keeps_nominations_and_stamps_manifest_only(tmp_path: Path):
    source = tmp_path / "publisher"
    store = tmp_path / "store"
    history = tmp_path / "history" / "nomination.jsonl"
    history.parent.mkdir()
    history.write_text('{"nomination_id":"keep"}\n', encoding="utf-8")
    before = history.read_bytes()
    rows = [_row("brain_a_scan_setup|2026-10-28|HPG|seen")]
    _write_trio(source, rows)
    original_board = (source / "board.json").read_bytes()
    result = publish_serving(source, store, published_at=STAMP)
    assert result.status == EXPORTED
    assert current_target(store) == result.generation_id
    served_board = (store / "generations" / result.generation_id / "board.json").read_bytes()
    assert served_board == original_board
    manifest = json.loads(
        (store / "generations" / result.generation_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["published_at"] == STAMP.isoformat()
    assert manifest["final_buy_enabled"] is False
    assert history.read_bytes() == before
    again = publish_serving(source, store, published_at=datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert again.status == UNCHANGED
    assert again.generation_id == result.generation_id
    kept = json.loads(
        (store / "generations" / result.generation_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert kept["published_at"] == STAMP.isoformat()


def test_switch_preserves_previous_nominations_and_leaves_unattributed_unattributed(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    store = tmp_path / "store"
    nomination = _row("brain_a_scan_setup|2026-10-28|HPG|seen")
    _write_trio(first, [nomination])
    extra = _row(
        "unattributed|FPT|2026-10-30",
        source="unattributed",
        t0="2026-10-30",
        symbol="FPT",
        cohort="action_unattributed",
    )
    _write_trio(second, [nomination, extra])
    assert publish_serving(first, store, published_at=STAMP).status == EXPORTED
    switched = publish_serving(second, store, published_at=STAMP)
    assert switched.status == EXPORTED
    board = json.loads((store / "generations" / switched.generation_id / "board.json").read_text(encoding="utf-8"))
    by_id = {row["row_id"]: row for row in board["rows"]}
    assert by_id[nomination["row_id"]]["cohort"] == "nomination"
    assert by_id[nomination["row_id"]]["t0_date"] == "2026-10-28"
    assert by_id[extra["row_id"]]["cohort"] == "action_unattributed"
    assert by_id[extra["row_id"]]["source"] == "unattributed"


def test_refuses_promotion_t0_change_and_dropped_nomination_without_moving_pointer(tmp_path: Path):
    good = tmp_path / "good"
    store = tmp_path / "store"
    nomination = _row("brain_a_scan_setup|2026-10-28|HPG|seen")
    _write_trio(good, [nomination])
    first = publish_serving(good, store, published_at=STAMP)
    assert first.status == EXPORTED
    pointer = (store / "current").read_text(encoding="utf-8")

    promoted = tmp_path / "promoted"
    _write_trio(
        promoted,
        [
            nomination,
            _row(
                "unattributed|FPT|2026-10-30",
                source="brain_a_scan_setup",
                cohort="action_unattributed",
                symbol="FPT",
            ),
        ],
    )
    assert publish_serving(promoted, store, published_at=STAMP).reason == "unattributed_promoted"

    changed = tmp_path / "changed"
    moved = dict(nomination)
    moved["t0_date"] = "2026-10-30"
    _write_trio(changed, [moved])
    assert publish_serving(changed, store, published_at=STAMP).reason == "t0_changed"

    dropped = tmp_path / "dropped"
    _write_trio(dropped, [_row("brain_a_scan_setup|2026-10-28|FPT|other", symbol="FPT")])
    assert publish_serving(dropped, store, published_at=STAMP).reason == "nomination_missing"
    assert (store / "current").read_text(encoding="utf-8") == pointer
    assert current_target(store) == first.generation_id


def test_failed_promotion_retains_the_previous_generation(tmp_path: Path):
    first_source = tmp_path / "first"
    second_source = tmp_path / "second"
    store = tmp_path / "store"
    _write_trio(first_source, [_row("brain_a_scan_setup|2026-10-28|HPG|seen")])
    kept_row = _row("brain_a_scan_setup|2026-10-28|HPG|seen")
    added = _row("market_aware_sweetspot|2026-10-26|FPT|seen", source="market_aware_sweetspot", symbol="FPT", t0="2026-10-26")
    _write_trio(second_source, [kept_row, added])
    first = publish_serving(first_source, store, published_at=STAMP)
    good = (store / "generations" / first.generation_id / "board.json").read_bytes()

    def _boom(src, dst):
        raise OSError("promotion")

    failed = publish_serving(second_source, store, published_at=STAMP, replace=_boom)
    assert failed.status == REFUSED
    assert failed.reason == "promotion_failed"
    assert current_target(store) == first.generation_id
    assert (store / "generations" / first.generation_id / "board.json").read_bytes() == good


def test_serve_module_does_not_import_trading_or_network():
    source = Path(__file__).resolve().parents[1] / "research" / "v2_research_ledger" / "serve_generation.py"
    text = source.read_text(encoding="utf-8")
    assert "nomination.jsonl" not in text
    tree = ast.parse(text)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    banned = ("app", "urllib", "requests", "socket", "subprocess", "vnstock", "live_candidate", "streamlit")
    assert not any(any(word in name.split(".") for word in banned) for name in imported)

"""Incremental research ingest. Fixtures plus the committed store. No git push."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from pathlib import Path

from research.approximate_returns.view import BUNDLED_VIEW
from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.incremental_ingest import (
    COMMIT_PATHS,
    commit_process_text,
    exclusive_ingest_lock,
    incremental_ingest,
)
from research.v2_research_ledger.ingest_rows import ingest_sources

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "research" / "v2_research_ledger" / "durable"
SIDECAR = ROOT / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
GUARDIAN_OUTCOMES = ROOT / "research" / "guardian_research" / "outcomes.json"
ACTION_CONTRACT = ROOT / "modules" / "live_candidate_v2_action" / "contract.py"
FRT = "sidecar|2026-11-11|FRT|2026-11-11T19:49:09.937669+07:00"


def _freeze(symbol: str, price: float, seen: str = "2026-11-11T19:49:09.937669+07:00") -> dict:
    return {
        "breakout_ref_at_first_seen": price + 100,
        "candidate_first_seen_ts": seen,
        "ema9_at_first_seen": price - 10,
        "price_at_first_seen": price,
        "session": "2026-11-11",
        "symbol": symbol,
    }


def _row(symbol: str, price: float, seen: str = "2026-11-11T19:49:09.937669+07:00") -> dict:
    return {
        "candidate_first_seen_ts": seen,
        "price_at_first_seen": price,
        "session": "2026-11-11",
        "source": "brain_a_scan_setup",
        "status": "NOMINATED",
        "symbol": symbol,
    }


def _write_sidecar(path: Path, freeze: list[dict], rows: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "freeze_ledger": freeze,
                "observed_at": "2026-11-12T11:32:35+07:00",
                "rows": rows,
                "session": "2026-11-12",
            }
        ),
        encoding="utf-8",
    )


def test_new_identity_and_new_link_then_duplicate_is_a_no_op(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(sidecar, [_freeze("HPG", 27000)], [])
    directory = tmp_path / "store"
    first = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    assert first["inserted_identities"] == ["sidecar|2026-11-11|HPG|2026-11-11T19:49:09.937669+07:00"]
    assert first["inserted_links"] == []
    _write_sidecar(sidecar, [_freeze("HPG", 27000)], [_row("HPG", 27000)])
    second = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    assert second["inserted_identities"] == []
    assert second["inserted_links"] == ["nomination|sidecar|2026-11-11|HPG|2026-11-11T19:49:09.937669+07:00"]
    before = (directory / "identities.jsonl").read_bytes()
    links = (directory / "links.jsonl").read_bytes()
    manifest = (directory / "manifest.json").read_bytes()
    third = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    assert third["inserted_identities"] == []
    assert third["inserted_links"] == []
    assert third["run_counts"]["inserted"] == 0
    assert (directory / "identities.jsonl").read_bytes() == before
    assert (directory / "links.jsonl").read_bytes() == links
    assert (directory / "manifest.json").read_bytes() == manifest
    published = json.loads(manifest)
    assert published["identity_count"] == 1
    assert published["link_count"] == 1
    assert not (directory / ".manifest.json.partial").exists()


def test_first_seal_wins_and_a_price_change_is_a_conflict(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(sidecar, [_freeze("FRT", 148000)], [_row("FRT", 148000)])
    directory = tmp_path / "store"
    incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    _write_sidecar(sidecar, [_freeze("FRT", 999)], [_row("FRT", 999)])
    report = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    reloaded = DurableRowStore(directory)
    assert reloaded.identities[FRT]["t0_price"] == 148000
    assert reloaded.identities[FRT]["sealed"]["t0_price"] == 148000
    assert report["inserted_identities"] == []
    assert any(str(item).endswith(FRT) or item == f"nomination|{FRT}" for item in report["conflict_ids"])
    assert reloaded.links[f"nomination|{FRT}"]["t0_price"] == 148000


def test_frt_baseline_gap_is_closed_without_changing_the_seal(tmp_path: Path):
    """The shipped failure is a current row with no nomination link. The seal stays."""
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(sidecar, [_freeze("FRT", 148000)], [])
    directory = tmp_path / "store"
    ingest_sources(DurableRowStore(directory), sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    store = DurableRowStore(directory)
    assert FRT in store.identities
    assert f"nomination|{FRT}" not in store.links
    with pytest_raises_keyerror(store, f"nomination|{FRT}"):
        pass
    _write_sidecar(sidecar, [_freeze("FRT", 148000)], [_row("FRT", 148000)])
    report = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    reloaded = DurableRowStore(directory)
    assert report["inserted_links"] == [f"nomination|{FRT}"]
    assert reloaded.links[f"nomination|{FRT}"]["status"] == "NOMINATED"
    assert reloaded.identities[FRT]["t0_price"] == 148000
    assert reloaded.identities[FRT]["candidate_first_seen_ts"] == "2026-11-11T19:49:09.937669+07:00"
    assert reloaded.identities[FRT]["t0_date"] == "2026-11-11"


def test_a_ticker_without_a_source_row_does_not_get_a_link(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(sidecar, [_freeze("FRT", 148000)], [])
    directory = tmp_path / "store"
    report = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    assert report["inserted_links"] == []
    assert f"nomination|{FRT}" not in DurableRowStore(directory).links


def test_rotating_rows_keep_the_old_link_and_add_the_new_one(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    directory = tmp_path / "store"
    _write_sidecar(sidecar, [_freeze("CSV", 20000), _freeze("DPG", 30000)], [_row("CSV", 20000)])
    incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    _write_sidecar(sidecar, [_freeze("CSV", 20000), _freeze("DPG", 30000)], [_row("DPG", 30000)])
    report = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    store = DurableRowStore(directory)
    assert "nomination|sidecar|2026-11-11|CSV|2026-11-11T19:49:09.937669+07:00" in store.links
    assert report["inserted_links"] == ["nomination|sidecar|2026-11-11|DPG|2026-11-11T19:49:09.937669+07:00"]
    assert report["coverage"]["missing_link"] == []
    assert report["coverage"]["rotating_links_not_in_current_rows"] == [
        "nomination|sidecar|2026-11-11|CSV|2026-11-11T19:49:09.937669+07:00"
    ]
    assert store.identities["sidecar|2026-11-11|CSV|2026-11-11T19:49:09.937669+07:00"]["t0_price"] == 20000


def test_missing_sources_do_not_invent_rows_or_action_states(tmp_path: Path):
    directory = tmp_path / "store"
    report = incremental_ingest(
        directory,
        sidecar_path=tmp_path / "absent.json",
        sweet_csv=None,
        evidence_dir=tmp_path / "missing-evidence",
    )
    assert report["identity_count"] == 0
    assert report["manifest"]["sidecar"]["status"] == "MISSING"
    assert report["manifest"]["sweetspot"]["status"] == "MISSING"
    assert report["manifest"]["action_evidence"]["status"] == "MISSING"
    assert report["inserted_identities"] == []
    text = (directory / "manifest.json").read_text(encoding="utf-8")
    assert "BUY_READY" not in text
    assert "WAIT" not in text


def test_reload_after_a_new_store_object_sees_the_appended_link(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(sidecar, [_freeze("SAB", 55000)], [_row("SAB", 55000)])
    directory = tmp_path / "store"
    incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    reloaded = DurableRowStore(directory)
    ident = "sidecar|2026-11-11|SAB|2026-11-11T19:49:09.937669+07:00"
    assert reloaded.identities[ident]["t0_price"] == 55000
    assert reloaded.links[f"nomination|{ident}"]["source_field"] == "brain_a_scan_setup"
    assert reloaded.read_manifest()["link_count"] == 1


def test_commit_process_does_not_push_and_names_only_the_durable_files():
    text = commit_process_text()
    assert "Do not git push" in text
    for path in COMMIT_PATHS:
        assert path in text
    module = (ROOT / "research/v2_research_ledger/incremental_ingest.py").read_text(encoding="utf-8")
    tree = ast.parse(module)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    banned = ("research.guardian_research", "modules.post_close_finalize", "modules.live_candidate_v2_action", "subprocess")
    assert not any(name == item or name.startswith(item + ".") for name in imported for item in banned)
    assert "Do not git push" in text
    assert "os.system" not in module
    assert "subprocess" not in imported


def test_concurrent_ingest_waits_and_keeps_both_identities(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_sidecar(first, [_freeze("EIB", 18000)], [])
    _write_sidecar(second, [_freeze("EIB", 18000), _freeze("DPG", 30000)], [])
    directory = tmp_path / "store"
    incremental_ingest(directory, sidecar_path=first, sweet_csv=None, evidence_dir=None)
    held = exclusive_ingest_lock(directory)
    held.__enter__()
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; "
            "from research.v2_research_ledger.incremental_ingest import incremental_ingest; "
            "incremental_ingest(Path(sys.argv[1]), sidecar_path=Path(sys.argv[2]), sweet_csv=None, evidence_dir=None)",
            str(directory),
            str(second),
        ],
        cwd=str(ROOT),
    )
    try:
        time.sleep(0.4)
        assert child.poll() is None
    finally:
        held.__exit__(None, None, None)
    assert child.wait(timeout=10) == 0
    store = DurableRowStore(directory)
    assert "sidecar|2026-11-11|EIB|2026-11-11T19:49:09.937669+07:00" in store.identities
    assert "sidecar|2026-11-11|DPG|2026-11-11T19:49:09.937669+07:00" in store.identities
    assert store.read_manifest()["identity_count"] == 2


def test_repository_ingest_fixes_current_row_gaps_without_resealing_frt():
    guardian = GUARDIAN_OUTCOMES.read_bytes()
    approximate = BUNDLED_VIEW.read_bytes()
    sidecar_bytes = SIDECAR.read_bytes()
    contract = ACTION_CONTRACT.read_bytes()
    before = DurableRowStore(STORE)
    frt_seal = dict(before.identities[FRT]["sealed"])
    had_frt_link = f"nomination|{FRT}" in before.links
    report = incremental_ingest(STORE, sidecar_path=SIDECAR, sweet_csv=ROOT / "data/earning_learning/market_aware_sweetspot_observer_ledger.csv", evidence_dir=ROOT / "research/v2_research_ledger/evidence")
    after = DurableRowStore(STORE)
    assert after.identities[FRT]["sealed"] == frt_seal
    assert after.identities[FRT]["t0_price"] == 148000
    document = json.loads(sidecar_bytes)
    frt_rows = [
        row for row in document["rows"]
        if row.get("symbol") == "FRT" and row.get("candidate_first_seen_ts") == "2026-11-11T19:49:09.937669+07:00"
    ]
    if frt_rows:
        assert after.links[f"nomination|{FRT}"]["status"] == frt_rows[0]["status"]
        assert f"nomination|{FRT}" in report["inserted_links"] or had_frt_link
    else:
        assert f"nomination|{FRT}" not in after.links or had_frt_link
    assert report["coverage"]["missing_identity"] == []
    assert report["coverage"]["missing_link"] == []
    assert SIDECAR.read_bytes() == sidecar_bytes
    assert GUARDIAN_OUTCOMES.read_bytes() == guardian
    assert BUNDLED_VIEW.read_bytes() == approximate
    assert ACTION_CONTRACT.read_bytes() == contract
    published = json.loads((STORE / "manifest.json").read_text(encoding="utf-8"))
    assert published["identity_count"] == len(after.identities)
    assert published["link_count"] == len(after.links)
    assert published["t_plus_recomputed"] is False
    assert published["action_evidence"]["status"] == "MISSING"


class pytest_raises_keyerror:
    def __init__(self, store: DurableRowStore, key: str) -> None:
        self.store = store
        self.key = key

    def __enter__(self):
        try:
            self.store.links[self.key]
        except KeyError:
            return self
        raise AssertionError(f"{self.key} was present")

    def __exit__(self, *_args):
        return False

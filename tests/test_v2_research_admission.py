"""Admission rules for Research Ledger ingest. Temporary stores only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.incremental_ingest import incremental_ingest
from research.v2_research_ledger.ingest_rows import ingest_sources

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "research" / "v2_research_ledger" / "durable"
SIDECAR = ROOT / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
SWEET = ROOT / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"
DURABLE_FILES = ("identities.jsonl", "links.jsonl", "conflicts.jsonl", "manifest.json")
SEEN = "2026-11-18T12:37:10Z"
LIVE_SWEETSPOT = {
    "C4G": ("sweet|910e88d6549be194", 4500),
    "FCN": ("sweet|4070560f87a96cb9", 10700),
    "HHV": ("sweet|21b914ec0d13faaf", 9320),
    "SHB": ("sweet|f7cbf8209edddcf1", 10450),
    "TPB": ("sweet|1233ad846dc56887", 12350),
    "VSC": ("sweet|158650a9e0fe1582", 13000),
}


def _freeze(symbol: str, price: float, seen: str = "2026-11-11T19:49:09.937669+07:00") -> dict:
    return {
        "breakout_ref_at_first_seen": price + 100,
        "candidate_first_seen_ts": seen,
        "ema9_at_first_seen": price - 10,
        "price_at_first_seen": price,
        "session": "2026-11-11",
        "symbol": symbol,
    }


def _row(symbol: str, price: float, *, source: str = "brain_a_scan_setup", session: str = "2026-11-11", seen: str = "2026-11-11T19:49:09.937669+07:00") -> dict:
    return {
        "candidate_first_seen_ts": seen,
        "price_at_first_seen": price,
        "session": session,
        "source": source,
        "status": "NOMINATED",
        "symbol": symbol,
    }


def _write_sidecar(path: Path, freeze: list[dict], rows: list[dict]) -> None:
    path.write_text(
        json.dumps({"freeze_ledger": freeze, "observed_at": "2026-11-19T14:20:10+07:00", "rows": rows, "session": "2026-11-19"}),
        encoding="utf-8",
    )


def _sweet(path: Path, rows: list[str]) -> None:
    header = "observer_id,t0_date,symbol,observer_status,market_real_t0,price_t0,created_at,origin_setup\n"
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def _copy_store(directory: Path) -> None:
    directory.mkdir()
    for name in DURABLE_FILES:
        shutil.copyfile(STORE / name, directory / name)


def _bytes(directory: Path) -> dict[str, bytes]:
    captured = {}
    for name in DURABLE_FILES:
        path = directory / name
        captured[name] = path.read_bytes() if path.is_file() else b""
    return captured


def test_live_sweetspot_nominations_create_nothing_and_repeat_is_a_no_op(tmp_path: Path):
    directory = tmp_path / "store"
    _copy_store(directory)
    before = _bytes(directory)
    repository = _bytes(STORE)
    first = incremental_ingest(directory, sidecar_path=SIDECAR, sweet_csv=SWEET, evidence_dir=None)
    assert first["inserted_identities"] == []
    assert first["inserted_links"] == []
    assert first["identity_count"] == 1434
    assert first["link_count"] == 131
    assert first["conflicts"] == 33
    existing = [row for row in first["admission"] if row["classification"] == "EXISTING_OBSERVATION"]
    assert {(row["symbol"], row["identity_id"]) for row in existing} == {
        (symbol, identity_id) for symbol, (identity_id, _price) in LIVE_SWEETSPOT.items()
    }
    assert all(row["reason"] is None for row in existing)
    store = DurableRowStore(directory)
    for symbol, (identity_id, price) in LIVE_SWEETSPOT.items():
        sealed = store.identities[identity_id]["sealed"]
        assert sealed["t0_date"] == "2026-11-18"
        assert sealed["t0_price"] == price
        assert sealed["created_at"] == SEEN
        sidecar_id = f"sidecar|2026-11-19|{symbol}|{SEEN}"
        assert sidecar_id not in store.identities
        assert f"nomination|{sidecar_id}" not in store.links
    assert store.read_manifest()["identity_count"] == len(store.identities)
    assert store.read_manifest()["link_count"] == len(store.links)
    assert store.read_manifest()["conflict_count"] == len(store.conflicts)
    assert (directory / "identities.jsonl").read_bytes() == before["identities.jsonl"]
    assert (directory / "links.jsonl").read_bytes() == before["links.jsonl"]
    assert (directory / "conflicts.jsonl").read_bytes() == before["conflicts.jsonl"]
    after_first = _bytes(directory)
    second = incremental_ingest(directory, sidecar_path=SIDECAR, sweet_csv=SWEET, evidence_dir=None)
    assert second["inserted_identities"] == []
    assert second["inserted_links"] == []
    assert second["conflicts"] == 33
    assert _bytes(directory) == after_first
    assert _bytes(STORE) == repository


def test_new_sweetspot_observation_is_inserted_once(tmp_path: Path):
    sweet = tmp_path / "sweet.csv"
    _sweet(sweet, ["obs-new,2026-11-19,AAA,OBSERVE,1.5,12300,2026-11-19T01:00:00Z,MUA EARLY"])
    directory = tmp_path / "store"
    first = incremental_ingest(directory, sidecar_path=None, sweet_csv=sweet, evidence_dir=None)
    assert first["inserted_identities"] == ["sweet|obs-new"]
    assert first["inserted_links"] == []
    sealed = DurableRowStore(directory).identities["sweet|obs-new"]["sealed"]
    assert sealed["t0_date"] == "2026-11-19"
    assert sealed["t0_price"] == 12300
    before = _bytes(directory)
    second = incremental_ingest(directory, sidecar_path=None, sweet_csv=sweet, evidence_dir=None)
    assert second["inserted_identities"] == []
    assert second["run_counts"]["inserted"] == 0
    assert _bytes(directory) == before


def test_changed_sweetspot_seal_keeps_the_original_and_records_one_conflict(tmp_path: Path):
    sweet = tmp_path / "sweet.csv"
    _sweet(sweet, ["obs-1,2026-11-18,C4G,OBSERVE,1.0,4500,2026-11-18T12:37:10Z,MUA EARLY"])
    directory = tmp_path / "store"
    ingest_sources(DurableRowStore(directory), sidecar_path=None, sweet_csv=sweet, evidence_dir=None)
    _sweet(sweet, ["obs-1,2026-11-19,C4G,OBSERVE,9.0,9999,2026-11-19T08:00:00Z,MUA LATE"])
    ingest_sources(DurableRowStore(directory), sidecar_path=None, sweet_csv=sweet, evidence_dir=None)
    store = DurableRowStore(directory)
    sealed = store.identities["sweet|obs-1"]["sealed"]
    assert sealed["t0_date"] == "2026-11-18"
    assert sealed["t0_price"] == 4500
    assert sealed["created_at"] == "2026-11-18T12:37:10Z"
    assert len(store.conflicts) == 1
    assert store.conflicts[0]["reason"] == "T0_IMMUTABLE"
    assert store.conflicts[0]["subject_id"] == "sweet|obs-1"
    before = _bytes(directory)
    ingest_sources(DurableRowStore(directory), sidecar_path=None, sweet_csv=sweet, evidence_dir=None)
    assert _bytes(directory) == before


def test_freeze_identity_and_nomination_link_are_written_in_one_pass(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(sidecar, [_freeze("HPG", 27000)], [_row("HPG", 27000)])
    directory = tmp_path / "store"
    first = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    identity_id = "sidecar|2026-11-11|HPG|2026-11-11T19:49:09.937669+07:00"
    assert first["inserted_identities"] == [identity_id]
    assert first["inserted_links"] == [f"nomination|{identity_id}"]
    assert first["admission"] == []
    store = DurableRowStore(directory)
    assert store.identities[identity_id]["sealed"]["t0_date"] == "2026-11-11"
    assert store.identities[identity_id]["sealed"]["t0_price"] == 27000
    assert store.links[f"nomination|{identity_id}"]["status"] == "NOMINATED"
    assert store.read_manifest()["identity_count"] == 1
    assert store.read_manifest()["link_count"] == 1
    before = _bytes(directory)
    second = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    assert second["inserted_identities"] == []
    assert second["inserted_links"] == []
    assert _bytes(directory) == before


def test_ambiguous_and_unmatched_camera_rows_are_deferred(tmp_path: Path):
    sweet = tmp_path / "sweet.csv"
    _sweet(
        sweet,
        [
            "obs-a,2026-11-18,C4G,OBSERVE,1.0,4500,2026-11-18T12:37:10Z,MUA",
            "obs-b,2026-11-18,C4G,OBSERVE,1.0,4500,2026-11-18T12:37:10Z,MUA",
        ],
    )
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(
        sidecar,
        [],
        [
            _row("C4G", 4500, source="market_aware_sweetspot", session="2026-11-19", seen=SEEN),
            _row("ZZZ", 1000, source="market_aware_sweetspot", session="2026-11-19", seen="2026-11-19T01:00:00Z"),
            _row("HPG", 27000, session="2026-11-19"),
        ],
    )
    directory = tmp_path / "store"
    report = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    assert report["inserted_identities"] == ["sweet|obs-a", "sweet|obs-b"]
    assert report["inserted_links"] == []
    reasons = {row["symbol"]: row["reason"] for row in report["admission"]}
    assert reasons["C4G"] == "AMBIGUOUS_SWEETSPOT_MATCH"
    assert reasons["ZZZ"] == "UNMATCHED_SWEETSPOT_NOMINATION"
    assert reasons["HPG"] == "UNMATCHED_CAMERA_NOMINATION"
    store = DurableRowStore(directory)
    assert "sidecar|2026-11-19|C4G|2026-11-18T12:37:10Z" not in store.identities
    assert "sidecar|2026-11-19|ZZZ|2026-11-19T01:00:00Z" not in store.identities
    assert "sidecar|2026-11-19|HPG|2026-11-11T19:49:09.937669+07:00" not in store.identities
    assert store.links == {}
    assert store.conflicts == []
    assert store.read_manifest()["identity_count"] == 2


def test_sweetspot_nomination_price_conflict_does_not_replace_the_seal(tmp_path: Path):
    sweet = tmp_path / "sweet.csv"
    _sweet(sweet, ["obs-1,2026-11-18,C4G,OBSERVE,1.0,4500,2026-11-18T12:37:10Z,MUA"])
    sidecar = tmp_path / "camera_sidecar.json"
    _write_sidecar(sidecar, [], [_row("C4G", 9999, source="market_aware_sweetspot", session="2026-11-19", seen=SEEN)])
    directory = tmp_path / "store"
    first = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    assert first["inserted_identities"] == ["sweet|obs-1"]
    assert first["inserted_links"] == []
    assert first["admission"][0]["classification"] == "CONFLICT"
    assert first["admission"][0]["identity_id"] == "sweet|obs-1"
    store = DurableRowStore(directory)
    assert store.identities["sweet|obs-1"]["sealed"]["t0_price"] == 4500
    assert store.identities["sweet|obs-1"]["sealed"]["t0_date"] == "2026-11-18"
    assert len(store.conflicts) == 1
    assert "sidecar|2026-11-19|C4G|2026-11-18T12:37:10Z" not in store.identities
    before = _bytes(directory)
    second = incremental_ingest(directory, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    assert second["inserted_identities"] == []
    assert _bytes(directory) == before


def test_missing_sources_do_not_fabricate_rows(tmp_path: Path):
    directory = tmp_path / "store"
    report = incremental_ingest(
        directory,
        sidecar_path=tmp_path / "absent.json",
        sweet_csv=tmp_path / "absent.csv",
        evidence_dir=None,
    )
    assert report["inserted_identities"] == []
    assert report["inserted_links"] == []
    assert report["identity_count"] == 0
    assert report["manifest"]["sidecar"]["status"] == "MISSING"
    assert report["manifest"]["sweetspot"]["status"] == "MISSING"
    assert DurableRowStore(directory).identities == {}
    assert report["manifest"]["identity_count"] == 0
    assert report["manifest"]["link_count"] == 0

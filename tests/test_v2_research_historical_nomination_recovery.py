"""Stage 2 historical nomination replay. Temporary store. No git push."""

from __future__ import annotations

import hashlib
from pathlib import Path

from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.historical_nomination_recovery import (
    RECOVERED_IDENTITY_IDS,
    iter_published_sidecar_snapshots,
    recover_historical_nominations,
)
from research.v2_research_ledger.incremental_ingest import incremental_ingest

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "research" / "v2_research_ledger" / "durable"
SIDECAR = ROOT / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
SWEET = ROOT / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"
EVIDENCE = ROOT / "research" / "v2_research_ledger" / "evidence"

BASELINE_LINKS = 39
BASELINE_CONFLICTS = 4
IDENTITIES_SHA = "a2e868e74e62fef8d74c0215f817194e9489cba7af523e788c42251f9c28b848"
BASELINE_LINKS_SHA = "8879316c0edd61ca8a7b5eacdd747368847b15abcaa23cea20490e37b6a44769"
BASELINE_CONFLICTS_SHA = "942d275d7540a6cf385816bbd32685c3a1c41cc45e6eb61cc3cf150a221f1116"
LINKS_SHA = "377ff151d96c290c062efdfe32118b02d49efaaa30c98d5871fe6ac5b1fd2ec4"
CONFLICTS_SHA = "ed13a4a6b9b66017993f85471137b04b9fa536dd950b6dfd93c4e1f07d4db82d"
MANIFEST_SHA = "48e44d058ec1bc4c11321afb21265f2e9ae95c932c2cac156586ccdcdefbe25b"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_historical_replay_appends_92_links_and_replays_clean(tmp_path: Path):
    assert len(RECOVERED_IDENTITY_IDS) == 92
    identities = (STORE / "identities.jsonl").read_bytes()
    committed_links = (STORE / "links.jsonl").read_bytes()
    committed_conflicts = (STORE / "conflicts.jsonl").read_bytes()
    committed_manifest = (STORE / "manifest.json").read_bytes()
    assert _sha(identities) == IDENTITIES_SHA
    assert _sha(committed_links) == LINKS_SHA
    assert _sha(committed_conflicts) == CONFLICTS_SHA
    assert _sha(committed_manifest) == MANIFEST_SHA

    link_lines = committed_links.splitlines(keepends=True)
    conflict_lines = committed_conflicts.splitlines(keepends=True)
    assert len(link_lines) == 131
    assert len(conflict_lines) == 33
    baseline_links = b"".join(link_lines[:BASELINE_LINKS])
    baseline_conflicts = b"".join(conflict_lines[:BASELINE_CONFLICTS])
    assert _sha(baseline_links) == BASELINE_LINKS_SHA
    assert _sha(baseline_conflicts) == BASELINE_CONFLICTS_SHA

    directory = tmp_path / "store"
    directory.mkdir()
    (directory / "identities.jsonl").write_bytes(identities)
    (directory / "links.jsonl").write_bytes(baseline_links)
    (directory / "conflicts.jsonl").write_bytes(baseline_conflicts)
    starting = DurableRowStore(directory)
    seals = {ident: dict(row.get("sealed") or {}) for ident, row in starting.identities.items()}
    assert len(starting.identities) == 1434
    assert len(starting.links) == 39
    assert len(starting.conflicts) == 4

    first = recover_historical_nominations(starting, iter_published_sidecar_snapshots(ROOT))
    assert first["inserted_links"] == sorted(f"nomination|{ident}" for ident in RECOVERED_IDENTITY_IDS)
    assert first["appended_conflicts"] == 29
    assert len(starting.links) == 131
    assert len(starting.conflicts) == 33
    assert (directory / "identities.jsonl").read_bytes() == identities
    assert (directory / "links.jsonl").read_bytes().splitlines(keepends=True)[:BASELINE_LINKS] == link_lines[:BASELINE_LINKS]
    assert (directory / "conflicts.jsonl").read_bytes().splitlines(keepends=True)[:BASELINE_CONFLICTS] == conflict_lines[:BASELINE_CONFLICTS]
    for ident, sealed in seals.items():
        assert starting.identities[ident].get("sealed") == sealed

    links_once = (directory / "links.jsonl").read_bytes()
    conflicts_once = (directory / "conflicts.jsonl").read_bytes()
    assert _sha(links_once) == LINKS_SHA
    assert _sha(conflicts_once) == CONFLICTS_SHA

    second = recover_historical_nominations(DurableRowStore(directory), iter_published_sidecar_snapshots(ROOT))
    assert second["inserted_links"] == []
    assert second["appended_conflicts"] == 0
    assert (directory / "links.jsonl").read_bytes() == links_once
    assert (directory / "conflicts.jsonl").read_bytes() == conflicts_once
    assert (directory / "identities.jsonl").read_bytes() == identities

    published = incremental_ingest(directory, sidecar_path=SIDECAR, sweet_csv=SWEET, evidence_dir=EVIDENCE)
    manifest = published["manifest"]
    assert published["inserted_identities"] == []
    assert published["inserted_links"] == []
    assert manifest["identity_count"] == 1434
    assert manifest["link_count"] == 131
    assert manifest["conflict_count"] == 33
    assert manifest["sidecar"]["linked_current_rows"] == 0
    assert manifest["t_plus_recomputed"] is False
    assert (directory / "links.jsonl").read_bytes() == links_once
    assert (directory / "conflicts.jsonl").read_bytes() == conflicts_once
    assert (directory / "identities.jsonl").read_bytes() == identities
    assert (STORE / "manifest.json").read_bytes() == committed_manifest
    first_manifest = (directory / "manifest.json").read_bytes()

    again = incremental_ingest(directory, sidecar_path=SIDECAR, sweet_csv=SWEET, evidence_dir=EVIDENCE)
    assert again["inserted_identities"] == []
    assert again["inserted_links"] == []
    assert again["manifest"]["identity_count"] == 1434
    assert (directory / "links.jsonl").read_bytes() == committed_links
    assert (directory / "conflicts.jsonl").read_bytes() == committed_conflicts
    assert (directory / "identities.jsonl").read_bytes() == identities
    assert (directory / "manifest.json").read_bytes() == first_manifest
    assert (STORE / "manifest.json").read_bytes() == committed_manifest
    reloaded = DurableRowStore(directory)
    for ident, sealed in seals.items():
        assert reloaded.identities[ident].get("sealed") == sealed

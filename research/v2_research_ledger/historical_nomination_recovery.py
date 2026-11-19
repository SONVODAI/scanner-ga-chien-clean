"""Recover approved historical Brain A nomination links from published sidecars.

The current sidecar rows array rotates. This replay reads the published
Git history and appends links only for the 92 identities approved for
Stage 2. A later setup on an existing link is recorded as
``LINK_SEAL_IMMUTABLE`` and does not replace the stored setup.

The replay does not create identities, does not change nomination rules,
and does not include the older September–October identities.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from research.v2_research_ledger.contract import SOURCE_BRAIN_A
from research.v2_research_ledger.durable_store import DurableRowStore, canonical_number
from research.v2_research_ledger.ingest_rows import _nomination_link

SIDECAR_GIT_PATH = "research/live_candidate_v2_camera_sidecar/camera_sidecar.json"
RECOVERY_NOT_BEFORE = "2026-11-11"
NOMINATED = "NOMINATED"

# Closed set. Eighty-four identities sealed in Stage 1, plus eight 11 November
# identities whose exact nomination had rotated off before links were stored.
RECOVERED_IDENTITY_IDS = frozenset(
    {
        "sidecar|2026-11-11|BSI|2026-11-12T10:19:27.594905+07:00",
        "sidecar|2026-11-11|FRT|2026-11-11T19:49:09.937669+07:00",
        "sidecar|2026-11-11|GEG|2026-11-12T10:19:27.594905+07:00",
        "sidecar|2026-11-11|HHV|2026-11-12T10:19:27.594905+07:00",
        "sidecar|2026-11-11|HVN|2026-11-12T10:19:27.594905+07:00",
        "sidecar|2026-11-11|KBC|2026-11-11T19:49:09.937669+07:00",
        "sidecar|2026-11-11|NT2|2026-11-12T10:19:27.594905+07:00",
        "sidecar|2026-11-11|VPL|2026-11-11T19:49:09.937669+07:00",
        "sidecar|2026-11-12|AGR|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|ANV|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|BFC|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|BSI|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|BVS|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|CEO|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|CII|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|CTG|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|DBC|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|DIG|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|DPR|2026-11-12T20:57:16.099898+07:00",
        "sidecar|2026-11-12|DXG|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|DXS|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|EVF|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|FCN|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|FRT|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|FTS|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|GIL|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|GMD|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|HDB|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|HDG|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|HHS|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|HHV|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|HPG|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|HSG|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|HVN|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|IJC|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|KBC|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|LPB|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|MSB|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|NAB|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|NHA|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|NKG|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|NVL|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|OCB|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|PC1|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|PDR|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|POW|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|REE|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|SAB|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|SHB|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|SHS|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|SIP|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|SSI|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|STB|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|SZC|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|TCH|2026-11-13T10:29:48.952092+07:00",
        "sidecar|2026-11-12|TCX|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|TPB|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|VCG|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|VCI|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|VCK|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|VDS|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|VHC|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|VHM|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|VIC|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|VIX|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|VND|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-12|VPL|2026-11-13T09:07:56.624658+07:00",
        "sidecar|2026-11-12|VRE|2026-11-12T19:56:34.603892+07:00",
        "sidecar|2026-11-13|BAF|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|BSI|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|CTG|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|DBC|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|FCN|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|FOX|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|HDB|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|NAB|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|NT2|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|OCB|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|PLC|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|POW|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|SBT|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|SHB|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|SIP|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|TPB|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VDS|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VGS|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VHC|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VIC|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VND|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VPL|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VPX|2026-11-13T17:03:36.790322+07:00",
        "sidecar|2026-11-13|VRE|2026-11-13T17:03:36.790322+07:00",
    }
)


def iter_published_sidecar_snapshots(repo: Path) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield ``(commit, committer_time, document)`` from 11 November 2026 onward."""
    log = subprocess.check_output(
        ["git", "log", "--reverse", "--format=%H%x09%cI", "--", SIDECAR_GIT_PATH],
        cwd=repo,
        text=True,
    )
    for line in log.splitlines():
        if "\t" not in line:
            continue
        commit, committed_at = line.split("\t", 1)
        if committed_at[:10] < RECOVERY_NOT_BEFORE:
            continue
        payload = subprocess.check_output(["git", "show", f"{commit}:{SIDECAR_GIT_PATH}"], cwd=repo)
        document = json.loads(payload)
        if isinstance(document, dict):
            yield commit, committed_at, document


def recover_historical_nominations(
    store: DurableRowStore,
    snapshots: Iterable[tuple[str, str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Append approved links. Keep every existing link and identity seal."""
    before_links = set(store.links)
    before_conflicts = len(store.conflicts)
    for commit, committed_at, document in snapshots:
        rows = document.get("rows") if isinstance(document.get("rows"), list) else []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            identity_id = _sidecar_identity_id(raw)
            if identity_id not in store.identities:
                continue
            if str(raw.get("source") or "") != SOURCE_BRAIN_A or str(raw.get("status") or "") != NOMINATED:
                continue
            if not _matches_sealed_identity(raw, store.identities[identity_id]):
                continue
            link_id = f"nomination|{identity_id}"
            if identity_id not in RECOVERED_IDENTITY_IDS and link_id not in store.links:
                continue
            link = _nomination_link(identity_id, raw, document)
            if link_id not in store.links:
                link["source_commit"] = commit
                link["source_commit_time"] = committed_at
            store.put_link(link)
    inserted = sorted(set(store.links) - before_links)
    return {
        "appended_conflicts": len(store.conflicts) - before_conflicts,
        "inserted_links": inserted,
    }


def _sidecar_identity_id(raw: Mapping[str, Any]) -> str:
    session = str(raw.get("session") or "")[:10]
    symbol = str(raw.get("symbol") or "").strip().upper()
    seen = raw.get("candidate_first_seen_ts") or ""
    return f"sidecar|{session}|{symbol}|{seen}"


def _matches_sealed_identity(raw: Mapping[str, Any], ident: Mapping[str, Any]) -> bool:
    sealed = ident.get("sealed")
    if not isinstance(sealed, dict):
        return False
    offered = {
        "breakout_ref_at_first_seen": canonical_number(raw.get("breakout_ref_at_first_seen")),
        "candidate_first_seen_ts": str(raw.get("candidate_first_seen_ts") or ""),
        "ema9_at_first_seen": canonical_number(raw.get("ema9_at_first_seen")),
        "source_attribution": str(raw.get("source") or "").strip(),
        "symbol": str(raw.get("symbol") or "").strip().upper(),
        "t0_date": str(raw.get("session") or "")[:10],
        "t0_price": canonical_number(raw.get("price_at_first_seen")),
    }
    return all(sealed.get(field) == offered[field] for field in sealed)

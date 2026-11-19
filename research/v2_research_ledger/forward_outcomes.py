"""Derived T+ outcomes for the Research Ledger.

The builder reads a sealed ledger and a validated approximate reference store.
It writes a new generation file. An existing generation with different bytes
is refused, so a later ``as_of`` does not replace an earlier one.

The sealed JSONL files, Guardian Research, and the reference store are not
written. The panel falls back to ``UNAVAILABLE_NOT_RECOMPUTED`` when no
generation matches the ledger that is open.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from research.approximate_returns.contract import (
    HORIZONS,
    PRICE_BASIS,
    SOURCE,
    STATUS_AVAILABLE,
    STATUS_DISCONTINUITY,
    STATUS_NOT_YET,
    STATUS_T0_MISSING,
    STATUS_TARGET_MISSING,
    STATUS_TRUNCATED,
)
from research.approximate_returns.returns import evaluate_rows
from research.guardian_research.reference_export import read_reference_store

DOCUMENT_SCHEMA = "v2_research_forward_outcomes.v1"
INDEX_SCHEMA = "v2_research_forward_index.v1"
CALCULATION_VERSION = "ledger_forward.v1"
FALLBACK_STATUS = "UNAVAILABLE_NOT_RECOMPUTED"

BRAIN_LINKED = "brain_linked"
BRAIN_UNLINKED = "brain_unlinked"
SWEETSPOT = "sweetspot"
SWEETSPOT_BLANK = "sweetspot_blank"
POPULATIONS = (BRAIN_LINKED, BRAIN_UNLINKED, SWEETSPOT, SWEETSPOT_BLANK)

LEDGER_FILES = ("identities.jsonl", "links.jsonl", "conflicts.jsonl", "manifest.json")
STAGE2_LEDGER_HASHES = {
    "identities.jsonl": "a2e868e74e62fef8d74c0215f817194e9489cba7af523e788c42251f9c28b848",
    "links.jsonl": "377ff151d96c290c062efdfe32118b02d49efaaa30c98d5871fe6ac5b1fd2ec4",
    "conflicts.jsonl": "ed13a4a6b9b66017993f85471137b04b9fa536dd950b6dfd93c4e1f07d4db82d",
    "manifest.json": "48e44d058ec1bc4c11321afb21265f2e9ae95c932c2cac156586ccdcdefbe25b",
}
STAGE2_REFERENCE_SHA256 = "a90e163943d8b2b953f5eab718c05334da49d5caf60be6d9d6ef1d855bd54bdd"
HORIZON_LABELS = tuple(f"T+{step}" for step in HORIZONS)
PRIMARY_STATUS = STATUS_AVAILABLE
MISSING_STATUSES = frozenset({STATUS_NOT_YET, STATUS_T0_MISSING, STATUS_TARGET_MISSING})
REVIEW_STATUSES = frozenset({STATUS_TRUNCATED, STATUS_DISCONTINUITY})
KNOWN_STATUSES = frozenset({PRIMARY_STATUS, *MISSING_STATUSES, *REVIEW_STATUSES})


class ForwardBuildError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def population_for(record: Mapping[str, Any], links: Mapping[str, Mapping[str, Any]]) -> str:
    """Label one sealed identity. A missing nomination link is not a nomination."""
    role = str(record.get("record_role") or "")
    symbol = str(record.get("symbol") or "").strip()
    if role == "sweetspot_identity":
        return SWEETSPOT if symbol else SWEETSPOT_BLANK
    if role == "sidecar_identity":
        link = links.get(f"nomination|{record.get('identity_id')}")
        if link and str(link.get("status") or "") == "NOMINATED":
            return BRAIN_LINKED
        return BRAIN_UNLINKED
    raise ForwardBuildError("POPULATION_UNKNOWN")


def file_hashes(directory: Path) -> dict[str, str]:
    root = Path(directory)
    hashes: dict[str, str] = {}
    for name in LEDGER_FILES:
        path = root / name
        if not path.is_file():
            raise ForwardBuildError(f"LEDGER_FILE_ABSENT:{name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def build_forward_document(
    ledger_dir: Path,
    reference_path: Path,
    *,
    expected_ledger_hashes: Mapping[str, str],
    expected_reference_sha256: str,
) -> dict[str, Any]:
    """Return a derived document. The ledger and the reference file are only read."""
    ledger_root = Path(ledger_dir)
    hashes = file_hashes(ledger_root)
    if dict(expected_ledger_hashes) != hashes:
        raise ForwardBuildError("LEDGER_HASH_MISMATCH")
    store = read_reference_store(Path(reference_path))
    if store is None or store.get("content_sha256") != expected_reference_sha256:
        raise ForwardBuildError("REFERENCE_NOT_VALIDATED")
    sessions = _calendar(store)
    identities, links = _load_ledger(ledger_root)
    _require_unique_coverage(identities)
    prepared = [
        {
            "row_id": row.get("identity_id"),
            "symbol": row.get("symbol") or "",
            "t0_date": str(row.get("t0_date") or "")[:10],
            "source": "",
            "t0_price": None,
        }
        for row in identities
    ]
    evaluated = evaluate_rows(prepared, store)
    if any(row.get("t0_price_used_as_denominator") for row in evaluated):
        raise ForwardBuildError("NOMINATION_PRICE_USED")
    by_id = {row["row_id"]: row for row in evaluated}
    if len(by_id) != len(identities):
        raise ForwardBuildError("IDENTITY_COVERAGE_INCOMPLETE")
    rows = []
    for record in identities:
        identity_id = str(record.get("identity_id") or "")
        item = by_id.get(identity_id)
        if item is None:
            raise ForwardBuildError("IDENTITY_COVERAGE_INCOMPLETE")
        population = population_for(record, links)
        t0_date = str(record.get("t0_date") or "")[:10]
        if item.get("t0_date") != t0_date:
            raise ForwardBuildError("T0_MISALIGNED")
        horizons, reference_present = _checked_horizons(item, sessions)
        rows.append(
            {
                "horizons": horizons,
                "identity_id": identity_id,
                "population": population,
                "reference_t0_present": reference_present,
                "symbol": str(record.get("symbol") or ""),
                "t0_date": t0_date,
                "t0_price_used_as_denominator": False,
            }
        )
    rows.sort(key=lambda row: row["identity_id"])
    document = {
        "as_of": sessions[-1],
        "calculation_version": CALCULATION_VERSION,
        "coverage": _coverage(rows),
        "identity_count": len(rows),
        "ledger_hashes": hashes,
        "official_pnl": False,
        "price_basis": PRICE_BASIS,
        "reference_sha256": store.get("content_sha256"),
        "reference_source": SOURCE,
        "rows": rows,
        "schema": DOCUMENT_SCHEMA,
        "trading_sessions": sessions,
    }
    return document


def publish_forward_document(document: Mapping[str, Any], output_root: Path, ledger_dir: Path) -> dict[str, Any]:
    """Write one generation. A different body for the same generation is refused."""
    root = Path(output_root)
    _refuse_protected_output(root, Path(ledger_dir))
    generation_id = _generation_id(document)
    payload = _canonical(document)
    directory = root / "generations"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{generation_id}.json"
    if target.is_file():
        if target.read_bytes() != payload:
            raise ForwardBuildError("REFUSE_OVERWRITE")
        file_status = "unchanged"
    else:
        _atomic_write(target, payload)
        file_status = "written"
    entry = {
        "as_of": document["as_of"],
        "calculation_version": document["calculation_version"],
        "generation_id": generation_id,
        "identity_count": document["identity_count"],
        "ledger_hashes": document["ledger_hashes"],
        "path": f"generations/{generation_id}.json",
        "reference_sha256": document["reference_sha256"],
    }
    index_status = _record_generation(root / "index.json", entry)
    return {"file_status": file_status, "generation_id": generation_id, "index_status": index_status, "path": str(target)}


def attachable_outcomes(ledger_dir: Path, outcomes_root: Path | None = None) -> dict[str, Any] | None:
    """Return the newest matching generation, or None when the panel must stay unavailable."""
    root = Path(outcomes_root) if outcomes_root is not None else Path(ledger_dir).parent / "outcomes"
    try:
        hashes = file_hashes(ledger_dir)
        identities, links = _load_ledger(Path(ledger_dir))
    except (ForwardBuildError, OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    index = _read_index(root / "index.json")
    if index is None:
        return None
    chosen: list[dict[str, Any]] = []
    for entry in index.get("generations") or []:
        if not isinstance(entry, dict) or entry.get("ledger_hashes") != hashes:
            continue
        document = _read_generation(root / str(entry.get("path") or ""))
        if document is None or not _document_matches(document, identities, links, hashes):
            continue
        chosen.append(document)
    if not chosen:
        return None
    latest = max(str(item.get("as_of") or "") for item in chosen)
    current = [item for item in chosen if str(item.get("as_of") or "") == latest]
    if len(current) != 1:
        return None
    return current[0]


def display_horizon(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a cell for the table. Only a primary return keeps its percentage."""
    status = str(cell.get("status") or FALLBACK_STATUS)
    if status not in KNOWN_STATUSES:
        status = FALLBACK_STATUS
    value = cell.get("return_pct")
    if status == PRIMARY_STATUS and isinstance(value, (int, float)) and not isinstance(value, bool):
        return {
            "included_in_primary": True,
            "return_pct": value,
            "status": status,
            "target_session": cell.get("target_session"),
        }
    return {
        "included_in_primary": False,
        "return_pct": None,
        "status": status if status in KNOWN_STATUSES else FALLBACK_STATUS,
        "target_session": cell.get("target_session"),
    }


def _calendar(store: Mapping[str, Any]) -> list[str]:
    sessions = [str(item) for item in store.get("trading_sessions") or []]
    as_of = str(store.get("as_of") or "")
    if not sessions or sessions != sorted(set(sessions)) or sessions[-1] != as_of:
        raise ForwardBuildError("CALENDAR_INVALID")
    for row in store.get("rows") or []:
        if str(row.get("session") or "") > as_of:
            raise ForwardBuildError("LOOKAHEAD_ROW")
    return sessions


def _load_ledger(directory: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    identities = _jsonl(directory / "identities.jsonl")
    links = {str(row.get("link_id") or ""): row for row in _jsonl(directory / "links.jsonl") if row.get("link_id")}
    return identities, links


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if not isinstance(loaded, dict):
            raise ForwardBuildError("LEDGER_ROW_INVALID")
        rows.append(loaded)
    return rows


def _require_unique_coverage(identities: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for record in identities:
        identity_id = str(record.get("identity_id") or "")
        if not identity_id or identity_id in seen:
            raise ForwardBuildError("IDENTITY_COVERAGE_INCOMPLETE")
        seen.add(identity_id)


def _checked_horizons(item: Mapping[str, Any], sessions: list[str]) -> tuple[dict[str, dict[str, Any]], bool]:
    position = {day: index for index, day in enumerate(sessions)}.get(str(item.get("t0_date") or ""))
    reference_present = item.get("reference_t0_price") is not None and bool(item.get("reference_t0_clock"))
    checked: dict[str, dict[str, Any]] = {}
    raw = item.get("horizons") or {}
    for step, label in zip(HORIZONS, HORIZON_LABELS):
        cell = raw.get(label)
        if not isinstance(cell, dict):
            raise ForwardBuildError("HORIZON_MISSING")
        status = str(cell.get("status") or "")
        if status not in KNOWN_STATUSES:
            raise ForwardBuildError("HORIZON_STATUS_UNKNOWN")
        expected_target = None
        if reference_present and position is not None and position + step < len(sessions):
            expected_target = sessions[position + step]
        if cell.get("target_session") != expected_target:
            raise ForwardBuildError("HORIZON_MISALIGNED")
        if not reference_present or position is None:
            if status != STATUS_T0_MISSING or cell.get("return_pct") is not None:
                raise ForwardBuildError("HORIZON_MISALIGNED")
        elif position + step >= len(sessions):
            if status != STATUS_NOT_YET or cell.get("return_pct") is not None:
                raise ForwardBuildError("HORIZON_MISALIGNED")
        elif status == STATUS_TARGET_MISSING and cell.get("return_pct") is not None:
            raise ForwardBuildError("MISSING_RETURN_NOT_NULL")
        elif status == PRIMARY_STATUS and not _is_number(cell.get("return_pct")):
            raise ForwardBuildError("PRIMARY_RETURN_ABSENT")
        elif status in REVIEW_STATUSES and not _is_number(cell.get("return_pct")):
            raise ForwardBuildError("REVIEW_RETURN_ABSENT")
        if bool(cell.get("included_in_primary")) != (status == PRIMARY_STATUS):
            raise ForwardBuildError("PRIMARY_FLAG_MISMATCH")
        checked[label] = {
            "included_in_primary": status == PRIMARY_STATUS,
            "return_pct": cell.get("return_pct") if status in {PRIMARY_STATUS, *REVIEW_STATUSES} else None,
            "status": status,
            "target_session": expected_target,
        }
    return checked, reference_present


def _coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Status counts only. Populations are not averaged together."""
    coverage: dict[str, Any] = {}
    for population in POPULATIONS:
        chosen = [row for row in rows if row["population"] == population]
        horizons: dict[str, dict[str, int]] = {}
        for label in HORIZON_LABELS:
            counts: dict[str, int] = {}
            for row in chosen:
                status = row["horizons"][label]["status"]
                counts[status] = counts.get(status, 0) + 1
            counts["usable_primary"] = counts.get(PRIMARY_STATUS, 0)
            horizons[label] = counts
        coverage[population] = {"horizons": horizons, "rows": len(chosen)}
    return coverage


def _document_matches(
    document: Mapping[str, Any],
    identities: list[dict[str, Any]],
    links: Mapping[str, Mapping[str, Any]],
    hashes: Mapping[str, str],
) -> bool:
    if document.get("schema") != DOCUMENT_SCHEMA or document.get("calculation_version") != CALCULATION_VERSION:
        return False
    if document.get("official_pnl") is not False or document.get("price_basis") != PRICE_BASIS:
        return False
    if document.get("ledger_hashes") != dict(hashes):
        return False
    sessions = document.get("trading_sessions")
    if not isinstance(sessions, list) or [str(item) for item in sessions] != sorted(set(map(str, sessions))):
        return False
    calendar = [str(item) for item in sessions]
    if not calendar or document.get("as_of") != calendar[-1]:
        return False
    rows = document.get("rows")
    if not isinstance(rows, list):
        return False
    expected_ids = {str(record.get("identity_id") or "") for record in identities}
    found_ids = [str(row.get("identity_id") or "") for row in rows if isinstance(row, dict)]
    if len(found_ids) != len(expected_ids) or set(found_ids) != expected_ids or "" in found_ids:
        return False
    by_record = {str(record.get("identity_id") or ""): record for record in identities}
    for row in rows:
        if not isinstance(row, dict) or row.get("t0_price_used_as_denominator") is not False:
            return False
        record = by_record.get(str(row.get("identity_id") or ""))
        if record is None or str(row.get("t0_date") or "") != str(record.get("t0_date") or "")[:10]:
            return False
        try:
            population = population_for(record, links)
        except ForwardBuildError:
            return False
        if row.get("population") != population:
            return False
        horizons = row.get("horizons")
        if not isinstance(horizons, dict):
            return False
        if row.get("reference_t0_present") not in {True, False}:
            return False
        present = row.get("reference_t0_present") is True
        position = {day: index for index, day in enumerate(calendar)}.get(str(row.get("t0_date") or ""))
        for step, label in zip(HORIZONS, HORIZON_LABELS):
            cell = horizons.get(label)
            if not isinstance(cell, dict) or cell.get("status") not in KNOWN_STATUSES:
                return False
            status = str(cell.get("status"))
            value = cell.get("return_pct")
            if status == PRIMARY_STATUS and not _is_number(value):
                return False
            if status in MISSING_STATUSES and value is not None:
                return False
            if status in REVIEW_STATUSES and not _is_number(value):
                return False
            if bool(cell.get("included_in_primary")) != (status == PRIMARY_STATUS):
                return False
            if not present or position is None:
                if status != STATUS_T0_MISSING or cell.get("target_session") is not None:
                    return False
            elif position + step >= len(calendar):
                if status != STATUS_NOT_YET or cell.get("target_session") is not None:
                    return False
            elif cell.get("target_session") != calendar[position + step] or status in {STATUS_T0_MISSING, STATUS_NOT_YET}:
                return False
    return True


def _generation_id(document: Mapping[str, Any]) -> str:
    ledger = hashlib.sha256(_canonical({"ledger_hashes": document["ledger_hashes"]})).hexdigest()[:12]
    reference = str(document.get("reference_sha256") or "")[:12]
    return f"{document['as_of']}_{ledger}_{reference}"


def _record_generation(path: Path, entry: Mapping[str, Any]) -> str:
    current = _read_index(path)
    generations = list(current.get("generations") or []) if current else []
    for existing in generations:
        if existing.get("generation_id") != entry["generation_id"]:
            continue
        if existing != dict(entry):
            raise ForwardBuildError("REFUSE_OVERWRITE")
        return "unchanged"
    generations.append(dict(entry))
    generations.sort(key=lambda item: (str(item.get("as_of") or ""), str(item.get("generation_id") or "")))
    payload = _canonical({"generations": generations, "schema": INDEX_SCHEMA})
    if path.is_file() and path.read_bytes() == payload:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, payload)
    return "written"


def _read_index(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict) or loaded.get("schema") != INDEX_SCHEMA:
        return None
    if not isinstance(loaded.get("generations"), list):
        return None
    return loaded


def _read_generation(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def _refuse_protected_output(output_root: Path, ledger_dir: Path) -> None:
    output = output_root.resolve()
    ledger = ledger_dir.resolve()
    if output == ledger or ledger in output.parents:
        raise ForwardBuildError("OUTPUT_INSIDE_LEDGER")


def _atomic_write(path: Path, payload: bytes) -> None:
    partial = path.with_name(f".{path.name}.partial")
    partial.write_bytes(payload)
    partial.replace(path)


def _canonical(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Publish one derived Ledger T+ generation")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args(argv)
    try:
        document = build_forward_document(
            Path(args.ledger),
            Path(args.reference),
            expected_ledger_hashes=STAGE2_LEDGER_HASHES,
            expected_reference_sha256=STAGE2_REFERENCE_SHA256,
        )
        result = publish_forward_document(document, Path(args.output_root), Path(args.ledger))
    except ForwardBuildError as exc:
        print(json.dumps({"ok": False, "reason": exc.reason}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

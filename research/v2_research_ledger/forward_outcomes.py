"""Derived T+ outcomes for the Research Ledger.

The builder reads a sealed ledger and a validated approximate reference store.
``as_of`` is the validated Price Book's last trading session. The system clock
is not a session. A dry run reports the generation and writes nothing.
``--publish`` writes one new generation. An existing generation with different
bytes is refused, and a failed index update removes a generation created by
that same attempt.

The sealed JSONL files, Guardian Research, and the reference store are not
written. The panel falls back to ``UNAVAILABLE_NOT_RECOMPUTED`` when no
generation matches the ledger that is open.
"""

from __future__ import annotations

import datetime
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
from research.guardian_research.reference_export import _digest, read_reference_store
from research.v2_research_ledger.durable_store import MANIFEST_SCHEMA

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
PACKAGED_OUTCOMES = Path(__file__).resolve().parent / "outcomes"
# Byte pins for the committed Stage 2 store. Publication does not read them.
# A newer ledger or Price Book is validated from the files that were opened.
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
    expected_ledger_hashes: Mapping[str, str] | None = None,
    expected_reference_sha256: str | None = None,
) -> dict[str, Any]:
    """Return a derived document. The ledger and the reference file are only read.

    The sealed-file hashes, manifest counts, Price Book checksum, price basis,
    source, and trading calendar are always checked. Optional expected hashes
    are an additional pin. They do not replace those checks, and publication
    does not require the Stage 2 pins.
    """
    ledger_root = Path(ledger_dir)
    hashes = file_hashes(ledger_root)
    if expected_ledger_hashes is not None and dict(expected_ledger_hashes) != hashes:
        raise ForwardBuildError("LEDGER_HASH_MISMATCH")
    identities, links, conflict_count = _load_ledger(ledger_root)
    _validate_manifest(ledger_root, len(identities), len(links), conflict_count)
    _require_unique_coverage(identities)
    store = _validated_reference(Path(reference_path))
    if expected_reference_sha256 is not None and store.get("content_sha256") != expected_reference_sha256:
        raise ForwardBuildError("REFERENCE_NOT_VALIDATED")
    sessions = _calendar(store)
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


def plan_forward_publication(document: Mapping[str, Any], output_root: Path, ledger_dir: Path) -> dict[str, Any]:
    """Report the write. This creates no directory and replaces no file."""
    plan = _publication_plan(document, output_root, ledger_dir)
    return {key: value for key, value in plan.items() if key not in {"entry", "payload"}}


def publish_forward_document(document: Mapping[str, Any], output_root: Path, ledger_dir: Path) -> dict[str, Any]:
    """Write one generation. A different body for the same generation is refused."""
    plan = _publication_plan(document, output_root, ledger_dir)
    target = Path(plan["path"])
    if plan["file_status"] == "unchanged" and plan["index_status"] == "unchanged":
        return {
            "file_status": "unchanged",
            "generation_id": plan["generation_id"],
            "index_status": "unchanged",
            "path": str(target),
        }
    created = False
    if plan["file_status"] == "would_write":
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, plan["payload"])
        created = True
    try:
        if plan["index_status"] == "would_write":
            index_status = _record_generation(Path(output_root) / "index.json", plan["entry"])
        else:
            index_status = "unchanged"
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return {
        "file_status": "written" if created else "unchanged",
        "generation_id": plan["generation_id"],
        "index_status": index_status,
        "path": str(target),
    }


def attachable_outcomes(ledger_dir: Path, outcomes_root: Path | None = None) -> dict[str, Any] | None:
    """Return the newest matching generation, or None when the panel must stay unavailable."""
    root = Path(outcomes_root) if outcomes_root is not None else Path(ledger_dir).parent / "outcomes"
    try:
        hashes = file_hashes(ledger_dir)
        identities, links, _conflict_count = _load_ledger(Path(ledger_dir))
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
    sessions = [_session_day(item) for item in store.get("trading_sessions") or []]
    as_of = str(store.get("as_of") or "")
    if not sessions or sessions != sorted(set(sessions)) or sessions[-1] != as_of:
        raise ForwardBuildError("CALENDAR_INVALID")
    if _session_day(as_of) != as_of:
        raise ForwardBuildError("CALENDAR_INVALID")
    for row in store.get("rows") or []:
        if str(row.get("session") or "") > as_of:
            raise ForwardBuildError("LOOKAHEAD_ROW")
    return sessions


def _session_day(value: object) -> str:
    text = str(value or "")
    try:
        parsed = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise ForwardBuildError("CALENDAR_INVALID") from exc
    if parsed.isoformat() != text:
        raise ForwardBuildError("CALENDAR_INVALID")
    return text


def _validated_reference(path: Path) -> dict[str, Any]:
    """Accept a store only when its checksum, basis, and source agree."""
    store = read_reference_store(path)
    if store is not None:
        return store
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ForwardBuildError("REFERENCE_NOT_VALIDATED") from exc
    if not isinstance(document, dict):
        raise ForwardBuildError("REFERENCE_NOT_VALIDATED")
    if document.get("price_basis") != PRICE_BASIS:
        raise ForwardBuildError("REFERENCE_BASIS_MISMATCH")
    if document.get("source") != SOURCE:
        raise ForwardBuildError("REFERENCE_SOURCE_MISMATCH")
    if document.get("content_sha256") != _digest(document):
        raise ForwardBuildError("REFERENCE_CHECKSUM_MISMATCH")
    raise ForwardBuildError("REFERENCE_NOT_VALIDATED")


def _validate_manifest(directory: Path, identity_count: int, link_count: int, conflict_count: int) -> None:
    path = directory / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ForwardBuildError("MANIFEST_INVALID") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ForwardBuildError("MANIFEST_INVALID")
    counts = (
        manifest.get("identity_count") == identity_count
        and manifest.get("link_count") == link_count
        and manifest.get("conflict_count") == conflict_count
    )
    if not counts:
        raise ForwardBuildError("MANIFEST_COUNT_MISMATCH")
    if manifest.get("final_buy_enabled") not in {None, False}:
        raise ForwardBuildError("MANIFEST_INVALID")
    if manifest.get("t_plus_recomputed") not in {None, False}:
        raise ForwardBuildError("MANIFEST_INVALID")


def _load_ledger(directory: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], int]:
    identities = _jsonl(directory / "identities.jsonl")
    links: dict[str, dict[str, Any]] = {}
    for row in _jsonl(directory / "links.jsonl"):
        link_id = str(row.get("link_id") or "")
        if not link_id or link_id in links:
            raise ForwardBuildError("LEDGER_ROW_INVALID")
        links[link_id] = row
    conflicts = _jsonl(directory / "conflicts.jsonl")
    return identities, links, len(conflicts)


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


def _publication_plan(document: Mapping[str, Any], output_root: Path, ledger_dir: Path) -> dict[str, Any]:
    root = Path(output_root)
    _refuse_protected_output(root, Path(ledger_dir))
    _require_publishable(document)
    generation_id = _generation_id(document)
    payload = _canonical(document)
    target = root / "generations" / f"{generation_id}.json"
    if target.is_file():
        if target.read_bytes() != payload:
            raise ForwardBuildError("REFUSE_OVERWRITE")
        file_status = "unchanged"
    else:
        file_status = "would_write"
    entry = {
        "as_of": document["as_of"],
        "calculation_version": document["calculation_version"],
        "generation_id": generation_id,
        "identity_count": document["identity_count"],
        "ledger_hashes": document["ledger_hashes"],
        "path": f"generations/{generation_id}.json",
        "reference_sha256": document["reference_sha256"],
    }
    return {
        "entry": entry,
        "file_status": file_status,
        "generation_id": generation_id,
        "index_status": _index_disposition(root / "index.json", entry),
        "path": str(target),
        "payload": payload,
    }


def _require_publishable(document: Mapping[str, Any]) -> None:
    if document.get("schema") != DOCUMENT_SCHEMA or document.get("calculation_version") != CALCULATION_VERSION:
        raise ForwardBuildError("DOCUMENT_INVALID")
    if document.get("official_pnl") is not False or document.get("price_basis") != PRICE_BASIS:
        raise ForwardBuildError("DOCUMENT_INVALID")
    if document.get("reference_source") != SOURCE:
        raise ForwardBuildError("DOCUMENT_INVALID")
    sessions = document.get("trading_sessions")
    if not isinstance(sessions, list) or not sessions or document.get("as_of") != sessions[-1]:
        raise ForwardBuildError("CALENDAR_INVALID")
    if not isinstance(document.get("ledger_hashes"), dict) or not document.get("reference_sha256"):
        raise ForwardBuildError("DOCUMENT_INVALID")
    rows = document.get("rows")
    if not isinstance(rows, list) or document.get("identity_count") != len(rows):
        raise ForwardBuildError("DOCUMENT_INVALID")


def _index_disposition(path: Path, entry: Mapping[str, Any]) -> str:
    if path.exists() and not path.is_file():
        raise ForwardBuildError("INDEX_INVALID")
    if not path.is_file():
        return "would_write"
    current = _read_index(path)
    if current is None:
        raise ForwardBuildError("INDEX_INVALID")
    for existing in current.get("generations") or []:
        if not isinstance(existing, dict) or existing.get("generation_id") != entry["generation_id"]:
            continue
        if existing != dict(entry):
            raise ForwardBuildError("REFUSE_OVERWRITE")
        return "unchanged"
    return "would_write"


def _generation_id(document: Mapping[str, Any]) -> str:
    ledger = hashlib.sha256(_canonical({"ledger_hashes": document["ledger_hashes"]})).hexdigest()[:12]
    reference = str(document.get("reference_sha256") or "")[:12]
    return f"{document['as_of']}_{ledger}_{reference}"


def _record_generation(path: Path, entry: Mapping[str, Any]) -> str:
    if _index_disposition(path, entry) == "unchanged":
        return "unchanged"
    current = _read_index(path) if path.is_file() else None
    generations = list(current.get("generations") or []) if current else []
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
    try:
        partial.write_bytes(payload)
        partial.replace(path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _canonical(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_packaged_outcomes(output_root: Path) -> bool:
    return Path(output_root).resolve() == PACKAGED_OUTCOMES.resolve()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate or publish one derived Ledger T+ generation")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--publish", action="store_true", help="Write the generation. Omit for a dry run.")
    parser.add_argument(
        "--approve-repository-write",
        action="store_true",
        help="Required only when --publish targets the committed outcomes directory.",
    )
    parser.add_argument("--expect-reference-sha256", default=None)
    args = parser.parse_args(argv)
    try:
        document = build_forward_document(
            Path(args.ledger),
            Path(args.reference),
            expected_reference_sha256=args.expect_reference_sha256,
        )
        output = Path(args.output_root)
        if args.publish and _is_packaged_outcomes(output) and not args.approve_repository_write:
            raise ForwardBuildError("REPOSITORY_PUBLICATION_NOT_APPROVED")
        if args.publish:
            result = publish_forward_document(document, output, Path(args.ledger))
            mode = "publish"
        else:
            result = plan_forward_publication(document, output, Path(args.ledger))
            mode = "dry_run"
    except ForwardBuildError as exc:
        print(json.dumps({"ok": False, "reason": exc.reason}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "as_of": document["as_of"],
                "calculation_version": document["calculation_version"],
                "coverage": document["coverage"],
                "identity_count": document["identity_count"],
                "ledger_hashes": document["ledger_hashes"],
                "mode": mode,
                "ok": True,
                "price_basis": document["price_basis"],
                "reference_sha256": document["reference_sha256"],
                "reference_source": document["reference_source"],
                "trading_sessions": document["trading_sessions"],
                **result,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

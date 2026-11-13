"""First-write VNINDEX witness for a Guardian T0 freeze batch.

The writer and the delayed sealer share one hash. A later probe is not a
substitute for a missing or broken stamp.
"""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from research.guardian_research.indicators import finite_number
from research.guardian_research.session_authority import WITNESS_SOURCE

PROVENANCE = "research.guardian_research.session_authority.probe_vnindex"
WITNESS_COLUMNS = (
    "guardian_witness_source",
    "guardian_witness_bar_session",
    "guardian_witness_provenance",
    "guardian_witness_sha256",
)
HASH_FIELDS = ("market_real", "price", "ema9", "ma20", "obv", "obv_ema9")


def stamp_new_freeze_rows(rows: pd.DataFrame, probe=None) -> pd.DataFrame:
    """Stamp one verified batch. A failed or mismatched probe leaves blanks.

    The caller has already chosen the rows that are being appended. This does
    not fill rows that were stored before, and it does not probe unless the
    batch has one session and one observation timestamp.
    """
    stamped = rows.copy()
    for column in WITNESS_COLUMNS:
        stamped[column] = ""
    if stamped.empty:
        return stamped
    sessions = {_session_text(value) for value in stamped["trade_date"]}
    frozen = {_cell(value) for value in stamped["frozen_at"]}
    if len(sessions) != 1 or "" in sessions or len(frozen) != 1 or "" in frozen:
        return stamped
    session = next(iter(sessions))
    frozen_at = next(iter(frozen))
    try:
        witness = _read_probe(session, probe)
    except Exception:
        return stamped
    if not _probe_matches(witness, session):
        return stamped
    digest = witness_digest(
        session=session,
        frozen_at=frozen_at,
        source=WITNESS_SOURCE,
        bar_session=session,
        rows=stamped,
    )
    if not digest:
        return stamped
    stamped["guardian_witness_source"] = WITNESS_SOURCE
    stamped["guardian_witness_bar_session"] = session
    stamped["guardian_witness_provenance"] = PROVENANCE
    stamped["guardian_witness_sha256"] = digest
    return stamped


def witness_digest(
    *,
    session: str,
    frozen_at: str,
    source: str,
    bar_session: str,
    rows: pd.DataFrame,
) -> str | None:
    """SHA-256 of the canonical batch. None means the batch cannot be stamped."""
    body_rows = []
    for _, row in rows.iterrows():
        identity = _cell(row.get("observation_id"))
        symbol = _symbol(row.get("symbol"))
        if not identity or not symbol:
            return None
        numbers = {}
        for field in HASH_FIELDS:
            number = canonical_number(row.get(field))
            if number is None:
                return None
            numbers[field] = number
        body_rows.append({"observation_id": identity, "symbol": symbol, **numbers})
    body_rows.sort(key=lambda item: item["symbol"])
    body = {
        "bar_session": bar_session,
        "frozen_at": frozen_at,
        "rows": body_rows,
        "session": session,
        "source": source,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonical_number(value) -> str | None:
    """One decimal rendering that survives a CSV write and read."""
    number = finite_number(value)
    if number is None:
        return None
    return format(number, ".12g")


def verify_persisted_witness(frame: pd.DataFrame, session: str) -> tuple[dict | None, str | None]:
    """Recompute the stamp. This does not download a bar or read observations."""
    if any(column not in frame.columns for column in WITNESS_COLUMNS):
        return None, "WITNESS_ABSENT"
    records = []
    for _, row in frame.iterrows():
        item = {column: _cell(row.get(column)) for column in WITNESS_COLUMNS}
        if any(not item[column] for column in WITNESS_COLUMNS):
            return None, "WITNESS_ABSENT"
        records.append(item)
    if not records:
        return None, "WITNESS_ABSENT"
    sources = {item["guardian_witness_source"] for item in records}
    bars = {item["guardian_witness_bar_session"] for item in records}
    provenances = {item["guardian_witness_provenance"] for item in records}
    digests = {item["guardian_witness_sha256"] for item in records}
    if len(sources) != 1 or len(bars) != 1 or len(provenances) != 1 or len(digests) != 1:
        return None, "WITNESS_INCONSISTENT"
    source = next(iter(sources))
    bar = next(iter(bars))
    provenance = next(iter(provenances))
    digest = next(iter(digests))
    if source != WITNESS_SOURCE or provenance != PROVENANCE:
        return None, "WITNESS_INVALID"
    if bar != session:
        return None, "WITNESS_INCONSISTENT"
    frozen_values = {_cell(value) for value in frame["frozen_at"]}
    if len(frozen_values) != 1 or "" in frozen_values:
        return None, "WITNESS_INCONSISTENT"
    recomputed = witness_digest(
        session=session,
        frozen_at=next(iter(frozen_values)),
        source=source,
        bar_session=bar,
        rows=frame,
    )
    if recomputed is None or recomputed != digest:
        return None, "WITNESS_INTEGRITY"
    return {
        "source": WITNESS_SOURCE,
        "bar_session": bar,
        "probe_error": None,
        "provenance": PROVENANCE,
    }, None


def _read_probe(session: str, probe):
    if probe is not None:
        return probe(session)
    from research.guardian_research import session_authority

    return session_authority.probe_vnindex(session)


def _probe_matches(witness, session: str) -> bool:
    if not isinstance(witness, dict) or witness.get("source") != WITNESS_SOURCE:
        return False
    if witness.get("probe_error"):
        return False
    return _session_text(witness.get("bar_session")) == session


def _session_text(value) -> str:
    text = _cell(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return ""


def _symbol(value) -> str:
    return _cell(value).upper()


def _cell(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()

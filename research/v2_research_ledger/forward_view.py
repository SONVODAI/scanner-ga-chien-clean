"""Forward-status evaluation for caller-supplied rows and a reference store.

The 14:45 rule lives in ``research.approximate_returns``. This module does not
edit those helpers, does not read a default reference file, and does not write
the durable store or a horizons file. A missing book is the caller's problem:
pass the store in, or do not call.

The sealed ``t0_price`` is copied through and is never the return denominator.
``t0_price_used_as_denominator`` stays false. Only an ``APPROX_AVAILABLE`` cell
keeps a return. Every other status keeps ``return_pct`` null.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from research.approximate_returns.contract import PRICE_BASIS
from research.approximate_returns.returns import evaluate_rows

SCHEMA = "v2_research_forward_status.v1"


def evaluate_forward_status(
    rows: Sequence[Mapping[str, Any]],
    reference_store: Mapping[str, Any],
) -> dict[str, Any]:
    """Return horizon statuses for copies of ``rows``. Inputs are not modified."""
    if not isinstance(reference_store, Mapping):
        raise TypeError("reference_store must be a mapping supplied by the caller")
    originals = [dict(row) for row in rows]
    evaluated = evaluate_rows(originals, dict(reference_store))
    published = [
        _published_row(source, result)
        for source, result in zip(originals, evaluated, strict=True)
    ]
    return {
        "official_pnl": False,
        "price_basis": PRICE_BASIS,
        "reference_file_assumed": False,
        "rows": published,
        "schema": SCHEMA,
    }


def _published_row(source: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    horizons = {
        label: _published_cell(cell)
        for label, cell in dict(result.get("horizons") or {}).items()
    }
    return {
        "candidate_first_seen_ts": source.get("candidate_first_seen_ts"),
        "horizons": horizons,
        "price_basis": PRICE_BASIS,
        "reference_t0_price": result.get("reference_t0_price"),
        "row_id": source.get("row_id"),
        "source": source.get("source"),
        "source_attribution": source.get("source_attribution"),
        "symbol": source.get("symbol"),
        "t0_date": source.get("t0_date"),
        "t0_price": source.get("t0_price"),
        "t0_price_provenance": source.get("t0_price_provenance"),
        "t0_price_used_as_denominator": False,
    }


def _published_cell(cell: Mapping[str, Any]) -> dict[str, Any]:
    primary = bool(cell.get("included_in_primary"))
    return {
        "included_in_primary": primary,
        "reference_price": cell.get("reference_price") if primary else None,
        "return_pct": cell.get("return_pct") if primary else None,
        "status": cell.get("status"),
        "target_session": cell.get("target_session"),
    }

"""Approximate forward results for a sealed Guardian snapshot.

The snapshot document is not modified. Missing prices stay null.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.approximate_returns.report import _performance
from research.approximate_returns.returns import evaluate_rows
from research.guardian_research.contract import CLASSIFICATIONS, FORWARD_HORIZONS
from research.guardian_research.performance import PRICE_BASIS, SCHEMA, _digest

DRAWDOWN_REASON = "INTRADAY_PATH_ABSENT"


def measure_snapshot(document: dict, store: dict) -> dict:
    """Measure T+n from the approximate reference store. Holdings are not created."""
    before = json.dumps(document, sort_keys=True)
    classified = list(document.get("rows") or [])
    prepared = [
        {
            "row_id": row.get("symbol"),
            "symbol": row.get("symbol"),
            "t0_date": document.get("session"),
            "source": "guardian_research",
            "t0_price": row.get("reference_price"),
            "t0_price_provenance": row.get("reference_price_provenance"),
            "action_state": row.get("classification"),
            "market_real": row.get("market_real"),
            "market_real_provenance": row.get("market_real_provenance"),
        }
        for row in classified
    ]
    evaluated = evaluate_rows(prepared, store)
    if json.dumps(document, sort_keys=True) != before:
        raise RuntimeError("snapshot was modified")
    by_class = {}
    for name in sorted(CLASSIFICATIONS):
        chosen = [row for row, source in zip(evaluated, classified) if source.get("classification") == name]
        by_class[name] = {
            "observations": len(chosen),
            "horizons": {f"T+{step}": _performance(chosen, f"T+{step}") for step in FORWARD_HORIZONS},
        }
    sell = by_class["SELL"]["horizons"]
    rows = []
    for source, item in zip(classified, evaluated):
        horizons = {}
        for step in FORWARD_HORIZONS:
            cell = item["horizons"][f"T+{step}"]
            horizons[f"T+{step}"] = {
                "status": cell["status"],
                "return_pct": cell["return_pct"],
                "included_in_primary": cell["included_in_primary"],
            }
        rows.append({
            "symbol": source.get("symbol"),
            "classification": source.get("classification"),
            "reason": source.get("reason"),
            "score": source.get("score"),
            "transition": source.get("transition"),
            "state_age_sessions": source.get("state_age_sessions"),
            "live_adjusted_input": bool((source.get("freshness") or {}).get("live_injected")),
            "position_inputs_required": source.get("position_inputs_required"),
            "position_inputs_used": source.get("position_inputs_used"),
            "horizons": horizons,
        })
    view = {
        "schema": SCHEMA,
        "price_basis": PRICE_BASIS,
        "official_pnl": False,
        "portfolio_decision": False,
        "observation_origin": document.get("observation_origin"),
        "session": document.get("session"),
        "snapshot_sha256": document.get("content_sha256"),
        "classification_version": document.get("classification_version"),
        "tracked_count": document.get("tracked_count"),
        "counts": document.get("counts"),
        "market_real": (document.get("market") or {}).get("market_real"),
        "market_real_status": (document.get("market") or {}).get("market_real_status"),
        "reconstruction": document.get("reconstruction"),
        "input_assessment": _inputs(classified),
        "classifications": by_class,
        "missed_rally": {
            "definition": "Share of SELL research labels whose later approximate return is positive by the stated threshold. Not a trade result.",
            "horizons": {
                label: {
                    "sample": item["primary"],
                    "above_3pct": item["win_rate_above_3pct"],
                    "above_5pct": item["win_rate_above_5pct"],
                }
                for label, item in sell.items()
            },
        },
        "subsequent_drawdown": {
            "status": "UNAVAILABLE",
            "reason": DRAWDOWN_REASON,
            "worst_drawdown_pct": None,
        },
        "transitions": _transitions(classified),
        "rows": rows,
        "statement": (
            "Approximate research returns use the last 5-minute close on both ends. "
            "They are not execution P&L. HOLD, WATCH, and SELL are research labels, not portfolio orders. "
            "A BACKFILLED snapshot was reconstructed from a persisted scan and is not a contemporaneous observation. "
            "Missing prices are left blank. No statistical significance is claimed."
        ),
    }
    view["content_sha256"] = _digest(view)
    return view


def write_performance_view(document: dict, store: dict, destination: Path) -> Path:
    view = measure_snapshot(document, store)
    target = Path(destination)
    payload = json.dumps(view, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    partial.write_text(payload, encoding="utf-8")
    partial.replace(target)
    return target


def _inputs(rows: list[dict]) -> dict:
    return {
        "classification_inputs": ["price", "ema9", "ma20", "obv", "obv_ema9"],
        "position_inputs_required": any(row.get("position_inputs_required") for row in rows),
        "position_inputs_used": any(row.get("position_inputs_used") for row in rows),
        "holdings_invented": False,
        "live_adjusted_inputs": sum(1 for row in rows if (row.get("freshness") or {}).get("live_injected")),
        "unavailable": sum(1 for row in rows if row.get("classification") == "UNAVAILABLE"),
    }


def _transitions(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row.get("transition") or "ABSENT")
        counts[name] = counts.get(name, 0) + 1
    return {"counts": dict(sorted(counts.items())), "signal_age_sessions": "state_age_sessions on each row"}

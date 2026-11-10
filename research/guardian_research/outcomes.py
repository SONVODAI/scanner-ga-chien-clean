"""T+ research over sealed Guardian snapshots.

Reads snapshots and, when present, the approximate reference store.
It does not write a snapshot, invent a session, or mix price bases.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.approximate_returns.contract import PRICE_BASIS, SCHEMA_REFERENCE
from research.approximate_returns.reference import index_store
from research.approximate_returns.report import _performance
from research.guardian_research.contract import FORWARD_CALENDAR, FORWARD_HORIZONS
from research.guardian_research.forward import measure_snapshot
from research.guardian_research.snapshot import read_snapshot

SCHEMA = "guardian_research_outcomes.v1"
STORE_NAME = "reference_store.json"
VIEW_NAME = "outcomes.json"
CLASS_ORDER = ("HOLD", "WATCH", "SELL", "UNAVAILABLE")
HORIZON_LABELS = tuple(f"T+{step}" for step in FORWARD_HORIZONS)


def refresh_outcomes(root: Path | None = None, store_path: Path | None = None, destination: Path | None = None) -> dict:
    """Rewrite the evidence file. Sealed snapshots are read and then re-read."""
    base = Path(root) if root is not None else _default_root()
    before = _snapshot_bytes(base)
    chosen = Path(store_path) if store_path is not None else _store_path(base)
    store = _read_store(chosen) if chosen is not None else None
    view = build_outcomes(base, store)
    target = Path(destination) if destination is not None else _package_view()
    _write(view, target)
    if _snapshot_bytes(base) != before:
        raise RuntimeError("sealed snapshot bytes changed")
    return {
        "status": "measured" if view["measured"] else "unmeasured",
        "evidence_status": view["evidence_status"],
        "sealed_sessions": [item["session"] for item in view["sealed_sessions"]],
        "path": str(target),
    }


def build_outcomes(root: Path, store: dict | None) -> dict:
    documents = _load_sealed(root)
    contemporaneous = [doc for doc in documents if doc.get("observation_origin") == "CONTEMPORANEOUS"]
    backfilled = [doc for doc in documents if doc.get("observation_origin") == "BACKFILLED"]
    accepted, store_status = _accept_store(store)
    measured = bool(contemporaneous) and accepted is not None
    rows = []
    if measured:
        lookup = index_store(accepted)
        for document in contemporaneous:
            view = measure_snapshot(document, accepted)
            by_symbol = {row.get("symbol"): row for row in document.get("rows") or []}
            for item in view["rows"]:
                source = by_symbol.get(item.get("symbol")) or {}
                horizons = {}
                for label in HORIZON_LABELS:
                    cell = dict(item["horizons"][label])
                    step = int(label.split("+", 1)[1])
                    adverse, adverse_status = _adverse(item.get("symbol"), document.get("session"), step, lookup)
                    cell["adverse_close_path_pct"] = adverse
                    cell["adverse_status"] = adverse_status
                    horizons[label] = cell
                rows.append({
                    "session": document.get("session"),
                    "symbol": item.get("symbol"),
                    "classification": item.get("classification"),
                    "tenure": _tenure(source),
                    "live_adjusted_input": bool((source.get("freshness") or {}).get("live_injected")),
                    "horizons": horizons,
                })
    else:
        for document in contemporaneous:
            for source in document.get("rows") or []:
                rows.append({
                    "session": document.get("session"),
                    "symbol": source.get("symbol"),
                    "classification": source.get("classification"),
                    "tenure": _tenure(source),
                    "live_adjusted_input": bool((source.get("freshness") or {}).get("live_injected")),
                    "horizons": {label: _blank_cell() for label in HORIZON_LABELS},
                })
    evidence = "MEASURED" if measured else store_status
    view = {
        "schema": SCHEMA,
        "price_basis": PRICE_BASIS if measured else None,
        "official_pnl": False,
        "portfolio_decision": False,
        "measured": measured,
        "evidence_status": evidence,
        "calendar": FORWARD_CALENDAR,
        "calendar_status": "REFERENCE_STORE" if measured else "UNAVAILABLE",
        "sealed_sessions": [_session_fact(doc) for doc in documents],
        "contemporaneous_sessions": [doc.get("session") for doc in contemporaneous],
        "backfilled_sessions_excluded": [doc.get("session") for doc in backfilled],
        "classifications": _by_class(rows),
        "tenure": _tenure_summary(rows),
        "false_sell": _false_sell(rows),
        "rows": rows,
        "statement": _statement(measured, evidence),
    }
    view["content_sha256"] = _digest(view)
    return view


def read_outcomes(path: Path | None = None) -> dict | None:
    target = Path(path) if path is not None else _package_view()
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        return None
    if document.get("official_pnl") is not False or document.get("portfolio_decision") is not False:
        return None
    if document.get("content_sha256") != _digest(document):
        return None
    return document


def _accept_store(store: dict | None) -> tuple[dict | None, str]:
    if not isinstance(store, dict):
        return None, "PRICE_REFERENCE_ABSENT"
    if store.get("schema") != SCHEMA_REFERENCE or store.get("price_basis") != PRICE_BASIS:
        return None, "PRICE_BASIS_MISMATCH"
    sessions = [str(item) for item in store.get("trading_sessions") or []]
    if not sessions or sessions != sorted(set(sessions)) or store.get("as_of") != sessions[-1]:
        return None, "CALENDAR_UNVERIFIED"
    return store, "MEASURED"


def _adverse(symbol, origin, step: int, lookup: dict) -> tuple[float | None, str]:
    """Worst close-to-close change through T+n. Not an intraday drawdown."""
    sessions = lookup["sessions"]
    position = lookup["index"].get(origin)
    start = lookup["prices"].get((symbol, origin))
    if position is None or start is None:
        return None, "T0_REFERENCE_MISSING"
    if position + step >= len(sessions):
        return None, "NOT_YET_OBSERVED"
    worst = None
    for offset in range(1, step + 1):
        price = lookup["prices"].get((symbol, sessions[position + offset]))
        if price is None:
            return None, "PATH_INCOMPLETE"
        change = (price / start - 1) * 100
        worst = change if worst is None else min(worst, change)
    return round(worst, 4), "DAILY_CLOSE_PATH"


def _by_class(rows: list[dict]) -> dict:
    grouped = {}
    for name in CLASS_ORDER:
        chosen = [row for row in rows if row.get("classification") == name]
        grouped[name] = {
            "observations": len(chosen),
            "new_or_changed": sum(1 for row in chosen if row.get("tenure") == "NEW_OR_CHANGED"),
            "persistent": sum(1 for row in chosen if row.get("tenure") == "PERSISTENT"),
            "horizons": {label: _horizon_summary(chosen, label) for label in HORIZON_LABELS},
        }
    return grouped


def _horizon_summary(rows: list[dict], label: str) -> dict:
    summary = _performance(rows, label)
    primary = [
        row["horizons"][label]["return_pct"]
        for row in rows
        if row["horizons"][label].get("included_in_primary")
    ]
    summary["positive_return_rate"] = _share(primary, lambda value: value > 0)
    summary["loss_rate_below_minus_3pct"] = _share(primary, lambda value: value < -3)
    summary["loss_rate_below_minus_5pct"] = _share(primary, lambda value: value < -5)
    summary["unmeasured"] = sum(1 for row in rows if row["horizons"][label].get("status") == "NOT_MEASURED")
    summary["evidence"] = "MEASURED" if summary["primary"] else "INSUFFICIENT_EVIDENCE"
    adverse = [
        row["horizons"][label].get("adverse_close_path_pct")
        for row in rows
        if row["horizons"][label].get("adverse_status") == "DAILY_CLOSE_PATH"
        and row["horizons"][label].get("adverse_close_path_pct") is not None
    ]
    summary["adverse_close_path_average_pct"] = _mean(adverse)
    summary["adverse_close_path_worst_pct"] = round(min(adverse), 4) if adverse else None
    summary["adverse_sample"] = len(adverse)
    return summary


def _false_sell(rows: list[dict]) -> dict:
    sell = [row for row in rows if row.get("classification") == "SELL"]
    horizons = {}
    any_primary = False
    for label in HORIZON_LABELS:
        primary = [
            row["horizons"][label]["return_pct"]
            for row in sell
            if row["horizons"][label].get("included_in_primary")
        ]
        any_primary = any_primary or bool(primary)
        horizons[label] = {
            "sample": len(primary),
            "evidence": "MEASURED" if primary else "INSUFFICIENT_EVIDENCE",
            "rose": _share(primary, lambda value: value > 0),
            "rose_above_3pct": _share(primary, lambda value: value > 3),
            "rose_above_5pct": _share(primary, lambda value: value > 5),
            "fell": _share(primary, lambda value: value < 0),
        }
    return {
        "definition": "SELL research labels whose later same-basis return is positive. Not a portfolio order.",
        "evidence": "MEASURED" if any_primary else "INSUFFICIENT_EVIDENCE",
        "horizons": horizons,
    }


def _tenure(row: dict) -> str:
    age = row.get("state_age_sessions")
    transition = str(row.get("transition") or "")
    if transition == "CHANGED" or age == 1:
        return "NEW_OR_CHANGED"
    if isinstance(age, int) and age > 1:
        return "PERSISTENT"
    return "UNCLASSIFIED_TENURE"


def _tenure_summary(rows: list[dict]) -> dict:
    counts = {"NEW_OR_CHANGED": 0, "PERSISTENT": 0, "UNCLASSIFIED_TENURE": 0}
    for row in rows:
        name = row.get("tenure")
        if name in counts:
            counts[name] += 1
    return counts


def _session_fact(document: dict) -> dict:
    rows = document.get("rows") or []
    return {
        "session": document.get("session"),
        "observation_origin": document.get("observation_origin"),
        "tracked_count": document.get("tracked_count"),
        "counts": document.get("counts"),
        "content_sha256": document.get("content_sha256"),
        "live_adjusted_inputs": sum(1 for row in rows if (row.get("freshness") or {}).get("live_injected")),
    }


def _blank_cell() -> dict:
    return {
        "status": "NOT_MEASURED",
        "return_pct": None,
        "included_in_primary": False,
        "adverse_close_path_pct": None,
        "adverse_status": "NOT_MEASURED",
    }


def _statement(measured: bool, evidence: str) -> str:
    if measured:
        return (
            "Returns use the approximate last 5-minute close on both ends. "
            "They are not official closes and not execution P&L. "
            "T+n follows the reference store's verified trading sessions. "
            "Each sealed session is one observation; overlapping symbols are not independent samples. "
            "A horizon with no primary sample is insufficient evidence. "
            "Adverse movement is the worst close-to-close change through that horizon, not an intraday drawdown."
        )
    return (
        f"Forward returns were not calculated ({evidence}). "
        "No session, price, or classification was invented. "
        "Sealed T0 counts below are inventory, not performance."
    )


def _load_sealed(root: Path) -> list[dict]:
    folder = Path(root) / "sessions"
    if not folder.is_dir():
        return []
    documents = []
    for path in sorted(folder.glob("*.json")):
        try:
            document = read_snapshot(path)
        except (OSError, ValueError):
            continue
        if isinstance(document, dict):
            documents.append(document)
    return documents


def _store_path(root: Path) -> Path | None:
    from research.guardian_research.reference_export import resolve_store_path

    return resolve_store_path(root)


def _read_store(path: Path) -> dict | None:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return document if isinstance(document, dict) else None


def _snapshot_bytes(root: Path) -> dict[str, bytes]:
    folder = Path(root) / "sessions"
    if not folder.is_dir():
        return {}
    return {path.name: path.read_bytes() for path in sorted(folder.glob("*.json"))}


def _write(view: dict, target: Path) -> None:
    payload = json.dumps(view, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    partial.write_text(payload, encoding="utf-8")
    partial.replace(target)


def _digest(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "content_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _share(values: list[float], predicate) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if predicate(value)) / len(values), 4)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _default_root() -> Path:
    from research.guardian_research.panel import default_root

    return default_root()


def _package_view() -> Path:
    return Path(__file__).resolve().parent / VIEW_NAME


def main() -> int:
    result = refresh_outcomes()
    print(json.dumps({key: result[key] for key in ("status", "evidence_status", "sealed_sessions")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

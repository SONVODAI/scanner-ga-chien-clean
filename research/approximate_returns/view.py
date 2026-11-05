"""Display projection of a finished approximate panel. Returns are not recalculated."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "approximate_performance_view.v1"
BUNDLED_VIEW = Path(__file__).resolve().parent / "performance_view.json"


def project_view(panel: dict) -> dict:
    """Copy the stored summary into the Cloud view. The frozen rows stay in the panel."""
    from research.approximate_returns.contract import PRICE_BASIS, SOURCE
    from research.approximate_returns.report import overall_performance

    summary = panel.get("summary") if isinstance(panel.get("summary"), dict) else {}
    rows = list(panel.get("rows") or [])
    gaps = [row.get("t0_gap_pct") for row in rows if isinstance(row.get("t0_gap_pct"), (int, float))]
    document = {
        "schema": SCHEMA,
        "price_basis": panel.get("price_basis") or PRICE_BASIS,
        "source": panel.get("source") or SOURCE,
        "official_pnl": False,
        "executed_buys": False,
        "as_of": panel.get("as_of"),
        "panel_sha256": panel.get("content_sha256"),
        "records": summary.get("records"),
        "deduped_observations": summary.get("deduped_observations"),
        "coverage": summary.get("coverage"),
        "overall": overall_performance(rows),
        "cohorts": summary.get("cohorts"),
        "market_context": summary.get("market_context"),
        "action_states": summary.get("action_states"),
        "t0_gaps": {
            "rows_with_both_prices": len(gaps),
            "abs_gap_at_least_2pct": sum(1 for value in gaps if abs(value) >= 2),
            "abs_gap_at_least_5pct": sum(1 for value in gaps if abs(value) >= 5),
        },
        "discontinuities": list(panel.get("discontinuities") or []),
        "statement": (
            "Approximate research returns use the last 5-minute close on both ends. "
            "They are not execution P&L. WAIT and NO_OBSERVATION are not executed buys. "
            "Every statistic is shown with its sample count. "
            "Row coverage counts every frozen row. Cohort statistics count each symbol and T0 date once."
        ),
    }
    document["content_sha256"] = _digest(document)
    return document


def write_view(panel_path: Path, destination: Path | None = None) -> Path:
    from research.approximate_returns.build import read_panel

    panel = read_panel(panel_path)
    document = project_view(panel)
    target = Path(destination) if destination is not None else BUNDLED_VIEW
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    partial.write_text(payload, encoding="utf-8")
    partial.replace(target)
    return target


def read_view(path: Path) -> dict | None:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(document, dict):
        return None
    if document.get("schema") != SCHEMA or document.get("official_pnl") is not False:
        return None
    if document.get("content_sha256") != _digest(document):
        return None
    return document


def _digest(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "content_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

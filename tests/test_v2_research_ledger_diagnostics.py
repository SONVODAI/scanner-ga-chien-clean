"""Read-only delivery diagnostics. The scanner app is not imported."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from modules.v2_research_ledger_panel.ui import (
    format_delivery_diagnostics,
    format_row_composition,
    render_v2_research_ledger_panel,
)
from research.v2_research_ledger.delivery_view import load_delivery
from research.v2_research_ledger.serve_generation import publish_serving
from datetime import datetime, timezone

STAMP = datetime(2026, 10, 30, 15, 35, tzinfo=timezone.utc)


def _write_source(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    board = {
        "as_of": "2026-10-29",
        "coverage": {"rows": 1},
        "freshness": {"reasons": ["MISSING_SOURCE:sidecar"], "source_health": {"sidecar": {"status": "MISSING"}}},
        "price_book": "absent",
        "rows": [
            {
                "cohort": "nomination",
                "row_id": "brain_a_scan_setup|2026-10-28|HPG|seen",
                "source": "brain_a_scan_setup",
                "symbol": "HPG",
                "t0_date": "2026-10-28",
                "t0_price": None,
            }
        ],
    }
    board_bytes = (json.dumps(board, sort_keys=True) + "\n").encode("utf-8")
    clock = (
        json.dumps(
            {"evidence": None, "schema": "v2_research_ledger_source_clock.v1", "sidecar": None, "sweet": None},
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(board_bytes).hexdigest()
    manifest = {
        "board_bytes": len(board_bytes),
        "board_sha256": digest,
        "clock_sha256": hashlib.sha256(clock).hexdigest(),
        "final_buy_enabled": False,
        "generation_id": digest,
        "rows": 1,
        "schema": "v2_research_publisher_manifest.v1",
        "source_health": {
            "action_evidence": {"status": "PRESENT"},
            "sidecar": {"status": "MISSING"},
            "sweetspot": {"status": "MISSING"},
        },
    }
    (directory / "board.json").write_bytes(board_bytes)
    (directory / "source_clock.json").write_bytes(clock)
    (directory / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"))


class _Expander:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.captions: list[str] = []

    def expander(self, *_args, **_kwargs):
        return _Expander()

    def caption(self, text: str) -> None:
        self.captions.append(str(text))

    def warning(self, text: str) -> None:
        self.captions.append(str(text))

    def selectbox(self, _label, options, index=0):
        return options[index]

    def text_input(self, _label, value=""):
        return value

    def dataframe(self, *_args, **_kwargs):
        return None


def test_panel_reads_generation_without_the_scanner(tmp_path: Path):
    source = tmp_path / "source"
    store = tmp_path / "store"
    _write_source(source)
    published = publish_serving(source, store, published_at=STAMP)
    assert published.status == "EXPORTED"
    view = load_delivery(store / "generations" / published.generation_id)
    assert view.diagnostics is not None
    line = format_delivery_diagnostics(view.diagnostics)
    assert f"generation={published.generation_id}" in line
    assert "as_of=2026-10-29" in line
    assert f"published_at={STAMP.isoformat()}" in line
    assert "rows=1" in line
    assert "sidecar=MISSING" in line
    assert "sweetspot=MISSING" in line
    assert "action_evidence=PRESENT" in line
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(fake, delivery_dir=store / "generations" / published.generation_id)
    assert any(line in caption for caption in fake.captions)
    assert any(
        "research_rows=1 attributed_nominations=1 unattributed_action_only=0." in caption
        for caption in fake.captions
    )
    assert not any("BUY" in caption and "order" in caption.lower() for caption in fake.captions)


def test_composition_separates_nominations_from_unattributed_actions():
    rows = [
        {"cohort": "nomination", "source": "brain_a_scan_setup", "t0_date": "2026-10-28"},
        {"cohort": "nomination", "source": "market_aware_sweetspot", "t0_date": "2026-10-26"},
        {"cohort": "action_unattributed", "source": "unattributed", "t0_date": "2026-10-30"},
    ]
    assert format_row_composition(rows) == (
        "research_rows=3 attributed_nominations=2 unattributed_action_only=1."
    )


def test_panel_module_does_not_import_the_scanner():
    path = Path(__file__).resolve().parents[1] / "modules" / "v2_research_ledger_panel" / "ui.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    banned = ("app", "vnstock", "live_candidate", "market_first")
    assert "research.v2_research_ledger.delivery_view" in imported
    assert not any(name == word or name.startswith(word + ".") for name in imported for word in banned)

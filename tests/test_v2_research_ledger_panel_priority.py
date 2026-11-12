"""The durable store is the current ledger panel. A remote trio stays historical."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from research.approximate_returns.view import BUNDLED_VIEW, read_view
from research.v2_research_ledger.delivery_view import DATA_FRESH, DELIVERY_UNAVAILABLE, SOURCE_STALE, DeliveryView
from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.ingest_rows import ingest_sources
from research.v2_research_ledger.panel_board import HORIZON_STATUS
from modules.v2_research_ledger_panel.ui import render_v2_research_ledger_panel

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "research" / "v2_research_ledger" / "durable"
PANEL = ROOT / "modules" / "v2_research_ledger_panel" / "ui.py"


class _Expander:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.captions: list[str] = []
        self.frames: list[object] = []

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

    def dataframe(self, frame, *_args, **_kwargs):
        self.frames.append(frame)


def _sidecar(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "freeze_ledger": [
                    {
                        "breakout_ref_at_first_seen": 27100.0,
                        "candidate_first_seen_ts": "2026-11-06T19:00:00+07:00",
                        "ema9_at_first_seen": 26990.0,
                        "price_at_first_seen": 27000.0,
                        "session": "2026-11-05",
                        "symbol": "HPG",
                    }
                ],
                "observed_at": "2026-11-12T10:26:13+07:00",
                "rows": [],
                "session": "2026-11-12",
            }
        ),
        encoding="utf-8",
    )


def _store(tmp_path: Path) -> Path:
    sidecar = tmp_path / "camera_sidecar.json"
    _sidecar(sidecar)
    directory = tmp_path / "store"
    ingest_sources(DurableRowStore(directory), sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    return directory


def _remote(state: str, symbol: str, latest: str) -> DeliveryView:
    return DeliveryView(
        state,
        "ok",
        {
            "as_of": "2026-11-05",
            "freshness": {"latest_t0": latest, "reasons": [state]},
            "rows": [
                {
                    "action_state": "WAIT",
                    "source": "brain_a_scan_setup",
                    "symbol": symbol,
                    "t0_date": latest,
                    "t0_price": 1,
                }
            ],
        },
        1,
    )


def _symbols(frame: object) -> set[str]:
    if not isinstance(frame, list):
        return set()
    return {str(row.get("Symbol") or "") for row in frame if isinstance(row, dict)}


def test_valid_store_takes_precedence_over_accepted_remote_data(tmp_path: Path):
    directory = _store(tmp_path)
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=_remote(DATA_FRESH, "OLD", "2026-11-04"),
        row_store=directory,
    )
    text = "\n".join(fake.captions)
    assert "durable_row_store identities=1" in text
    assert "research_rows=1" in text
    assert f"row_horizons={HORIZON_STATUS}" in text
    assert "historical_remote_delivery state=DATA_FRESH historical_rows=1" in text
    assert "This is not the durable store population." in text
    assert _symbols(fake.frames[0]) == {"HPG"}
    assert _symbols(fake.frames[-1]) == {"OLD"}


def test_source_stale_remote_delivery_cannot_hide_the_durable_store(tmp_path: Path):
    directory = _store(tmp_path)
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=_remote(SOURCE_STALE, "OLD", "2026-11-04"),
        row_store=directory,
    )
    text = "\n".join(fake.captions)
    assert "durable_row_store identities=1" in text
    assert "research_rows=1" in text
    assert "freshness=UNVERIFIED" in text
    assert "latest T0 (provenance)=unknown" in text
    assert "historical_remote_delivery state=SOURCE_STALE historical_rows=1 latest T0 (provenance)=2026-11-04" in text
    assert "SOURCE_STALE: historical remote delivery is stale." in text
    assert _symbols(fake.frames[0]) == {"HPG"}
    assert "OLD" not in _symbols(fake.frames[0])
    assert _symbols(fake.frames[-1]) == {"OLD"}


def test_invalid_store_is_an_explicit_warning_and_historical_stays_labeled(tmp_path: Path):
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "manifest.json").write_text('{"schema":"not-the-store"}\n', encoding="utf-8")
    (directory / "identities.jsonl").write_text("{}\n", encoding="utf-8")
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=_remote(SOURCE_STALE, "OLD", "2026-11-04"),
        row_store=directory,
    )
    text = "\n".join(fake.captions)
    assert "DURABLE_STORE_INVALID:" in text
    assert "Historical remote data is not the current durable store." in text
    assert "durable_row_store identities=" not in text
    assert "research_rows=" not in text
    assert "historical_remote_delivery state=SOURCE_STALE historical_rows=1" in text
    assert _symbols(fake.frames[0]) == {"OLD"}


def test_committed_store_is_the_current_population():
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=_remote(SOURCE_STALE, "HISTORICAL", "2026-11-04"),
        row_store=STORE,
    )
    text = "\n".join(fake.captions)
    assert "durable_row_store identities=1339" in text
    assert "research_rows=1339" in text
    assert f"row_horizons={HORIZON_STATUS}" in text
    assert "historical_rows=1" in text
    assert "HISTORICAL" not in _symbols(fake.frames[0])
    assert _symbols(fake.frames[-1]) == {"HISTORICAL"}


def test_approximate_view_is_unchanged_by_panel_rendering(tmp_path: Path):
    before = BUNDLED_VIEW.read_bytes()
    render_v2_research_ledger_panel(
        _FakeStreamlit(),
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=_store(tmp_path),
    )
    assert BUNDLED_VIEW.read_bytes() == before
    view = read_view(BUNDLED_VIEW)
    assert view is not None
    assert view["records"] == 1055
    assert view["deduped_observations"] == 1024
    assert view["official_pnl"] is False


def test_panel_rendering_does_not_ingest(tmp_path: Path, monkeypatch):
    directory = _store(tmp_path)
    before = (directory / "identities.jsonl").read_bytes()
    links = (directory / "links.jsonl").read_bytes() if (directory / "links.jsonl").is_file() else b""

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("ingest_sources called")

    monkeypatch.setattr("research.v2_research_ledger.ingest_rows.ingest_sources", _forbidden)
    source = PANEL.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert "research.v2_research_ledger.ingest_rows" not in imported
    assert "ingest_sources" not in source
    render_v2_research_ledger_panel(
        _FakeStreamlit(),
        remote=True,
        remote_view=_remote(SOURCE_STALE, "OLD", "2026-11-04"),
        row_store=directory,
    )
    assert (directory / "identities.jsonl").read_bytes() == before
    if links:
        assert (directory / "links.jsonl").read_bytes() == links
    else:
        assert not (directory / "links.jsonl").is_file()

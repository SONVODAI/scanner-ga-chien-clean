"""The performance board displays the finished view and does not rescore rows."""

from __future__ import annotations

import json
from pathlib import Path

from modules.v2_research_ledger_panel.approximate_ui import render_approximate_performance_panel
from research.approximate_returns.view import BUNDLED_VIEW, project_view, read_view
from research.v2_research_ledger.remote_delivery import RemoteResponse, fetch_approximate_performance

ROOT = Path(__file__).resolve().parents[1]


def _cell(status: str = "APPROX_AVAILABLE", value: float = 4.0) -> dict:
    return {
        "status": status,
        "target_session": "2026-10-27",
        "reference_price": 110,
        "return_pct": value if status == "APPROX_AVAILABLE" else None,
        "included_in_primary": status == "APPROX_AVAILABLE",
    }


def _row(row_id: str, source: str, cohort: str) -> dict:
    horizons = {f"T+{step}": _cell() for step in (1, 3, 5, 10, 15, 20)}
    return {
        "row_id": row_id,
        "symbol": "HPG",
        "t0_date": "2026-10-26",
        "source": source,
        "comparison_cohort": cohort,
        "action_state": "WAIT",
        "lifecycle": "ACTIVE",
        "frozen_t0_price": 50,
        "t0_gap_pct": 100.0,
        "market_real": 6.0,
        "market_real_provenance": "nomination.market_real_at_nomination",
        "horizons": horizons,
    }


def _panel() -> dict:
    rows = [
        _row("b1", "brain_a_scan_setup", "overlap"),
        _row("s1", "market_aware_sweetspot", "overlap"),
    ]
    from research.approximate_returns.report import summarize

    return {
        "price_basis": "APPROX_LAST_5M_CLOSE",
        "source": "vnstock4_kbs",
        "as_of": "2026-11-05",
        "content_sha256": "abc",
        "official_pnl": False,
        "rows": rows,
        "summary": summarize(rows),
        "discontinuities": [{"symbol": "GMD", "session": "2026-10-07", "prior_session": "2026-10-06", "change_pct": -30.0}],
    }


class _Expander:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Fake:
    def __init__(self) -> None:
        self.captions: list[str] = []
        self.frames: list[object] = []
        self.warnings: list[str] = []
        self.title = ""

    def expander(self, title, expanded=False):
        self.title = title
        return _Expander()

    def caption(self, text):
        self.captions.append(str(text))

    def markdown(self, text):
        self.captions.append(str(text))

    def dataframe(self, frame, **_kwargs):
        self.frames.append(frame)

    def warning(self, text):
        self.warnings.append(str(text))


def test_view_keeps_overlap_as_one_sample_and_does_not_fill_missing_returns():
    view = project_view(_panel())
    assert view["official_pnl"] is False
    assert view["executed_buys"] is False
    assert view["records"] == 2
    assert view["deduped_observations"] == 1
    assert view["overall"]["horizons"]["T+5"]["primary"] == 1
    assert view["overall"]["horizons"]["T+5"]["average_return_pct"] == 4
    assert view["cohorts"]["overlap"]["observations"] == 1
    assert view["cohorts"]["brain_a"]["observations"] == 0
    assert view["t0_gaps"]["abs_gap_at_least_5pct"] == 2
    assert view["content_sha256"]


def test_panel_states_the_accounting_limits():
    fake = _Fake()
    render_approximate_performance_panel(fake, view=project_view(_panel()), remote=False)
    text = "\n".join(fake.captions)
    assert fake.title == "APPROXIMATE PERFORMANCE RESEARCH"
    assert "not execution P&L" in text
    assert "not executed buys" in text
    assert "No statistical significance" in text
    assert "Deduplicated symbol sessions=1" in text
    assert "Frozen rows=2" in text
    assert "Valid T+5 deduplicated sample=1" in text
    assert "Last confirmed trading session=2026-11-05" in text
    assert fake.warnings == []
    sources = fake.frames[0]
    overlap = sources[(sources["Source"] == "Overlap") & (sources["Horizon"] == "T+5")].iloc[0]
    brain = sources[(sources["Source"] == "Brain A") & (sources["Horizon"] == "T+5")].iloc[0]
    assert overlap["Sample"] == 1
    assert brain["Sample"] == 0
    assert "—" in set(brain[["Average", "Win >3%", "Loss rate"]])


def test_remote_view_is_rejected_when_the_hash_changes():
    view = project_view(_panel())
    body = (json.dumps(view, sort_keys=True) + "\n").encode("utf-8")
    tampered = body.replace(b"APPROX_LAST_5M_CLOSE", b"OFFICIAL_DAILY_CLOSE")

    def opener(url, headers, timeout):
        assert headers["Authorization"] == "Bearer ledger-token"
        assert url.endswith("/current/research_ledger/approximate_performance.json")
        return RemoteResponse(200, {}, tampered)

    assert fetch_approximate_performance("https://ledger.example", "ledger-token", opener=opener) is None


def test_bundled_research_view_matches_the_finished_panel():
    bundled = read_view(BUNDLED_VIEW)
    assert bundled is not None
    assert bundled["panel_sha256"] == "701201f4b5b9decd9f2ec1b9147b21bd56a6000edc9870c8f40c1272e52151e8"
    assert bundled["records"] == 1055
    assert bundled["deduped_observations"] == 1024
    assert bundled["overall"]["horizons"]["T+5"]["primary"] == 933
    assert bundled["cohorts"]["brain_a"]["horizons"]["T+5"]["primary"] == 729
    assert bundled["official_pnl"] is False
    assert bundled["executed_buys"] is False
    panel_path = ROOT / "data" / "approximate_returns" / "outcome_panel.json"
    if panel_path.is_file():
        panel = json.loads(panel_path.read_text(encoding="utf-8"))
        assert bundled["panel_sha256"] == panel["content_sha256"]

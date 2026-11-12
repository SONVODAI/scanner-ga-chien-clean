"""Durable V2 research row store. Fixtures only. No Guardian or action writes."""

from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from modules.v2_research_ledger_panel.ui import render_v2_research_ledger_panel
from research.approximate_returns.view import BUNDLED_VIEW, read_view
from research.v2_research_ledger.delivery_view import DELIVERY_UNAVAILABLE, DeliveryView
from research.v2_research_ledger.durable_store import CONFLICT, DurableRowStore, canonical_number
from research.v2_research_ledger.ingest_rows import ingest_sources
from research.v2_research_ledger.panel_board import HORIZON_STATUS, deduped_research_observations, load_row_panel

SIDECAR = ROOT / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
SWEET = ROOT / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"
STORE = ROOT / "research" / "v2_research_ledger" / "durable"
GUARDIAN_SESSION = ROOT / "data" / "guardian_research" / "sessions" / "2026-11-11.json"
GUARDIAN_OUTCOMES = ROOT / "research" / "guardian_research" / "outcomes.json"


def _sidecar(path: Path, freeze: list[dict], rows: list[dict] | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "freeze_ledger": freeze,
                "observed_at": "2026-11-12T10:26:13+07:00",
                "rows": rows or [],
                "session": "2026-11-12",
            }
        ),
        encoding="utf-8",
    )


def _freeze(symbol: str = "HPG", price: float = 27000.0, seen: str = "2026-11-06T19:00:00+07:00") -> dict:
    return {
        "breakout_ref_at_first_seen": price + 100,
        "candidate_first_seen_ts": seen,
        "ema9_at_first_seen": price - 10,
        "price_at_first_seen": price,
        "session": "2026-11-05",
        "symbol": symbol,
    }


def _sweet(path: Path, rows: list[str]) -> None:
    header = "observer_id,t0_date,symbol,observer_status,market_real_t0,price_t0,created_at,origin_setup\n"
    path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


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


def test_ingest_preserves_provenance_and_rejects_incomplete_rows(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    sweet = tmp_path / "sweet.csv"
    _sidecar(sidecar, [_freeze(), {"session": "2026-11-05", "symbol": "", "candidate_first_seen_ts": "x"}])
    _sweet(
        sweet,
        [
            "obs-1,2026-11-05,HPG,OBSERVE,7.5,27100,2026-11-05T12:00:00Z,MUA EARLY",
            "obs-2,2026-11-04,,NO_QUALIFIED_SWEETSPOT,4.0,,2026-11-04T12:00:00Z,",
        ],
    )
    store = DurableRowStore(tmp_path / "store")
    manifest = ingest_sources(store, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=tmp_path / "missing-evidence")
    identity = store.identities["sidecar|2026-11-05|HPG|2026-11-06T19:00:00+07:00"]
    assert identity["t0_date"] == "2026-11-05"
    assert identity["candidate_first_seen_ts"] == "2026-11-06T19:00:00+07:00"
    assert identity["t0_price"] == 27000
    assert identity["source_field"] is None
    assert identity["source_attribution"] == "brain_a_scan_setup"
    assert identity["decision"] == "DECISION_UNAVAILABLE"
    rejected = store.identities["sweet|obs-2"]
    assert rejected["symbol"] == ""
    assert rejected["decision"] == "REJECTED"
    assert rejected["decision_detail"] == "NO_QUALIFIED_SWEETSPOT"
    assert manifest["action_evidence"]["status"] == "MISSING"
    assert manifest["historical_row_panel"]["status"] == "UNAVAILABLE"
    assert manifest["t_plus_recomputed"] is False
    assert "return_pct" not in identity


def test_second_ingest_is_idempotent_and_t0_price_cannot_change(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    sweet = tmp_path / "sweet.csv"
    _sidecar(sidecar, [_freeze()])
    _sweet(sweet, ["obs-1,2026-11-05,HPG,OBSERVE,7.5,27100,2026-11-05T12:00:00Z,MUA EARLY"])
    directory = tmp_path / "store"
    first = DurableRowStore(directory)
    ingest_sources(first, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    before = (directory / "identities.jsonl").read_bytes()
    again = DurableRowStore(directory)
    ingest_sources(again, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    assert (directory / "identities.jsonl").read_bytes() == before
    assert again.identities["sweet|obs-1"]["t0_price"] == 27100
    _sweet(sweet, ["obs-1,2026-11-05,HPG,OBSERVE,7.5,99999,2026-11-05T12:00:00Z,MUA EARLY"])
    third = DurableRowStore(directory)
    result = third.put_identity(
        {
            **third.identities["sweet|obs-1"],
            "decision": "ACCEPTED",
            "market_real": 7.5,
            "observer_status": "OBSERVE",
            "source_attribution": "market_aware_sweetspot",
            "t0_price": 99999,
        }
    )
    assert result == CONFLICT
    reloaded = DurableRowStore(directory)
    assert reloaded.identities["sweet|obs-1"]["t0_price"] == 27100
    assert reloaded.identities["sweet|obs-1"]["sealed"]["t0_date"] == "2026-11-05"
    assert len(reloaded.conflicts) == 1


def test_store_reloads_after_a_new_process_object(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    _sidecar(sidecar, [_freeze(seen="2026-11-06T19:00:00+07:00")])
    directory = tmp_path / "store"
    ingest_sources(DurableRowStore(directory), sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    reloaded = DurableRowStore(directory)
    assert len(reloaded.identities) == 1
    assert reloaded.identities["sidecar|2026-11-05|HPG|2026-11-06T19:00:00+07:00"]["ema9_at_first_seen"] == 26990
    assert reloaded.read_manifest()["identity_count"] == 1


def test_dedup_keeps_sidecar_identities_separate_from_research_observations(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    sweet = tmp_path / "sweet.csv"
    row = {
        "candidate_first_seen_ts": "2026-11-06T19:00:00+07:00",
        "price_at_first_seen": 27000.0,
        "session": "2026-11-05",
        "setup": "MUA EARLY",
        "source": "brain_a_scan_setup",
        "status": "NOMINATED",
        "symbol": "HPG",
    }
    _sidecar(sidecar, [_freeze(), _freeze(symbol="SSI", price=30000.0)], [row])
    _sweet(
        sweet,
        [
            "obs-1,2026-11-05,HPG,OBSERVE,7.5,27100,2026-11-05T12:00:00Z,MUA EARLY",
            "obs-2,2026-11-05,HPG,OBSERVE,7.5,27100,2026-11-05T13:00:00Z,MUA EARLY",
            "obs-3,2026-11-05,SSI,NO_QUALIFIED_SWEETSPOT,4.0,30000,2026-11-05T12:00:00Z,",
        ],
    )
    store = DurableRowStore(tmp_path / "store")
    ingest_sources(store, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    assert len(store.identities) == 5
    assert len(store.links) == 1
    deduped = deduped_research_observations(store)
    assert ("market_aware_sweetspot", "HPG", "2026-11-05") in deduped
    assert deduped[("market_aware_sweetspot", "HPG", "2026-11-05")]["duplicate_identity_ids"] == ["sweet|obs-2"]
    assert ("brain_a_scan_setup", "HPG", "2026-11-05") in deduped
    assert ("brain_a_scan_setup", "SSI", "2026-11-05") not in deduped
    assert store.identities["sidecar|2026-11-05|SSI|2026-11-06T19:00:00+07:00"]["record_role"] == "sidecar_identity"


def test_conflicting_decisions_stay_stored_and_are_marked(tmp_path: Path):
    sweet = tmp_path / "sweet.csv"
    _sweet(
        sweet,
        [
            "obs-1,2026-11-05,HPG,OBSERVE,7.5,27100,2026-11-05T12:00:00Z,MUA EARLY",
            "obs-2,2026-11-05,HPG,NO_QUALIFIED_SWEETSPOT,7.5,27100,2026-11-05T13:00:00Z,",
        ],
    )
    store = DurableRowStore(tmp_path / "store")
    ingest_sources(store, sidecar_path=None, sweet_csv=sweet, evidence_dir=None)
    deduped = deduped_research_observations(store)
    assert deduped[("market_aware_sweetspot", "HPG", "2026-11-05")]["decision"] == "STATE_CONFLICT"
    assert {row["decision"] for row in store.identities.values()} == {"ACCEPTED", "REJECTED"}


def test_missing_sources_do_not_invent_rows(tmp_path: Path):
    store = DurableRowStore(tmp_path / "store")
    manifest = ingest_sources(store, sidecar_path=tmp_path / "absent.json", sweet_csv=None, evidence_dir=None)
    assert store.identities == {}
    assert manifest["sidecar"]["status"] == "MISSING"
    assert manifest["sweetspot"]["status"] == "MISSING"
    assert load_row_panel(store)["rows"] == []
    assert load_row_panel(DurableRowStore(tmp_path / "never-created")) is None


def test_panel_reads_the_store_and_does_not_show_a_stale_board(tmp_path: Path):
    sidecar = tmp_path / "camera_sidecar.json"
    _sidecar(sidecar, [_freeze()])
    directory = tmp_path / "store"
    ingest_sources(DurableRowStore(directory), sidecar_path=sidecar, sweet_csv=None, evidence_dir=None)
    stale = tmp_path / "stale-board.json"
    stale.write_text(json.dumps({"rows": [{"symbol": "STALE", "t0_date": "1999-01-01", "t0_price": 1}]}), encoding="utf-8")
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=directory,
        cache_path=stale,
    )
    text = "\n".join(fake.captions)
    assert "ROW_STORE_UNAVAILABLE" not in text
    assert "durable_row_store" in text
    assert "historical_row_panel=UNAVAILABLE" in text
    assert HORIZON_STATUS in text
    assert "cache_status=STALE" not in text
    assert "STALE" not in text
    rendered = json.dumps([str(frame) for frame in fake.frames])
    assert "STALE" not in rendered
    assert "1999-01-01" not in rendered
    panel = load_row_panel(DurableRowStore(directory))
    assert panel is not None
    assert panel["rows"][0]["horizons"]["T+20"] == {"return_pct": None, "status": HORIZON_STATUS}
    assert panel["t_plus_recomputed"] is False


def test_absent_store_is_explicit_when_remote_delivery_is_down(tmp_path: Path):
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=tmp_path / "missing-store",
        cache_path=tmp_path / "stale.json",
    )
    text = "\n".join(fake.captions)
    assert "ROW_STORE_UNAVAILABLE" in text
    assert "missing_secret" in text
    assert fake.frames == []


def test_modules_do_not_import_guardian_finalize_or_action_execution():
    banned = ("research.guardian_research", "modules.post_close_finalize", "modules.live_candidate_v2_action")
    for relative in (
        "research/v2_research_ledger/durable_store.py",
        "research/v2_research_ledger/ingest_rows.py",
        "research/v2_research_ledger/panel_board.py",
        "modules/v2_research_ledger_panel/ui.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(name == item or name.startswith(item + ".") for name in imported for item in banned)
    contract = (ROOT / "modules/live_candidate_v2_action/contract.py").read_text(encoding="utf-8")
    assert "CANDIDATE_IS_BUY = False" in contract
    assert "PXV_IMPLIES_BUY = False" in contract
    assert "ALERT_ELIGIBLE = False" in contract
    assert "EXECUTION_ENABLED = False" in contract


def test_shipped_store_preserves_repository_sources_and_survives_reload():
    guardian_session = GUARDIAN_SESSION.read_bytes()
    guardian_outcomes = GUARDIAN_OUTCOMES.read_bytes()
    approximate = read_view(BUNDLED_VIEW)
    assert approximate is not None
    assert approximate["records"] == 1055
    assert approximate["deduped_observations"] == 1024
    assert approximate["official_pnl"] is False
    assert set(approximate["coverage"]["horizons"]) == {"T+1", "T+3", "T+5", "T+10", "T+15", "T+20"}
    first = DurableRowStore(STORE)
    second = DurableRowStore(STORE)
    assert first.read_manifest()["t_plus_recomputed"] is False
    assert first.read_manifest()["historical_row_panel"]["status"] == "UNAVAILABLE"
    assert len(second.identities) == len(first.identities) > 0
    sidecar = json.loads(SIDECAR.read_text(encoding="utf-8"))
    for raw in sidecar["freeze_ledger"]:
        ident = f"sidecar|{raw['session'][:10]}|{raw['symbol']}|{raw['candidate_first_seen_ts']}"
        stored = second.identities[ident]
        assert stored["t0_price"] == int(raw["price_at_first_seen"])
        assert stored["candidate_first_seen_ts"] == raw["candidate_first_seen_ts"]
        assert stored["t0_date"] == raw["session"][:10]
        assert "T+1" not in stored
    linked = 0
    for raw in sidecar["rows"]:
        ident = f"sidecar|{str(raw['session'])[:10]}|{raw['symbol']}|{raw['candidate_first_seen_ts']}"
        assert ident in second.identities
        link = second.links[f"nomination|{ident}"]
        assert link["status"] == raw["status"]
        assert link["source_field"] == raw["source"]
        assert second.identities[ident]["t0_price"] == int(raw["price_at_first_seen"])
        linked += 1
    assert linked == len(sidecar["rows"])
    with SWEET.open(encoding="utf-8", newline="") as handle:
        sweet_rows = list(csv.DictReader(handle))
    assert sweet_rows
    for raw in sweet_rows:
        stored = second.identities[f"sweet|{raw['observer_id']}"]
        assert stored["created_at"] == raw["created_at"]
        assert stored["t0_date"] == raw["t0_date"][:10]
        assert stored["symbol"] == str(raw["symbol"] or "").strip().upper()
        assert stored["t0_price"] == canonical_number(raw["price_t0"])
        assert stored["market_real"] == canonical_number(raw["market_real_t0"])
        if raw["observer_status"] == "OBSERVE":
            assert stored["decision"] == "ACCEPTED"
        elif raw["observer_status"]:
            assert stored["decision"] == "REJECTED"
            assert stored["decision_detail"] == raw["observer_status"]
        assert "T+1" not in stored
    assert GUARDIAN_SESSION.read_bytes() == guardian_session
    assert GUARDIAN_OUTCOMES.read_bytes() == guardian_outcomes

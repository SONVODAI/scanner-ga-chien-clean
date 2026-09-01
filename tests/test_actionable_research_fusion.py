"""Acceptance tests for Actionable Research Fusion (RESEARCH ONLY)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from modules.actionable_research.contracts import (
    AUTHORITY_LABEL,
    CAMERA_DATA_FEED_MISSING,
    EDGE_STATUS_ACTIVE_MATCH,
    EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE,
    FOREIGN_STRONG_BUY,
    FOREIGN_STRONG_SELL,
    INTRADAY_ACTIVITY_HIGH,
    INTRADAY_ACTIVITY_UNKNOWN,
    NO_INTEREST_VI,
    OBSERVATION_CONFLICT,
    PRICE_DIRECTION_DOWN,
    SESSION_ELIGIBLE,
    SESSION_SKIPPED_NON_TRADING,
    SKIPPED_NON_TRADING_VI,
    TRADING_VALUE_UNUSUALLY_HIGH,
    UNABLE_VI,
)
from modules.actionable_research.engine import fuse_session
from modules.actionable_research.foreign import CAMERA_HAS_INTRADAY_FOREIGN
from modules.actionable_research.paths import FusionPaths
from modules.actionable_research.production_hook import run_actionable_research_after_daily
from modules.intraday_memory.config import IntradayConfig
from modules.intraday_memory.schema import CanonicalBar
from modules.intraday_memory.storage import upsert_session
from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_memory.universe import load_production_universe

REPO = Path(__file__).resolve().parents[1]
TRADE_DATE = "2026-08-14"  # Friday
WEEKEND = "2026-08-15"  # Saturday
UNIVERSE = load_production_universe(REPO / "app.py")


@pytest.fixture
def fusion_paths(tmp_path) -> FusionPaths:
    el = tmp_path / "earning_learning"
    el.mkdir()
    edge = tmp_path / "edge_research"
    edge.mkdir()
    camera = tmp_path / "intraday_memory"
    camera.mkdir()
    foreign = tmp_path / "foreign_flow_history"
    (foreign / "canonical" / "by_symbol").mkdir(parents=True)
    artifacts = tmp_path / "actionable_research"
    return FusionPaths(
        repo_root=REPO,
        artifact_root=artifacts,
        earning_learning_dir=el,
        edge_data_dir=edge,
        camera_root=camera,
        foreign_history_root=foreign,
        app_py_path=REPO / "app.py",
    )


def _write_freeze(paths: FusionPaths, trade_date: str, symbols=UNIVERSE) -> None:
    rows = []
    for i, sym in enumerate(symbols):
        rows.append(
            {
                "trade_date": trade_date,
                "symbol": sym,
                "health_group": "TRUNG TINH",
                "group": "THEO DOI",
                "pattern_key_v2_frozen": "CTX::DNA",
                "stock_pattern_key": "DNA",
                "rs5": 1.0 + i * 0.01,
                "rs10": 0.5,
                "rsi14": 50.0,
                "rs_spread": 0.5,
                "volume_ratio": 1.0,
                "price": 10000 + i,
            }
        )
    pd.DataFrame(rows).to_csv(paths.t0_freeze_path(), index=False)


def _write_market(paths: FusionPaths, trade_date: str, market_real: float = 5.0) -> None:
    pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "entity": "MARKET",
                "market_real": market_real,
                "market_forecast": 5.0,
                "breadth_score": 40.0,
                "session_slot": "AFTER_CLOSE",
            }
        ]
    ).to_csv(paths.market_daily_t0_path(), index=False)


def _bar(symbol: str, ts: datetime, close: int = 20000, volume: int = 1000, open_: int | None = None) -> CanonicalBar:
    o = close if open_ is None else open_
    return CanonicalBar(
        symbol=symbol,
        timestamp=ts,
        session_date=ts.date(),
        open=o,
        high=max(o, close),
        low=min(o, close),
        close=close,
        volume=volume,
    )


def _write_camera(
    paths: FusionPaths,
    trade_date: str,
    volumes: dict[str, int] | None = None,
    *,
    extra_late: dict[str, int] | None = None,
    hour: int = 10,
    closes: dict[str, int] | None = None,
    opens: dict[str, int] | None = None,
) -> None:
    d = date.fromisoformat(trade_date)
    ts = datetime(d.year, d.month, d.day, hour, 0, tzinfo=VN_TZ)
    bars = []
    volumes = volumes or {}
    closes = closes or {}
    opens = opens or {}
    for sym in UNIVERSE:
        close = int(closes.get(sym, 20000))
        open_ = int(opens.get(sym, close))
        bars.append(_bar(sym, ts, close=close, volume=int(volumes.get(sym, 1_000)), open_=open_))
    if extra_late:
        late = datetime(d.year, d.month, d.day, 14, 0, tzinfo=VN_TZ)
        for sym, vol in extra_late.items():
            bars.append(_bar(sym, late, volume=int(vol)))
    upsert_session(paths.camera_data_root(), d, bars)


def _write_edge_memory(paths: FusionPaths, rows: list[dict] | None = None) -> Path:
    path = paths.edge_memory_path()
    if rows is None:
        pd.DataFrame(columns=["edge_id", "hypothesis_id", "status"]).to_csv(path, index=False)
    else:
        pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_recognition(paths: FusionPaths, trade_date: str, matches: list[dict]) -> None:
    daily = paths.daily_edge_matches_path(trade_date)
    daily.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trade_date": trade_date,
        "assessment_state": "QUALIFIED_MATCH_FOUND" if matches else "NO_QUALIFIED_MATCH",
        "matches": matches,
    }
    daily.write_text(json.dumps(payload), encoding="utf-8")


def _write_foreign(paths: FusionPaths, trade_date: str, nets: dict[str, float]) -> None:
    rows = []
    for sym in UNIVERSE:
        net = float(nets.get(sym, 0.0))
        buy = max(net, 0.0) + 1.0
        sell = buy - net
        rows.append(
            {
                "trade_date": trade_date,
                "symbol": sym,
                "foreign_buy_value": buy,
                "foreign_sell_value": sell,
                "foreign_net_value": net,
                "source": "HSX_FOREIGN_API",
            }
        )
    out = paths.foreign_root() / "canonical" / f"{trade_date}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)


def _by_symbol(payload: dict, symbol: str) -> dict:
    rows = payload.get("observations") or payload.get("records") or []
    for rec in rows:
        if rec.get("symbol") == symbol:
            return rec
    raise AssertionError(f"missing {symbol}")


def test_camera_has_no_intraday_foreign_fields():
    assert CAMERA_HAS_INTRADAY_FOREIGN is False
    from modules.intraday_memory.schema import CANONICAL_COLUMNS

    assert "foreign_buy_value" not in CANONICAL_COLUMNS
    assert "foreign_net_value" not in CANONICAL_COLUMNS


def test_1_142_stock_eligible_session(fusion_paths):
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_market(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    payload = fuse_session(TRADE_DATE, paths=fusion_paths, persist=True)
    assert payload["session_status"] == SESSION_ELIGIBLE
    assert payload["universe_count"] == 142
    assert payload["scan"]["scanned_count"] == 142
    assert payload["notable_count"] == 0
    assert payload["observations"] == []
    assert payload["records"] == []
    assert payload["headline_vi"] == NO_INTEREST_VI
    assert payload["speak_policy"] == "SCAN_BROADLY_SPEAK_SELECTIVELY"
    assert payload["authority"] == AUTHORITY_LABEL
    assert payload["research_label"] == AUTHORITY_LABEL
    assert fusion_paths.daily_path(TRADE_DATE).exists()
    assert fusion_paths.latest_path().exists()


def test_2_zero_active_one_strong_money_flow_still_surfaced(fusion_paths):
    strong = UNIVERSE[0]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[strong] = 50_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, strong)
    assert rec["edge_status"] == EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE
    assert rec["activity_status"] == INTRADAY_ACTIVITY_HIGH
    assert rec["trading_value_status"] == TRADING_VALUE_UNUSUALLY_HIGH
    assert rec["notable"] is True
    assert strong in payload["surfaced_symbols"]
    assert payload["notable_count"] >= 1
    assert payload["scan"]["scanned_count"] == 142
    assert len(payload["observations"]) == payload["notable_count"]
    assert len(payload["observations"]) < 142
    assert "NO_OPPORTUNITY" not in json.dumps(payload)
    assert "Không có ACTIVE edge" in rec["evidence_summary"]
    assert "Hoạt động giao dịch intraday cao bất thường" in rec["evidence_summary"]
    assert "dòng tiền vào mạnh" not in rec["evidence_summary"].lower()
    assert "tiền vào mạnh" not in rec["evidence_summary"].lower()


def test_3_active_edge_missing_camera_stays_visible_unknown(fusion_paths):
    matched = UNIVERSE[1]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(
        fusion_paths,
        [{"edge_id": "E1", "hypothesis_id": "H1", "status": "ACTIVE", "best_horizon": "T5"}],
    )
    _write_recognition(
        fusion_paths,
        TRADE_DATE,
        [{"symbol": matched, "edge_id": "E1", "best_horizon": "T5", "edge_context_verdict": "CONTEXT_COMPATIBLE"}],
    )
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, matched)
    assert rec["edge_status"] == EDGE_STATUS_ACTIVE_MATCH
    assert rec["activity_status"] == INTRADAY_ACTIVITY_UNKNOWN
    assert rec["camera_data_status"] == CAMERA_DATA_FEED_MISSING
    assert rec["notable"] is True
    assert "UNKNOWN" == rec["activity_status"]
    assert rec["activity_status"] not in {"INTRADAY_ACTIVITY_NORMAL", "INTRADAY_ACTIVITY_LOW"}
    assert "khớp ACTIVE edge" in rec["evidence_summary"]


def test_4_active_edge_and_strong_money_flow_both_shown(fusion_paths):
    matched = UNIVERSE[2]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(
        fusion_paths,
        [{"edge_id": "E1", "hypothesis_id": "H1", "status": "ACTIVE", "best_horizon": "T3"}],
    )
    _write_recognition(
        fusion_paths,
        TRADE_DATE,
        [{"symbol": matched, "edge_id": "E1", "best_horizon": "T3"}],
    )
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[matched] = 80_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, matched)
    assert rec["edge_status"] == EDGE_STATUS_ACTIVE_MATCH
    assert rec["activity_status"] == INTRADAY_ACTIVITY_HIGH
    assert rec["research_label"] == AUTHORITY_LABEL
    assert "ACTIVE edge" in rec["evidence_summary"]
    assert "Hoạt động giao dịch" in rec["evidence_summary"]
    assert "dòng tiền vào mạnh" not in rec["evidence_summary"].lower()


def test_5_strong_flow_and_foreign_without_active_edge(fusion_paths):
    hot = UNIVERSE[3]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[hot] = 90_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    nets = {sym: 1.0 for sym in UNIVERSE}
    nets[hot] = 9_999_999.0
    _write_foreign(fusion_paths, TRADE_DATE, nets)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, hot)
    assert rec["edge_status"] == EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE
    assert rec["activity_status"] == INTRADAY_ACTIVITY_HIGH
    assert rec["foreign_flow_status"] == FOREIGN_STRONG_BUY
    assert rec["foreign_timing"] == "EOD"
    assert rec["interest_level"] == "HIGH"
    assert rec["research_label"] == AUTHORITY_LABEL
    assert hot == payload["surfaced_symbols"][0]
    assert "NO_ACTIVE_EDGE" in json.dumps(rec["reasons"])


def test_6_triple_evidence_strongest_still_research_only(fusion_paths):
    hot = UNIVERSE[4]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(
        fusion_paths,
        [{"edge_id": "E9", "hypothesis_id": "H9", "status": "ACTIVE", "best_horizon": "T10"}],
    )
    _write_recognition(fusion_paths, TRADE_DATE, [{"symbol": hot, "edge_id": "E9", "best_horizon": "T10"}])
    volumes = {sym: 800 for sym in UNIVERSE}
    volumes[hot] = 70_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    nets = {sym: -1.0 for sym in UNIVERSE}
    nets[hot] = 8_888_888.0
    _write_foreign(fusion_paths, TRADE_DATE, nets)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, hot)
    assert rec["edge_status"] == EDGE_STATUS_ACTIVE_MATCH
    assert rec["activity_status"] == INTRADAY_ACTIVITY_HIGH
    assert rec["foreign_flow_status"] == FOREIGN_STRONG_BUY
    assert rec["presentation_rank"] == 0
    assert rec["research_label"] == AUTHORITY_LABEL
    assert payload["research_label"] == AUTHORITY_LABEL
    assert rec["evidence_summary"].startswith("Cổ phiếu khớp ACTIVE edge")
    assert payload["authority"] == "RESEARCH ONLY"
    assert rec["research_label"] == "RESEARCH ONLY"
    assert rec.get("trading_decision") is None


def test_7_no_notable_evidence_truthful_empty(fusion_paths):
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    nets = {sym: 0.0 for sym in UNIVERSE}
    _write_foreign(fusion_paths, TRADE_DATE, nets)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    assert payload["notable_count"] == 0
    assert payload["surfaced_symbols"] == []
    assert payload["headline_vi"] == NO_INTEREST_VI
    assert payload["scan"]["scanned_count"] == 142
    assert payload["observations"] == []
    assert payload["records"] == []


def test_8_missing_camera_feed_is_unknown_not_normal(fusion_paths):
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    assert payload["observations"] == []
    assert payload["scan"]["scanned_count"] == 142
    assert payload["scan"]["camera_unknown_count"] == 142
    assert payload["camera"]["feed_status"] == CAMERA_DATA_FEED_MISSING
    assert payload["headline_vi"] == NO_INTEREST_VI


def test_9_missing_foreign_is_unknown_not_zero(fusion_paths):
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    assert payload["observations"] == []
    assert payload["scan"]["scanned_count"] == 142
    assert payload["scan"]["foreign_unknown_count"] == 142
    assert payload["foreign"]["completeness"] == "UNAVAILABLE"
    assert payload["foreign"]["available"] is False


def test_10_non_trading_day_skipped_no_scientific_records(fusion_paths):
    payload = fuse_session(
        WEEKEND,
        paths=fusion_paths,
        daily_result={"run_disposition": "SKIPPED_NON_TRADING_DAY"},
    )
    assert payload["session_status"] == SESSION_SKIPPED_NON_TRADING
    assert payload["records"] == []
    assert payload["scientific_writes"] == []
    assert payload["headline_vi"] == SKIPPED_NON_TRADING_VI
    assert payload["headline_vi"] != NO_INTEREST_VI
    weekend_natural = fuse_session(WEEKEND, paths=fusion_paths)
    assert weekend_natural["session_status"] == SESSION_SKIPPED_NON_TRADING
    assert weekend_natural["records"] == []
    assert weekend_natural["headline_vi"] != NO_INTEREST_VI
    ledger = fusion_paths.observation_ledger_path()
    if ledger.exists():
        lines = [ln for ln in ledger.read_text().splitlines() if ln.strip()]
        assert lines == []


def test_11_same_date_replay_no_duplicate_records(fusion_paths):
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    first = fuse_session(TRADE_DATE, paths=fusion_paths)
    second = fuse_session(TRADE_DATE, paths=fusion_paths)
    assert second["idempotent_replay"] is True
    assert second["scan"]["scanned_count"] == first["scan"]["scanned_count"] == 142
    assert second["record_count"] == first["record_count"] == 0
    index = json.loads(fusion_paths.index_path().read_text())
    assert list(index["runs"].keys()) == [TRADE_DATE]
    daily = json.loads(fusion_paths.daily_path(TRADE_DATE).read_text())
    assert daily["observations"] == []
    ledger = fusion_paths.observation_ledger_path()
    if ledger.exists():
        lines = [ln for ln in ledger.read_text().splitlines() if ln.strip()]
        assert len(lines) == 0


def test_12_pit_cutoff_drops_future_bars(fusion_paths):
    hot = UNIVERSE[5]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    extra_late = {hot: 500_000_000}
    _write_camera(fusion_paths, TRADE_DATE, volumes, extra_late=extra_late, hour=10)
    d = date.fromisoformat(TRADE_DATE)
    cutoff = datetime(d.year, d.month, d.day, 11, 0, tzinfo=VN_TZ)
    from modules.actionable_research.camera import classify_money_flow

    classified = classify_money_flow(TRADE_DATE, UNIVERSE, paths=fusion_paths, cutoff=cutoff)
    metrics = (classified["by_symbol"][hot].get("metrics") or {})
    assert metrics.get("session_volume") == 1_000
    payload = fuse_session(TRADE_DATE, paths=fusion_paths, cutoff=cutoff)
    assert payload["camera"]["look_ahead_bars_dropped"] >= 1
    assert payload["camera"]["cutoff"].startswith("2026-08-14T11:00:00")


def test_13_does_not_mutate_scientific_edge_stores(fusion_paths):
    memory_path = _write_edge_memory(
        fusion_paths,
        [{"edge_id": "E1", "hypothesis_id": "H1", "status": "ACTIVE", "best_horizon": "T5"}],
    )
    before = hashlib.sha256(memory_path.read_bytes()).hexdigest()
    ledger = fusion_paths.edge_root() / "edge_forward_ledger.csv"
    _write_freeze(fusion_paths, TRADE_DATE)
    fuse_session(TRADE_DATE, paths=fusion_paths)
    after = hashlib.sha256(memory_path.read_bytes()).hexdigest()
    assert before == after
    assert not ledger.exists()
    payload = json.loads(fusion_paths.daily_path(TRADE_DATE).read_text())
    assert payload["scientific_writes"] == []


def test_14_camera_runner_failure_does_not_break_collect(tmp_path):
    from modules.intraday_memory.runner import EXIT_SUCCESS, run_scheduled_collect

    config = IntradayConfig(data_root=tmp_path / "cam")
    mock_manifest = type("M", (), {})()
    mock_manifest.symbols_failed = {}
    mock_manifest.final_status = "SUCCESS"
    mock_manifest.summary_text = lambda: "ok"

    with patch(
        "modules.intraday_memory.runner.resolve_collect_session_date",
        return_value=(date(2026, 8, 14), None),
    ), patch(
        "modules.intraday_memory.runner.IntradayCollector"
    ) as collector_cls, patch(
        "modules.actionable_research.production_hook.maybe_run_fusion_after_camera",
        side_effect=RuntimeError("fusion boom"),
    ):
        collector_cls.return_value.collect_session.return_value = mock_manifest
        code = run_scheduled_collect(config)
    assert code == EXIT_SUCCESS


def test_production_hook_nested_payload_does_not_change_disposition(fusion_paths):
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    daily = {"run": {"run_disposition": "SUCCESS", "run_id": "r1"}}
    nested = run_actionable_research_after_daily(
        target_trade_date=TRADE_DATE,
        daily_result=daily,
        repo_root=REPO,
        data_dir=fusion_paths.edge_root(),
        camera_root=fusion_paths.camera_data_root(),
        artifact_root=fusion_paths.artifacts(),
    )
    assert nested["ran_fusion"] is True
    assert daily["run"]["run_disposition"] == "SUCCESS"
    assert nested["scientific_writes"] == []


def test_ui_loader_is_read_only(fusion_paths):
    from modules.actionable_research.ui import load_latest_fusion_view

    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    fuse_session(TRADE_DATE, paths=fusion_paths)
    view = load_latest_fusion_view(paths=fusion_paths)
    assert view["available"] is True
    assert view["authority"] == AUTHORITY_LABEL
    assert view["scanned_count"] == 142
    assert view["observations"] == []
    assert view["headline_vi"] == NO_INTEREST_VI


def test_speak_selectively_does_not_dump_universe(fusion_paths):
    strong = UNIVERSE[0]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[strong] = 50_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    daily = json.loads(fusion_paths.daily_path(TRADE_DATE).read_text())
    latest = json.loads(fusion_paths.latest_path().read_text())
    spoken = daily["observations"]
    assert payload["scan"]["scanned_count"] == 142
    assert 1 <= len(spoken) < 20
    assert all(r.get("notable") for r in spoken)
    artifact_records = (latest.get("artifact") or {}).get("records") or []
    assert len(artifact_records) == len(spoken)


def test_strong_foreign_sell_is_noteworthy_not_bullish_only(fusion_paths):
    hot = UNIVERSE[6]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    nets = {sym: 1.0 for sym in UNIVERSE}
    nets[hot] = -9_999_999.0
    _write_foreign(fusion_paths, TRADE_DATE, nets)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, hot)
    assert rec["foreign_flow_status"] == FOREIGN_STRONG_SELL
    assert rec["notable"] is True
    assert rec["research_label"] == AUTHORITY_LABEL
    assert "bán mạnh" in rec["evidence_summary"]


def test_abnormal_activity_during_price_decline_is_not_money_inflow(fusion_paths):
    hot = UNIVERSE[7]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[hot] = 80_000_000
    opens = {hot: 22000}
    closes = {hot: 18000}
    _write_camera(fusion_paths, TRADE_DATE, volumes, opens=opens, closes=closes)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, hot)
    assert rec["activity_status"] == INTRADAY_ACTIVITY_HIGH
    assert rec["price_direction"] == PRICE_DIRECTION_DOWN
    assert rec["notable"] is True
    assert rec.get("money_flow_status") not in {
        "MONEY_FLOW_STRONG",
        "MONEY_INFLOW_STRONG",
        "MONEY_OUTFLOW_STRONG",
    }
    assert rec.get("money_flow_direction") not in {"INFLOW", "OUTFLOW"}
    summary = rec["evidence_summary"].lower()
    assert "dòng tiền vào mạnh" not in summary
    assert "tiền vào mạnh" not in summary
    assert "hoạt động giao dịch" in summary
    assert "giá giảm" in summary
    assert "ACTIVITY_IS_NOT_MONEY_INFLOW" in rec["reasons"]
    assert rec["research_label"] == AUTHORITY_LABEL


def test_conflict_active_vs_foreign_sell_is_spoken(fusion_paths):
    hot = UNIVERSE[8]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(
        fusion_paths,
        [{"edge_id": "E2", "hypothesis_id": "H2", "status": "ACTIVE", "best_horizon": "T5"}],
    )
    _write_recognition(fusion_paths, TRADE_DATE, [{"symbol": hot, "edge_id": "E2", "best_horizon": "T5"}])
    nets = {sym: 1.0 for sym in UNIVERSE}
    nets[hot] = -8_888_888.0
    _write_foreign(fusion_paths, TRADE_DATE, nets)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    rec = _by_symbol(payload, hot)
    assert rec["edge_status"] == EDGE_STATUS_ACTIVE_MATCH
    assert rec["foreign_flow_status"] == FOREIGN_STRONG_SELL
    assert rec["observation_relation"] == OBSERVATION_CONFLICT
    assert rec["notable"] is True
    assert rec["evidence_summary"].startswith("Xung đột bằng chứng")


def test_legacy_sweetspot_alone_is_not_spoken(fusion_paths):
    hot = UNIVERSE[9]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    pd.DataFrame(
        [
            {
                "trade_date": TRADE_DATE,
                "symbol": hot,
                "matched_sweetspot": "RS5=5-10 RSI=50-55",
                "sweetspot_horizon": "T5",
            }
        ]
    ).to_csv(fusion_paths.sweetspot_observer_ledger_path(), index=False)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    assert payload["notable_count"] == 0
    assert payload["observations"] == []
    assert payload["headline_vi"] == NO_INTEREST_VI


def test_observation_ledger_first_write_wins(fusion_paths):
    strong = UNIVERSE[0]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[strong] = 50_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    fuse_session(TRADE_DATE, paths=fusion_paths)
    fuse_session(TRADE_DATE, paths=fusion_paths)
    ledger = fusion_paths.observation_ledger_path()
    lines = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    row = lines[0]
    assert row["symbol"] == strong
    assert row["outcome_status"] == "PENDING"
    assert row["t3_return_pct"] is None
    assert row["t5_return_pct"] is None
    assert row["t10_return_pct"] is None
    assert row["authority"] == "RESEARCH ONLY"
    assert row["activity_status"] == INTRADAY_ACTIVITY_HIGH
    assert row["maturity_basis"] == "vn_trading_sessions"


def _append_freeze_prices(paths: FusionPaths, extra_rows: list[dict]) -> None:
    existing = pd.read_csv(paths.t0_freeze_path())
    pd.concat([existing, pd.DataFrame(extra_rows)], ignore_index=True).to_csv(
        paths.t0_freeze_path(), index=False
    )


def test_national_day_creates_no_observation_or_maturity(fusion_paths):
    """N. Non-trading holiday must not birth T0 or advance T3/T5/T10."""
    from modules.actionable_research.observation_maturity import load_observation_ledger, target_session_for_horizon

    strong = UNIVERSE[0]
    t0 = TRADE_DATE
    holiday = "2026-09-02"
    _write_freeze(fusion_paths, t0)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[strong] = 50_000_000
    _write_camera(fusion_paths, t0, volumes)
    born = fuse_session(t0, paths=fusion_paths)
    assert born["observation_births"] == 1
    before = load_observation_ledger(fusion_paths)
    assert before[0]["t3_return_pct"] is None

    holiday_run = fuse_session(holiday, paths=fusion_paths)
    assert holiday_run["session_status"] == SESSION_SKIPPED_NON_TRADING
    assert holiday_run["observations"] == []
    assert holiday_run["headline_vi"] != NO_INTEREST_VI
    after = load_observation_ledger(fusion_paths)
    assert len(after) == 1
    assert after[0]["t3_return_pct"] is None
    assert after[0]["outcome_status"] == "PENDING"
    assert holiday_run["observation_maturity"]["skipped"] is True
    assert target_session_for_horizon("2026-08-28", "T3") == "2026-09-07"
    for closed in ("2026-08-31", "2026-09-01", "2026-09-02"):
        skipped = fuse_session(closed, paths=fusion_paths)
        assert skipped["session_status"] == SESSION_SKIPPED_NON_TRADING
        assert skipped["observations"] == []


def test_observation_maturity_uses_trading_sessions_not_calendar_days(fusion_paths):
    """O. T3 skips weekend; Saturday run does not mature."""
    from modules.actionable_research.observation_maturity import target_session_for_horizon

    strong = UNIVERSE[0]
    t0 = TRADE_DATE  # Friday 2026-08-14
    t3 = "2026-08-19"
    t5 = "2026-08-21"
    t10 = "2026-08-28"
    assert target_session_for_horizon(t0, "T3") == t3
    assert target_session_for_horizon(t0, "T5") == t5
    assert target_session_for_horizon(t0, "T10") == t10

    _write_freeze(fusion_paths, t0)
    t0_price = float(pd.read_csv(fusion_paths.t0_freeze_path()).query("symbol == @strong").iloc[0]["price"])
    _append_freeze_prices(
        fusion_paths,
        [
            {
                "trade_date": t3,
                "symbol": strong,
                "health_group": "TRUNG TINH",
                "group": "THEO DOI",
                "pattern_key_v2_frozen": "CTX::DNA",
                "price": t0_price * 1.10,
            },
            {
                "trade_date": t5,
                "symbol": strong,
                "health_group": "TRUNG TINH",
                "group": "THEO DOI",
                "pattern_key_v2_frozen": "CTX::DNA",
                "price": t0_price * 1.20,
            },
            {
                "trade_date": t10,
                "symbol": strong,
                "health_group": "TRUNG TINH",
                "group": "THEO DOI",
                "pattern_key_v2_frozen": "CTX::DNA",
                "price": t0_price * 0.95,
            },
        ],
    )
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[strong] = 50_000_000
    _write_camera(fusion_paths, t0, volumes)
    fuse_session(t0, paths=fusion_paths)

    saturday = fuse_session(WEEKEND, paths=fusion_paths)
    assert saturday["session_status"] == SESSION_SKIPPED_NON_TRADING
    ledger = [json.loads(ln) for ln in fusion_paths.observation_ledger_path().read_text().splitlines() if ln.strip()]
    assert ledger[0]["t3_return_pct"] is None

    t3_run = fuse_session(t3, paths=fusion_paths)
    assert t3_run["session_status"] == SESSION_ELIGIBLE
    ledger = [json.loads(ln) for ln in fusion_paths.observation_ledger_path().read_text().splitlines() if ln.strip()]
    row = ledger[0]
    assert abs(float(row["t3_return_pct"]) - 10.0) < 1e-6
    assert row["t3_status"] == "MATURE"
    assert row["t5_return_pct"] is None
    assert row["t10_return_pct"] is None
    assert row["t3_target_session"] == t3
    assert row["outcome_status"] == "PARTIAL"

    t5_run = fuse_session(t5, paths=fusion_paths)
    ledger = [json.loads(ln) for ln in fusion_paths.observation_ledger_path().read_text().splitlines() if ln.strip()]
    row = ledger[0]
    assert abs(float(row["t5_return_pct"]) - 20.0) < 1e-6
    assert row["t10_return_pct"] is None
    replay = fuse_session(t5, paths=fusion_paths)
    assert replay["idempotent_replay"] is True
    ledger2 = [json.loads(ln) for ln in fusion_paths.observation_ledger_path().read_text().splitlines() if ln.strip()]
    assert abs(float(ledger2[0]["t5_return_pct"]) - 20.0) < 1e-6
    assert len(ledger2) == 1


def test_t0_not_ready_is_unable_not_nothing_noteworthy(fusion_paths):
    payload = fuse_session(
        TRADE_DATE,
        paths=fusion_paths,
        daily_result={"run": {"run_disposition": "SUCCESS"}, "closed_loop_edge": {"skip_reason": "SKIPPED_T0_NOT_READY"}},
    )
    assert payload["session_status"] == "UNABLE_TO_ASSESS"
    assert payload["headline_vi"] == UNABLE_VI
    assert payload["headline_vi"] != NO_INTEREST_VI
    assert payload["observations"] == []


def test_fusion_creates_zero_scientific_live_forward_births(fusion_paths):
    strong = UNIVERSE[0]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(
        fusion_paths,
        [{"edge_id": "E1", "hypothesis_id": "H1", "status": "ACTIVE", "best_horizon": "T5"}],
    )
    _write_recognition(
        fusion_paths,
        TRADE_DATE,
        [{"symbol": strong, "edge_id": "E1", "best_horizon": "T5"}],
    )
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[strong] = 50_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes)
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    assert payload["scientific_writes"] == []
    ledger = fusion_paths.edge_root() / "edge_forward_ledger.csv"
    assert not ledger.exists()
    dumped = json.dumps(payload)
    assert "LIVE_FORWARD" not in dumped or payload["authority"] == AUTHORITY_LABEL
    assert "BUY" not in (payload.get("observations") or [{}])[0].get("reasons", [])


def test_forbidden_money_flow_labels_never_emitted(fusion_paths):
    from modules.actionable_research.contracts import FORBIDDEN_MONEY_FLOW_LABELS

    strong = UNIVERSE[0]
    _write_freeze(fusion_paths, TRADE_DATE)
    _write_edge_memory(fusion_paths, [])
    volumes = {sym: 1_000 for sym in UNIVERSE}
    volumes[strong] = 90_000_000
    _write_camera(fusion_paths, TRADE_DATE, volumes, opens={strong: 25000}, closes={strong: 15000})
    payload = fuse_session(TRADE_DATE, paths=fusion_paths)
    blob = json.dumps(payload)
    for label in FORBIDDEN_MONEY_FLOW_LABELS:
        assert f'"{label}"' not in blob
    rec = _by_symbol(payload, strong)
    assert rec["activity_status"] == INTRADAY_ACTIVITY_HIGH
    assert rec["price_direction"] == PRICE_DIRECTION_DOWN



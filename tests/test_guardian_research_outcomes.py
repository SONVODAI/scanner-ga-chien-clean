"""T+ evidence stays on the verified session list and never rewrites T0."""

import json
from pathlib import Path

from research.guardian_research.contract import FORWARD_HORIZONS
from research.guardian_research.outcomes import build_outcomes, refresh_outcomes
from research.guardian_research.snapshot import (
    build_snapshot,
    label_observation_origin,
    read_snapshot,
    write_snapshot,
)


def _observation(session, price, ema, ma, obv=10.0, obv_ema=50.0):
    return {
        "kind": "scan_row",
        "input_session": session,
        "reference_price_provenance": "production_scan.price",
        "quality": "production_scan_row",
        "source": "production_scan",
        "live_injected": False,
        "price": price,
        "ema9": ema,
        "ma20": ma,
        "obv": obv,
        "obv_ema9": obv_ema,
    }


def _seal(root: Path, session: str, observations: dict, priors=None) -> Path:
    document = build_snapshot(session, observations, symbols=tuple(observations), priors=priors)
    labeled = label_observation_origin(
        document,
        "CONTEMPORANEOUS",
        reconstruction={"observation_at": f"{session}T15:00:00+07:00", "sealed_at": f"{session}T15:00:00+07:00"},
    )
    return write_snapshot(root, labeled)


def _store(sessions: list[str], prices: dict[tuple[str, str], float], *, basis: str = "APPROX_LAST_5M_CLOSE") -> dict:
    rows = []
    for (symbol, session), close in prices.items():
        rows.append({"symbol": symbol, "session": session, "close": close, "clock": "14:45"})
    return {
        "schema": "approximate_reference_store.v1",
        "price_basis": basis,
        "trading_sessions": sessions,
        "as_of": sessions[-1],
        "rows": rows,
        "discontinuities": [],
    }


def test_weekend_is_not_a_trading_session_and_t0_stays_byte_stable(tmp_path):
    path = _seal(tmp_path, "2026-11-06", {"HPG": _observation("2026-11-06", 100, 90, 80)})
    before = path.read_bytes()
    store = _store(
        ["2026-11-06", "2026-11-09"],
        {("HPG", "2026-11-06"): 100.0, ("HPG", "2026-11-09"): 103.0},
    )
    view = build_outcomes(tmp_path, store)
    row = view["rows"][0]
    assert row["horizons"]["T+1"]["status"] == "APPROX_AVAILABLE"
    assert row["horizons"]["T+1"]["return_pct"] == 3.0
    assert row["horizons"]["T+3"]["status"] == "NOT_YET_OBSERVED"
    assert row["horizons"]["T+1"]["adverse_status"] == "DAILY_CLOSE_PATH"
    assert row["horizons"]["T+1"]["adverse_close_path_pct"] == 3.0
    assert path.read_bytes() == before
    assert read_snapshot(path)["content_sha256"] == json.loads(before)["content_sha256"]


def test_missing_later_price_stays_null(tmp_path):
    _seal(tmp_path, "2026-11-06", {"HPG": _observation("2026-11-06", 100, 90, 80)})
    store = _store(["2026-11-06", "2026-11-09"], {("HPG", "2026-11-06"): 100.0})
    view = build_outcomes(tmp_path, store)
    cell = view["rows"][0]["horizons"]["T+1"]
    assert cell["status"] == "TARGET_MISSING"
    assert cell["return_pct"] is None
    assert cell["included_in_primary"] is False
    assert cell["adverse_status"] == "PATH_INCOMPLETE"
    assert view["classifications"]["HOLD"]["horizons"]["T+1"]["evidence"] == "INSUFFICIENT_EVIDENCE"


def test_absent_store_reports_the_blocker_without_rates(tmp_path):
    _seal(tmp_path, "2026-11-06", {"HPG": _observation("2026-11-06", 100, 90, 80)})
    view = build_outcomes(tmp_path, None)
    assert view["measured"] is False
    assert view["evidence_status"] == "PRICE_REFERENCE_ABSENT"
    assert view["price_basis"] is None
    assert all(cell["return_pct"] is None for row in view["rows"] for cell in row["horizons"].values())
    assert view["false_sell"]["evidence"] == "INSUFFICIENT_EVIDENCE"


def test_repeated_refresh_is_identical_and_does_not_touch_the_seal(tmp_path):
    path = _seal(tmp_path, "2026-11-06", {"HPG": _observation("2026-11-06", 100, 90, 80)})
    before = path.read_bytes()
    store_path = tmp_path / "reference_store.json"
    store_path.write_text(json.dumps(_store(
        ["2026-11-06", "2026-11-09"],
        {("HPG", "2026-11-06"): 100.0, ("HPG", "2026-11-09"): 103.0},
    )), encoding="utf-8")
    first = refresh_outcomes(tmp_path, store_path, tmp_path / "outcomes.json")
    second = refresh_outcomes(tmp_path, store_path, tmp_path / "outcomes.json")
    assert first["status"] == second["status"] == "measured"
    assert path.read_bytes() == before
    written = (tmp_path / "outcomes.json").read_bytes()
    refresh_outcomes(tmp_path, store_path, tmp_path / "outcomes.json")
    assert (tmp_path / "outcomes.json").read_bytes() == written


def test_new_and_persistent_states_stay_separate(tmp_path):
    first = build_snapshot(
        "2026-11-06",
        {"HPG": _observation("2026-11-06", 100, 90, 80)},
        symbols=("HPG",),
    )
    _seal(tmp_path, "2026-11-09", {"HPG": _observation("2026-11-09", 100, 90, 80)}, priors=[first])
    store = _store(
        ["2026-11-06", "2026-11-09", "2026-11-10"],
        {
            ("HPG", "2026-11-09"): 100.0,
            ("HPG", "2026-11-10"): 90.0,
        },
    )
    view = build_outcomes(tmp_path, store)
    assert view["rows"][0]["tenure"] == "PERSISTENT"
    assert view["tenure"]["PERSISTENT"] == 1
    assert view["classifications"]["HOLD"]["persistent"] == 1
    assert view["classifications"]["HOLD"]["new_or_changed"] == 0
    assert view["rows"][0]["horizons"]["T+1"]["return_pct"] == -10.0
    assert view["rows"][0]["horizons"]["T+1"]["adverse_close_path_pct"] == -10.0


def test_false_sell_counts_a_later_rise_and_rejects_a_foreign_basis(tmp_path):
    _seal(tmp_path, "2026-11-06", {"FPT": _observation("2026-11-06", 30, 22, 24, 10, 50)})
    store = _store(
        ["2026-11-06", "2026-11-09"],
        {("FPT", "2026-11-06"): 30.0, ("FPT", "2026-11-09"): 33.0},
    )
    view = build_outcomes(tmp_path, store)
    assert view["rows"][0]["classification"] == "SELL"
    assert view["false_sell"]["horizons"]["T+1"]["rose"] == 1.0
    assert view["false_sell"]["horizons"]["T+1"]["rose_above_5pct"] == 1.0
    assert len(FORWARD_HORIZONS) == 6
    rejected = build_outcomes(tmp_path, _store(["2026-11-06"], {("FPT", "2026-11-06"): 30.0}, basis="OFFICIAL_CLOSE"))
    assert rejected["measured"] is False
    assert rejected["evidence_status"] == "PRICE_BASIS_MISMATCH"
    assert rejected["rows"][0]["horizons"]["T+1"]["return_pct"] is None

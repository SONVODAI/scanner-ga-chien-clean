"""T+ evidence stays on the verified session list and never rewrites T0."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from research.guardian_research.close_job import run_guardian_close
from research.guardian_research.contract import FORWARD_HORIZONS
from research.guardian_research.outcomes import build_outcomes, delayed_admission_reason, refresh_outcomes
from research.guardian_research.snapshot import (
    _digest,
    attach_session_witness,
    build_snapshot,
    label_observation_origin,
    read_snapshot,
    write_snapshot,
)
from tests.test_guardian_close_job import _payload

VN = ZoneInfo("Asia/Ho_Chi_Minh")


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


def _weekdays(start: str, count: int) -> list[str]:
    cursor = date.fromisoformat(start)
    days = []
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def _patch_remote(monkeypatch):
    monkeypatch.setenv("GUARDIAN_RESEARCH_SNAPSHOT_ENABLED", "true")
    monkeypatch.setattr(
        "research.guardian_research.pipeline.read_remote_snapshot",
        lambda _root, _session: (None, "absent"),
    )
    monkeypatch.setattr(
        "research.guardian_research.pipeline.publish_snapshot",
        lambda _root, _session: "created",
    )


def _close(root: Path, project: Path, session: str, now: datetime, observed: datetime):
    witness = {"source": "vnindex_daily_bar", "bar_session": session, "probe_error": None}
    return run_guardian_close(
        now=now,
        root=root,
        close_scan=lambda: _payload(("HPG",), observed_at=observed.isoformat(), day=session),
        symbols=("HPG",),
        witness=witness,
        project_root=project,
    )


def _write_origin(root: Path, session: str, origin: str, reconstruction: dict, *, witness: bool = True) -> Path:
    document = build_snapshot(session, {"HPG": _observation(session, 26, 25, 24)}, symbols=("HPG",))
    if witness:
        document = attach_session_witness(
            document,
            {"source": "vnindex_daily_bar", "bar_session": session, "probe_error": None},
        )
    labeled = label_observation_origin(document, origin, reconstruction=reconstruction)
    return write_snapshot(root, labeled)


def test_valid_delayed_enters_research_and_horizons_follow_trading_sessions(monkeypatch, tmp_path):
    _patch_remote(monkeypatch)
    project = tmp_path / "repo"
    research = project / "data" / "guardian_research"
    friday = datetime(2026, 11, 13, 19, 30, tzinfo=VN)
    first = _close(research, project, "2026-11-13", friday, friday)
    observed = datetime(2026, 11, 16, 18, 21, tzinfo=VN)
    second = _close(research, project, "2026-11-16", datetime(2026, 11, 16, 20, 1, tzinfo=VN), observed)
    assert first["status"] == "created"
    assert second["status"] == "created"
    delayed_path = Path(second["path"])
    delayed_bytes = delayed_path.read_bytes()
    assert read_snapshot(delayed_path)["observation_origin"] == "DELAYED"
    days = _weekdays("2026-11-13", 25)
    assert days[1] == "2026-11-16"
    assert "2026-11-14" not in days and "2026-11-15" not in days
    prices = {("HPG", day): 100.0 + offset for offset, day in enumerate(days)}
    view = build_outcomes(research, _store(days, prices))
    assert view["delayed_sessions_included"] == ["2026-11-16"]
    assert view["delayed_sessions_excluded"] == []
    assert view["contemporaneous_sessions"] == ["2026-11-13"]
    by_session = {row["session"]: row for row in view["rows"]}
    friday_row = by_session["2026-11-13"]
    monday_row = by_session["2026-11-16"]
    for step in FORWARD_HORIZONS:
        label = f"T+{step}"
        assert friday_row["horizons"][label]["status"] == "APPROX_AVAILABLE"
        assert friday_row["horizons"][label]["return_pct"] == float(step)
        assert monday_row["horizons"][label]["status"] == "APPROX_AVAILABLE"
        expected = round(((101.0 + step) / 101.0 - 1) * 100, 6)
        assert monday_row["horizons"][label]["return_pct"] == expected
    delayed_path.unlink()
    without = build_outcomes(research, _store(days, prices))
    delayed_path.write_bytes(delayed_bytes)
    kept = {row["session"]: row for row in without["rows"]}
    assert kept["2026-11-13"] == friday_row
    assert "2026-11-16" not in kept
    assert delayed_path.read_bytes() == delayed_bytes
    assert read_snapshot(delayed_path)["observation_origin"] == "DELAYED"


def test_invalid_delayed_and_backfilled_stay_out_of_research(tmp_path):
    early = _write_origin(
        tmp_path,
        "2026-11-16",
        "DELAYED",
        {
            "observation_at": "2026-11-16T15:00:00+07:00",
            "sealed_at": "2026-11-16T20:00:00+07:00",
            "timestamp_provenance": "close_scan.observed_at",
        },
    )
    naive = _write_origin(
        tmp_path / "naive",
        "2026-11-17",
        "DELAYED",
        {
            "observation_at": "2026-11-17T18:20:00",
            "sealed_at": "2026-11-17T20:00:00+07:00",
            "timestamp_provenance": "close_scan.observed_at",
        },
    )
    wrong_day = _write_origin(
        tmp_path / "day",
        "2026-11-18",
        "DELAYED",
        {
            "observation_at": "2026-11-19T18:20:00+07:00",
            "sealed_at": "2026-11-19T20:00:00+07:00",
            "timestamp_provenance": "close_scan.observed_at",
        },
    )
    before_seal = _write_origin(
        tmp_path / "order",
        "2026-11-19",
        "DELAYED",
        {
            "observation_at": "2026-11-19T20:00:00+07:00",
            "sealed_at": "2026-11-19T18:20:00+07:00",
            "timestamp_provenance": "close_scan.observed_at",
        },
    )
    unwitnessed = _write_origin(
        tmp_path / "witness",
        "2026-11-20",
        "DELAYED",
        {
            "observation_at": "2026-11-20T18:20:00+07:00",
            "sealed_at": "2026-11-20T20:00:00+07:00",
            "timestamp_provenance": "close_scan.observed_at",
        },
        witness=False,
    )
    backfilled = _write_origin(
        tmp_path / "backfill",
        "2026-11-23",
        "BACKFILLED",
        {
            "observation_at": "2026-11-23T18:20:00+07:00",
            "sealed_at": "2026-11-23T18:20:00+07:00",
            "timestamp_provenance": "close_scan.observed_at",
        },
    )
    valid_clock = _write_origin(
        tmp_path / "clock",
        "2026-11-24",
        "DELAYED",
        {
            "observation_at": "2026-11-24T18:20:00+07:00",
            "sealed_at": "2026-11-24T20:00:00+07:00",
            "timestamp_provenance": "close_scan.observed_at",
        },
    )
    wrong_bar = read_snapshot(valid_clock)
    wrong_bar["session_witness"]["bar_session"] = "2026-11-13"
    wrong_bar.pop("content_sha256")
    wrong_bar["content_sha256"] = _digest(wrong_bar)
    bar_path = write_snapshot(tmp_path / "bar", wrong_bar)
    tampered = read_snapshot(valid_clock)
    tampered["market"]["market_real"] = 3.6
    tampered["rows"][0]["market_real"] = 3.6
    tampered["rows"][0]["forward"]["horizons"]["T+1"]["return_pct"] = 5.0
    assert delayed_admission_reason(tampered, None) == "LOOKAHEAD"
    assert read_snapshot(valid_clock)["rows"][0]["forward"]["horizons"]["T+1"]["return_pct"] is None

    checks = (
        (tmp_path, early, "CLOCK_REJECTED"),
        (tmp_path / "naive", naive, "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"),
        (tmp_path / "day", wrong_day, "CLOCK_REJECTED"),
        (tmp_path / "order", before_seal, "SEAL_UNVERIFIED"),
        (tmp_path / "witness", unwitnessed, "WITNESS_ABSENT"),
        (tmp_path / "bar", bar_path, "WITNESS_INCONSISTENT"),
    )
    for root, path, reason in checks:
        view = build_outcomes(root, None)
        assert view["rows"] == []
        assert view["delayed_sessions_excluded"] == [{"session": read_snapshot(path)["session"], "reason": reason}]
        assert path.read_bytes()
    backfill_view = build_outcomes(backfilled.parent.parent, None)
    assert backfill_view["rows"] == []
    assert backfill_view["backfilled_sessions_excluded"] == ["2026-11-23"]
    assert backfill_view["delayed_sessions_included"] == []


def test_freeze_hash_mismatch_excludes_delayed_without_rewriting_the_snapshot(monkeypatch, tmp_path):
    _patch_remote(monkeypatch)
    project = tmp_path / "repo"
    research = project / "data" / "guardian_research"
    observed = datetime(2026, 11, 16, 18, 21, tzinfo=VN)
    result = _close(research, project, "2026-11-16", datetime(2026, 11, 16, 20, 1, tzinfo=VN), observed)
    snapshot = Path(result["path"])
    before = snapshot.read_bytes()
    freeze = project / "data" / "earning_learning" / "t0_observation_freeze.csv"
    original = freeze.read_bytes()
    admitted = build_outcomes(research, None)
    assert admitted["delayed_sessions_included"] == ["2026-11-16"]
    import pandas as pd

    frame = pd.read_csv(freeze)
    frame.loc[frame["trade_date"].astype(str).str.slice(0, 10) == "2026-11-16", "guardian_witness_sha256"] = "0" * 64
    frame.to_csv(freeze, index=False)
    refused = build_outcomes(research, None)
    assert refused["delayed_sessions_included"] == []
    assert refused["delayed_sessions_excluded"] == [{"session": "2026-11-16", "reason": "WITNESS_INTEGRITY"}]
    assert refused["rows"] == []
    assert snapshot.read_bytes() == before
    freeze.write_bytes(original)
    assert freeze.read_bytes() == original

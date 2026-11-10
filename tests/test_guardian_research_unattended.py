"""Unattended Guardian capture from the existing close scan, and a read-only panel."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from research.guardian_research.panel import render_guardian_research_panel
from research.guardian_research.pipeline import capture_from_close_payload
from research.guardian_research.snapshot import read_snapshot
from research.guardian_research.universe import load_tracked_symbols

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION = "2026-11-05"
EVENING = datetime(2026, 11, 5, 18, 30, tzinfo=VN)
EARLY = datetime(2026, 11, 5, 17, 59, tzinfo=VN)


def _row(symbol, price=26, ema9=25, ma20=24, obv=1000, obv_ema9=900, day=SESSION):
    return {
        "symbol": symbol,
        "date": day,
        "price": price,
        "ema9": ema9,
        "ma20": ma20,
        "obv": obv,
        "obv_ema9": obv_ema9,
        "is_live_adjusted": False,
    }


def _payload(rows, symbols, *, absent=(), errors=(), market_real=6.5, day=SESSION):
    return {
        "ok": True,
        "status": "READY",
        "source": "close_scan",
        "trade_date": day,
        "market_real": market_real,
        "trading_today": True,
        "trading_reason": f"VNINDEX có giao dịch hôm nay: {day}",
        "scan_df": pd.DataFrame(list(rows)),
        "scan_coverage": {
            "requested": list(symbols),
            "returned": [row["symbol"] for row in rows],
            "absent": list(absent),
            "errors": list(errors),
        },
    }


def test_close_scan_coverage_keeps_a_scanner_report_or_names_missing_rows():
    from modules.close_session_scan import scan_coverage

    attached = {"requested": ["HPG"], "returned": [], "absent": ["HPG"], "errors": ["HPG"]}
    assert scan_coverage(["HPG"], pd.DataFrame(), attached) is attached
    derived = scan_coverage(["HPG", "SSI"], pd.DataFrame([{"symbol": "hpg"}]), None)
    assert derived == {
        "requested": ["HPG", "SSI"],
        "returned": ["HPG"],
        "absent": ["SSI"],
        "errors": [],
    }


def test_a_session_without_the_vnindex_witness_is_not_sealed(tmp_path: Path):
    tracked = ("HPG",)
    closed = _payload([_row("HPG")], tracked)
    closed["trading_today"] = False
    closed["trading_reason"] = "Không lưu Evolution: VNINDEX mới nhất là 2026-11-04, không phải 2026-11-05"
    refused = capture_from_close_payload(closed, now=EVENING, root=tmp_path, symbols=tracked)
    assert refused["status"] == "refused"
    assert refused["reason"] == "NON_TRADING_SESSION"
    assert not (tmp_path / "sessions").exists()

    missing = _payload([_row("HPG")], tracked)
    del missing["trading_today"]
    absent = capture_from_close_payload(missing, now=EVENING, root=tmp_path, symbols=tracked)
    assert absent["reason"] == "SESSION_EVIDENCE_ABSENT"
    assert not (tmp_path / "sessions").exists()


def test_archive_save_clock_is_not_an_after_close_observation(tmp_path: Path):
    source = Path(__file__).resolve().parents[1].joinpath("modules", "daily_summary.py").read_text(encoding="utf-8")
    assert 'out["saved_at"] = datetime.now(VN_TZ).isoformat(timespec="seconds")' in source
    tracked = ("HPG",)
    payload = _payload([_row("HPG", day="2026-11-04")], tracked, day="2026-11-04")
    del payload["trading_reason"]
    payload["trading_reason"] = "VNINDEX có giao dịch hôm nay: 2026-11-04"
    payload["saved_at"] = "2026-11-04T21:11:16+07:00"
    refused = capture_from_close_payload(
        payload,
        now=datetime(2026, 11, 4, 21, 30, tzinfo=VN),
        root=tmp_path,
        symbols=tracked,
    )
    assert refused["status"] == "refused"
    assert refused["reason"] == "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"
    assert not (tmp_path / "sessions").exists()

    morning = _payload([_row("HPG", day="2026-11-05")], tracked, day="2026-11-05")
    morning["observed_at"] = "2026-11-06T05:19:59+07:00"
    early_morning = capture_from_close_payload(
        morning,
        now=datetime(2026, 11, 6, 6, 0, tzinfo=VN),
        root=tmp_path,
        symbols=tracked,
    )
    assert early_morning["reason"] == "SCHEDULE_TOO_LATE"
    assert not (tmp_path / "sessions").exists()

    # Observation stayed on the session evening; seal after ICT midnight is DELAYED.
    delayed_payload = _payload([_row("HPG")], tracked)
    delayed_payload["observed_at"] = EVENING.isoformat()
    delayed = capture_from_close_payload(
        delayed_payload,
        now=datetime(2026, 11, 6, 5, 30, tzinfo=VN),
        root=tmp_path / "delayed",
        symbols=tracked,
    )
    assert delayed["status"] == "created"
    assert delayed["document"]["observation_origin"] == "DELAYED"
    assert delayed["document"]["reconstruction"]["observation_at"] == EVENING.isoformat()
    assert delayed["document"]["reconstruction"]["sealed_at"] == datetime(
        2026, 11, 6, 5, 30, tzinfo=VN
    ).isoformat()

    after_open = capture_from_close_payload(
        delayed_payload,
        now=datetime(2026, 11, 6, 9, 0, tzinfo=VN),
        root=tmp_path / "after_open",
        symbols=tracked,
    )
    assert after_open["reason"] == "SCHEDULE_TOO_LATE"
    assert not (tmp_path / "after_open" / "sessions").exists()


def test_a_verified_scan_clock_can_be_sealed_later_without_rewriting(tmp_path: Path):
    tracked = ("HPG",)
    payload = _payload([_row("HPG")], tracked)
    payload["observed_at"] = EVENING.isoformat()
    sealed = capture_from_close_payload(payload, now=EVENING, root=tmp_path, symbols=tracked)
    assert sealed["status"] == "created"
    assert sealed["document"]["observation_origin"] == "CONTEMPORANEOUS"
    assert sealed["document"]["reconstruction"]["observation_at"] == EVENING.isoformat()
    assert sealed["document"]["reconstruction"]["sealed_at"] == EVENING.isoformat()
    assert sealed["document"]["reconstruction"]["timestamp_provenance"] == "close_scan.observed_at"
    stored = sealed["path"].read_bytes()
    later = capture_from_close_payload(
        payload,
        now=datetime(2026, 11, 6, 6, 0, tzinfo=VN),
        root=tmp_path,
        symbols=tracked,
    )
    assert later["status"] == "unchanged"
    assert sealed["path"].read_bytes() == stored
    changed = _payload([_row("HPG", price=20)], tracked)
    changed["observed_at"] = EVENING.isoformat()
    conflict = capture_from_close_payload(
        changed,
        now=datetime(2026, 11, 6, 6, 0, tzinfo=VN),
        root=tmp_path,
        symbols=tracked,
    )
    assert conflict["status"] == "conflict"
    assert sealed["path"].read_bytes() == stored


def test_close_scan_hands_one_payload_to_the_collector(monkeypatch, tmp_path: Path):
    from types import SimpleNamespace

    from modules import close_session_scan as scan_mod

    calls = {"scan": 0}

    def run_scan(symbols):
        calls["scan"] += 1
        run_scan.coverage = {
            "requested": list(symbols),
            "returned": list(symbols),
            "absent": [],
            "errors": [],
        }
        return pd.DataFrame([_row("HPG")])

    monkeypatch.setattr(scan_mod, "add_evolution_health", lambda frame: frame)
    monkeypatch.setattr(
        "modules.research_market_context.market_context.try_append_market_context",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "modules.research_evolution_ledger.ledger.try_append_evolution_ledger",
        lambda **_kwargs: None,
    )
    payload = scan_mod.build_close_scan_inputs(
        now=EVENING,
        symbols=["HPG"],
        api={
            "WATCHLIST": ["HPG"],
            "run_scan": run_scan,
            "calc_market_real": lambda _frame: 7.5,
            "calc_market_live": lambda _frame: 7.5,
            "calc_market_forecast": lambda _frame: SimpleNamespace(score=1.0, text="t", confidence=1.0),
            "market_status_text": lambda _value: ("status", "action"),
            "is_vnindex_trading_today": lambda: (True, "VNINDEX có giao dịch hôm nay: 2026-11-05"),
            "elite_regime": lambda *_args: ("regime", {}, "note"),
            "build_rsi_breadth_report": lambda _frame: {},
        },
    )
    assert calls["scan"] == 1
    assert payload["observed_at"] == EVENING.isoformat()
    assert payload["market_real"] == 7.5
    assert payload["trading_today"] is True
    assert payload["scan_coverage"]["requested"] == ["HPG"]
    assert payload["source"] == "close_scan"
    sealed = capture_from_close_payload(payload, now=EVENING, root=tmp_path, symbols=("HPG",))
    assert sealed["status"] == "created"
    assert sealed["document"]["rows"][0]["classification"] == "HOLD"
    assert calls["scan"] == 1


def test_partial_scan_does_not_seal_and_the_retry_does(tmp_path: Path):
    tracked = load_tracked_symbols()
    partial = _payload(
        [_row("HPG")],
        tracked,
        absent=[symbol for symbol in tracked if symbol != "HPG"],
        errors=["SSI"],
    )
    refused = capture_from_close_payload(partial, now=EVENING, root=tmp_path)
    assert refused["status"] == "refused"
    assert refused["reason"] == "PARTIAL_SCAN"
    assert not (tmp_path / "sessions").exists()

    early = capture_from_close_payload(
        _payload([_row("HPG")], tracked, absent=[symbol for symbol in tracked if symbol != "HPG"]),
        now=EARLY,
        root=tmp_path,
    )
    assert early["reason"] == "BEFORE_CANONICAL_WINDOW"
    assert not (tmp_path / "sessions").exists()

    sealed = capture_from_close_payload(
        _payload(
            [_row("HPG"), _row("SSI", price=24, ema9=23, ma20=24, obv=800, obv_ema9=900)],
            tracked,
            absent=[symbol for symbol in tracked if symbol not in {"HPG", "SSI"}],
        ),
        now=EVENING,
        root=tmp_path,
    )
    assert sealed["status"] == "created"
    assert sealed["tracked_count"] == 143
    by_symbol = {row["symbol"]: row for row in sealed["document"]["rows"]}
    assert by_symbol["HPG"]["classification"] == "HOLD"
    assert by_symbol["SSI"]["classification"] == "SELL"
    assert by_symbol["SSI"]["score"] == 80
    assert by_symbol["VCB"]["classification"] == "UNAVAILABLE"
    assert by_symbol["VCB"]["reason"] == "OBSERVATION_ABSENT"
    assert by_symbol["HPG"]["forward"]["status"] == "UNVERIFIED"
    stored = sealed["path"].read_bytes()

    again = capture_from_close_payload(
        _payload(
            [_row("HPG"), _row("SSI", price=24, ema9=23, ma20=24, obv=800, obv_ema9=900)],
            tracked,
            absent=[symbol for symbol in tracked if symbol not in {"HPG", "SSI"}],
        ),
        now=datetime(2026, 11, 5, 20, 30, tzinfo=VN),
        root=tmp_path,
    )
    assert again["status"] == "unchanged"
    assert sealed["path"].read_bytes() == stored

    conflict = capture_from_close_payload(
        _payload(
            [_row("HPG", price=20), _row("SSI", price=24, ema9=23, ma20=24, obv=800, obv_ema9=900)],
            tracked,
            absent=[symbol for symbol in tracked if symbol not in {"HPG", "SSI"}],
            market_real=1,
        ),
        now=datetime(2026, 11, 5, 20, 30, tzinfo=VN),
        root=tmp_path,
    )
    assert conflict["status"] == "conflict"
    assert read_snapshot(sealed["path"])["rows"][0]["market_real"] == 6.5
    assert sealed["path"].read_bytes() == stored


def test_existing_remote_snapshot_is_not_replaced(tmp_path: Path, monkeypatch):
    symbols = ("HPG",)
    monkeypatch.setattr(
        "research.guardian_research.pipeline.read_remote_snapshot",
        lambda *_args, **_kwargs: ({"content_sha256": "different"}, "present"),
    )
    refused = capture_from_close_payload(
        _payload([_row("HPG")], symbols),
        now=EVENING,
        root=tmp_path,
        symbols=symbols,
    )
    assert refused["status"] == "conflict"
    assert not (tmp_path / "sessions").exists()


def test_state_age_uses_only_sealed_sessions(tmp_path: Path):
    symbols = ("HPG", "SSI")
    first = capture_from_close_payload(
        _payload([_row("HPG", day="2026-11-04")], symbols, absent=["SSI"], day="2026-11-04"),
        now=datetime(2026, 11, 4, 18, 30, tzinfo=VN),
        root=tmp_path,
        symbols=symbols,
    )
    assert first["document"]["rows"][0]["transition"] == "INITIAL"
    assert first["document"]["rows"][0]["state_age_sessions"] == 1
    second = capture_from_close_payload(
        _payload([_row("HPG", price=24)], symbols, absent=["SSI"]),
        now=EVENING,
        root=tmp_path,
        symbols=symbols,
    )
    hpg = next(row for row in second["document"]["rows"] if row["symbol"] == "HPG")
    assert hpg["classification"] == "WATCH"
    assert hpg["previous_classification"] == "HOLD"
    assert hpg["transition"] == "CHANGED"
    assert hpg["state_age_sessions"] == 1
    assert next(row for row in second["document"]["rows"] if row["symbol"] == "SSI")["classification"] == "UNAVAILABLE"


def test_panel_reads_the_snapshot_and_does_not_write(tmp_path: Path, monkeypatch):
    symbols = ("HPG",)
    capture_from_close_payload(
        _payload([_row("HPG")], symbols),
        now=EVENING,
        root=tmp_path,
        symbols=symbols,
    )
    before = (tmp_path / "sessions" / f"{SESSION}.json").read_bytes()
    import streamlit as st

    monkeypatch.setattr(st, "markdown", lambda *_a, **_k: None)
    monkeypatch.setattr(st, "caption", lambda *_a, **_k: None)
    monkeypatch.setattr(st, "info", lambda *_a, **_k: None)
    monkeypatch.setattr(st, "dataframe", lambda *_a, **_k: None)
    monkeypatch.setattr(st, "expander", lambda *_a, **_k: _Expander())
    monkeypatch.setattr(st, "columns", lambda count: [_Metric() for _ in range(count)])
    shown = render_guardian_research_panel(
        pd.DataFrame([_row("ZZZ", price=1, ema9=1, ma20=1)]),
        99,
        EARLY,
        root=tmp_path,
    )
    assert shown["session"] == SESSION
    assert shown["rows"][0]["classification"] == "HOLD"
    assert (tmp_path / "sessions" / f"{SESSION}.json").read_bytes() == before
    source = Path(__file__).resolve().parents[1].joinpath("research", "guardian_research", "panel.py").read_text(encoding="utf-8")
    assert "capture_from_close_payload" not in source
    assert "write_snapshot" not in source


def test_finalize_seals_from_the_close_scan_without_replacing_other_steps(tmp_path, monkeypatch):
    from modules.post_close_finalize import run_post_close_finalize

    tracked = load_tracked_symbols()
    payload = _payload(
        [_row("HPG")],
        tracked,
        absent=[symbol for symbol in tracked if symbol != "HPG"],
    )
    monkeypatch.setattr("research.guardian_research.panel.default_root", lambda: tmp_path)
    monkeypatch.setattr(
        "modules.post_close_finalize._run_close_writers",
        lambda *_a, **_k: ({"status": "CAPTURED", "source": "close_scan"}, {"status": "FROZEN", "source": "close_scan"}),
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_forward",
        lambda *_a, **_k: {"status": "FROZEN", "source": "session_handoff_v1"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_buy_elite",
        lambda *_a, **_k: {"status": "APPENDED", "source": "session_handoff_v1"},
    )
    monkeypatch.setattr(
        "modules.post_close_finalize._finalize_learning",
        lambda *_a, **_k: {"status": "UPDATED", "source": "session_handoff_v1"},
    )
    report = run_post_close_finalize(
        now=EVENING,
        close_scan=lambda: payload,
        mature=False,
    )
    assert report["steps"]["market_t0"]["status"] == "CAPTURED"
    assert report["steps"]["sweetspot"]["status"] == "FROZEN"
    assert report["steps"]["guardian_research"]["status"] == "created"
    assert report["steps"]["guardian_research"]["source"] == "close_scan"


class _Expander:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Metric:
    def metric(self, *_args, **_kwargs):
        return None

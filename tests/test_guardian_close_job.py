"""Guardian close is isolated from Research Ledger finalization."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from research.guardian_research.close_job import run_guardian_close
from research.guardian_research.performance import read_performance_view
from research.guardian_research.snapshot import read_snapshot
from research.guardian_research.universe import load_tracked_symbols

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION = "2026-11-06"
EVENING = datetime(2026, 11, 6, 19, 30, tzinfo=VN)
OBSERVED = "2026-11-06T19:05:00+07:00"
BACKFILL_HASH = "388b856c2d85d885386de51b8ff834b640779e0c3e2e6e3d15902a4a2da72afa"


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


def _payload(symbols, *, absent=(), errors=(), observed_at=OBSERVED, day=SESSION, price=26):
    rows = [_row(symbol, price=price, day=day) for symbol in symbols if symbol not in set(absent)]
    return {
        "ok": True,
        "status": "READY",
        "source": "close_scan",
        "trade_date": day,
        "market_real": 6.5,
        "trading_today": True,
        "trading_reason": f"VNINDEX có giao dịch hôm nay: {day}",
        "observed_at": observed_at,
        "scan_df": pd.DataFrame(rows),
        "scan_coverage": {
            "requested": list(symbols),
            "returned": [row["symbol"] for row in rows],
            "absent": list(absent),
            "errors": list(errors),
        },
    }


def _enable(monkeypatch):
    monkeypatch.setenv("GUARDIAN_RESEARCH_SNAPSHOT_ENABLED", "true")


def _local_only(monkeypatch):
    monkeypatch.setattr(
        "research.guardian_research.pipeline.read_remote_snapshot",
        lambda _root, _session: (None, "absent"),
    )
    monkeypatch.setattr(
        "research.guardian_research.pipeline.publish_snapshot",
        lambda _root, _session: "created",
    )


def test_authority_gate_ignores_the_guardian_flag(monkeypatch, capsys):
    from modules.post_close_finalize import main

    called = []
    monkeypatch.setattr(
        "modules.post_close_finalize.run_post_close_finalize",
        lambda: called.append("ran") or {"status": "RAN"},
    )
    _enable(monkeypatch)
    monkeypatch.delenv("POST_CLOSE_RESEARCH_ENABLED", raising=False)
    main()
    assert "SCHEDULE_DISABLED" in capsys.readouterr().out

    monkeypatch.setenv("POST_CLOSE_RESEARCH_ENABLED", "true")
    monkeypatch.setattr("modules.forward_ledger_store.authority_ready", lambda **_kwargs: False)
    main()
    assert "AUTHORITY_NOT_READY" in capsys.readouterr().out
    assert called == []


def test_guardian_job_does_not_finalize_other_systems(monkeypatch, tmp_path: Path):
    calls = []

    def boom(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("unrelated finalizer was called")

    for target in (
        "modules.post_close_finalize.run_post_close_finalize",
        "modules.post_close_finalize._finalize_forward",
        "modules.post_close_finalize._finalize_buy_elite",
        "modules.post_close_finalize._finalize_learning",
        "modules.post_close_finalize._run_close_writers",
        "modules.research_market_context.market_context.try_append_market_context",
        "modules.research_evolution_ledger.ledger.try_append_evolution_ledger",
    ):
        monkeypatch.setattr(target, boom)
    _enable(monkeypatch)
    _local_only(monkeypatch)
    result = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert result["status"] == "created"
    assert calls == []
    source = Path(__file__).resolve().parents[1].joinpath(
        "research", "guardian_research", "close_job.py"
    ).read_text(encoding="utf-8")
    assert "post_close_finalize" not in source
    assert "authority_ready" not in source
    assert "live_candidate" not in source
    assert "position_guardian" not in source


def test_default_scan_does_not_retain_research_ledgers(monkeypatch, tmp_path: Path):
    seen = {}

    def build(**kwargs):
        seen.update(kwargs)
        return _payload(("HPG",))

    monkeypatch.setattr("modules.close_session_scan.build_close_scan_inputs", build)
    _enable(monkeypatch)
    _local_only(monkeypatch)
    result = run_guardian_close(now=EVENING, root=tmp_path, symbols=("HPG",))
    assert result["status"] == "created"
    assert seen["retain_research"] is False
    assert seen["now"] == EVENING


def test_flag_off_does_not_scan(monkeypatch):
    monkeypatch.delenv("GUARDIAN_RESEARCH_SNAPSHOT_ENABLED", raising=False)
    called = []
    result = run_guardian_close(close_scan=lambda: called.append("scan") or _payload(("HPG",)))
    assert result["status"] == "disabled"
    assert result["reason"] == "ENABLE_FLAG_OFF"
    assert called == []


def test_observed_at_and_vnindex_witness_are_required(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    missing_clock = _payload(("HPG",))
    del missing_clock["observed_at"]
    missing_clock["saved_at"] = "2026-11-06T21:10:01+07:00"
    saved = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: missing_clock,
        symbols=("HPG",),
    )
    assert saved["reason"] == "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"
    assert not (tmp_path / "sessions").exists()

    early = _payload(("HPG",), observed_at="2026-11-06T17:59:00+07:00")
    too_soon = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: early,
        symbols=("HPG",),
    )
    assert too_soon["reason"] == "BEFORE_CANONICAL_WINDOW"

    closed = _payload(("HPG",))
    closed["trading_today"] = False
    closed["trading_reason"] = "VNINDEX mới nhất là 2026-11-05, không phải 2026-11-06"
    witness = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: closed,
        symbols=("HPG",),
    )
    assert witness["reason"] == "NON_TRADING_SESSION"
    assert not (tmp_path / "sessions").exists()


def test_partial_stale_and_incomplete_143_payloads_are_refused(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    tracked = load_tracked_symbols()
    assert len(tracked) == 143
    partial = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(tracked, absent=("HPG",)),
        symbols=tracked,
    )
    assert partial["reason"] == "PARTIAL_SCAN"

    stale = _payload(("HPG",), day="2026-11-05")
    stale["trade_date"] = SESSION
    stale["scan_df"] = pd.DataFrame([_row("HPG", day="2026-11-05")])
    refused = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: stale,
        symbols=("HPG",),
    )
    assert refused["reason"] == "STALE_MARKET_DATA"

    blank = _payload(("HPG",))
    blank["scan_df"] = pd.DataFrame([_row("HPG", obv=None)])
    incomplete = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: blank,
        symbols=("HPG",),
    )
    assert incomplete["reason"] == "INCOMPLETE_INPUT"
    assert not (tmp_path / "sessions").exists()


def test_same_seal_is_idempotent_and_a_conflict_is_rejected(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    first = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert first["status"] == "created"
    assert first["tracked_count"] == 1
    stored = read_snapshot(Path(first["path"]))
    assert stored["content_sha256"] == first["content_sha256"]
    before = Path(first["path"]).read_bytes()

    again = run_guardian_close(
        now=datetime(2026, 11, 6, 20, 0, tzinfo=VN),
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert again["status"] == "unchanged"
    assert again["content_sha256"] == first["content_sha256"]
    assert Path(first["path"]).read_bytes() == before

    conflict = run_guardian_close(
        now=datetime(2026, 11, 6, 20, 5, tzinfo=VN),
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",), price=99),
        symbols=("HPG",),
    )
    assert conflict["status"] == "conflict"
    assert conflict["reason"] == "SNAPSHOT_CONFLICT"
    assert Path(first["path"]).read_bytes() == before


def test_publication_reports_the_remote_result_and_the_backfill_stays(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    published = []
    monkeypatch.setattr(
        "research.guardian_research.pipeline.read_remote_snapshot",
        lambda _root, _session: (None, "absent"),
    )
    monkeypatch.setattr(
        "research.guardian_research.pipeline.publish_snapshot",
        lambda root, session: published.append((Path(root), session)) or "GITHUB_OK",
    )
    result = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert result["remote"] == "GITHUB_OK"
    assert published == [(tmp_path, SESSION)]
    view = read_performance_view()
    assert view["session"] == "2026-10-30"
    assert view["observation_origin"] == "BACKFILLED"
    assert view["snapshot_sha256"] == BACKFILL_HASH
    assert view["counts"] == {"HOLD": 16, "SELL": 54, "UNAVAILABLE": 0, "WATCH": 73}


def test_schedule_is_isolated_and_the_ledger_workflow_is_unchanged():
    root = Path(__file__).resolve().parents[1]
    guardian = root.joinpath(".github", "workflows", "guardian-close.yml").read_text(encoding="utf-8")
    ledger = root.joinpath(".github", "workflows", "post-close-research.yml").read_text(encoding="utf-8")
    assert 'cron: "30 12 * * 1-5"' in guardian
    assert "vars.GUARDIAN_RESEARCH_SNAPSHOT_ENABLED == 'true'" in guardian
    assert "python -m research.guardian_research.close_job" in guardian
    assert "post_close_finalize" not in guardian
    assert "POST_CLOSE_RESEARCH_ENABLED" not in guardian
    assert 'cron: "30 11 * * 1-5"' in ledger
    assert 'cron: "30 13 * * 1-5"' in ledger
    assert "vars.POST_CLOSE_RESEARCH_ENABLED == 'true'" in ledger
    assert "python -m modules.post_close_finalize" in ledger
    source = root.joinpath("modules", "post_close_finalize.py").read_text(encoding="utf-8")
    assert "AUTHORITY_NOT_READY" in source
    assert "authority_ready" in source
    position = root.joinpath("position_guardian.py").read_text(encoding="utf-8")
    assert "def generate_signal" in position

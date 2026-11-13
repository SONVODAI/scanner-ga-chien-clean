"""Guardian close is isolated from Research Ledger finalization."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

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


def _witness(day=SESSION):
    return {"source": "vnindex_daily_bar", "bar_session": day, "probe_error": None}


def _run(*args, **kwargs):
    kwargs.setdefault("witness", _witness())
    return run_guardian_close(*args, **kwargs)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    if not path.exists():
        return ""
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file.relative_to(path).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


@pytest.fixture(autouse=True)
def production_research_data_stays_put():
    root = Path(__file__).resolve().parents[1]
    watched = (
        root / "data" / "earning_learning" / "t0_observation_freeze.csv",
        root / "data" / "guardian_research" / "sessions",
    )
    before = {path: _digest(path) for path in watched}
    yield
    after = {path: _digest(path) for path in watched}
    assert after == before


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
    result = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
        project_root=tmp_path / "freeze",
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
    assert "update_learning" not in source


def test_default_scan_does_not_retain_research_ledgers(monkeypatch, tmp_path: Path):
    seen = {}

    def build(**kwargs):
        seen.update(kwargs)
        return _payload(("HPG",))

    monkeypatch.setattr("modules.close_session_scan.build_close_scan_inputs", build)
    _enable(monkeypatch)
    _local_only(monkeypatch)
    result = _run(now=EVENING, root=tmp_path, symbols=("HPG",), project_root=tmp_path / "freeze")
    assert result["status"] == "created"
    assert seen["retain_research"] is False
    assert seen["now"] == EVENING


def test_flag_off_does_not_scan(monkeypatch):
    monkeypatch.delenv("GUARDIAN_RESEARCH_SNAPSHOT_ENABLED", raising=False)
    called = []
    result = _run(close_scan=lambda: called.append("scan") or _payload(("HPG",)))
    assert result["status"] == "disabled"
    assert result["reason"] == "ENABLE_FLAG_OFF"
    assert called == []


def test_observed_at_and_vnindex_witness_are_required(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    missing_clock = _payload(("HPG",))
    del missing_clock["observed_at"]
    missing_clock["saved_at"] = "2026-11-06T21:10:01+07:00"
    saved = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: missing_clock,
        symbols=("HPG",),
    )
    assert saved["reason"] == "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"
    assert not (tmp_path / "sessions").exists()

    early = _payload(("HPG",), observed_at="2026-11-06T17:59:00+07:00")
    too_soon = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: early,
        symbols=("HPG",),
    )
    assert too_soon["reason"] == "BEFORE_CANONICAL_WINDOW"

    closed = _payload(("HPG",))
    closed["trading_today"] = False
    closed["trading_reason"] = "VNINDEX mới nhất là 2026-11-05, không phải 2026-11-06"
    # Accepted VNINDEX bar for the session overrides a false clock-day flag.
    aligned = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: closed,
        symbols=("HPG",),
        project_root=tmp_path / "freeze",
    )
    assert aligned["status"] == "created"
    assert aligned["session"] == SESSION
    assert read_snapshot(Path(aligned["path"]))["session_witness"]["bar_session"] == SESSION

    from research.guardian_research.pipeline import capture_from_close_payload

    no_bar = _payload(("HPG",))
    no_bar["trading_today"] = False
    no_bar["trading_reason"] = "VNINDEX mới nhất là 2026-11-05, không phải 2026-11-06"
    refused = capture_from_close_payload(
        no_bar,
        now=EVENING,
        root=tmp_path / "no_bar",
        symbols=("HPG",),
    )
    assert refused["reason"] == "NON_TRADING_SESSION"
    assert not (tmp_path / "no_bar" / "sessions").exists()


def test_partial_stale_and_incomplete_143_payloads_are_refused(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    tracked = load_tracked_symbols()
    assert len(tracked) == 143
    partial = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(tracked, absent=("HPG",)),
        symbols=tracked,
        project_root=tmp_path / "no-freeze",
    )
    assert partial["reason"] == "PARTIAL_SCAN"

    stale = _payload(("HPG",), day="2026-11-05")
    stale["trade_date"] = SESSION
    stale["scan_df"] = pd.DataFrame([_row("HPG", day="2026-11-05")])
    refused = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: stale,
        symbols=("HPG",),
    )
    assert refused["reason"] == "STALE_MARKET_DATA"

    blank = _payload(("HPG",))
    blank["scan_df"] = pd.DataFrame([_row("HPG", obv=None)])
    incomplete = _run(
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
    first = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
        project_root=tmp_path / "freeze",
    )
    assert first["status"] == "created"
    assert first["tracked_count"] == 1
    stored = read_snapshot(Path(first["path"]))
    assert stored["content_sha256"] == first["content_sha256"]
    before = Path(first["path"]).read_bytes()

    again = _run(
        now=datetime(2026, 11, 6, 20, 0, tzinfo=VN),
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert again["status"] == "unchanged"
    assert again["content_sha256"] == first["content_sha256"]
    assert Path(first["path"]).read_bytes() == before

    # Conflicting rewrite is refused by the capture path without mutating bytes.
    from research.guardian_research.pipeline import capture_from_close_payload

    conflict = capture_from_close_payload(
        _payload(("HPG",), price=99),
        now=datetime(2026, 11, 6, 20, 5, tzinfo=VN),
        root=tmp_path,
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
    result = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
        project_root=tmp_path / "freeze",
    )
    assert result["remote"] == "GITHUB_OK"
    assert published == [(tmp_path, SESSION)]
    view = read_performance_view()
    assert view["session"] == "2026-10-30"
    assert view["observation_origin"] == "BACKFILLED"
    assert view["snapshot_sha256"] == BACKFILL_HASH
    assert view["counts"] == {"HOLD": 16, "SELL": 54, "UNAVAILABLE": 0, "WATCH": 73}


def test_vnindex_bar_names_the_session_and_a_mixed_scan_is_refused(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    seen = {}

    def probe(session):
        seen["search_end"] = session
        return _witness(SESSION)

    monkeypatch.setattr("research.guardian_research.close_job.probe_vnindex", probe)
    mislabeled = _payload(("HPG",))
    mislabeled["trade_date"] = "2026-11-10"
    sealed = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: mislabeled,
        symbols=("HPG",),
        project_root=tmp_path / "freeze",
    )
    assert seen["search_end"] == SESSION
    assert sealed["status"] == "created"
    assert sealed["session"] == SESSION
    stored = read_snapshot(Path(sealed["path"]))
    assert stored["session_witness"]["bar_session"] == SESSION
    assert stored["session_witness"]["source"] == "vnindex_daily_bar"
    assert stored["session_witness"]["provenance"].endswith("probe_vnindex")
    assert stored["classification_version"].startswith("position_guardian.generate_signal:")
    assert stored["reconstruction"]["timestamp_provenance"] == "close_scan.observed_at"
    assert stored["tracked_count"] == 1
    reread = read_snapshot(Path(sealed["path"]))
    assert reread["content_sha256"] == stored["content_sha256"]

    stale_bar = run_guardian_close(
        now=EVENING,
        root=tmp_path / "other",
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
        witness=_witness("2026-11-05"),
    )
    # Prior-day bar is outside the seal window for that session.
    assert stale_bar["reason"] == "SCHEDULE_TOO_LATE"
    assert not (tmp_path / "other" / "sessions").exists()

    mixed = _payload(("HPG", "SSI"))
    mixed["scan_df"] = pd.DataFrame([_row("HPG"), _row("SSI", day="2026-11-05")])
    mixed["scan_coverage"]["returned"] = ["HPG", "SSI"]
    refused = _run(
        now=EVENING,
        root=tmp_path / "mixed",
        close_scan=lambda: mixed,
        symbols=("HPG", "SSI"),
    )
    assert refused["reason"] == "MIXED_SESSION"
    assert not (tmp_path / "mixed" / "sessions").exists()

    unavailable = run_guardian_close(
        now=EVENING,
        root=tmp_path / "adapter",
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
        witness={"source": "vnindex_daily_bar", "bar_session": "", "probe_error": "ADAPTER_UNAVAILABLE"},
    )
    assert unavailable["reason"] == "WITNESS_ADAPTER_UNAVAILABLE"
    assert not (tmp_path / "adapter" / "sessions").exists()

    from research.guardian_research.pipeline import capture_from_close_payload

    mismatched = _payload(("HPG",))
    mismatched["session_witness"] = _witness("2026-11-05")
    blocked = capture_from_close_payload(
        mismatched,
        now=EVENING,
        root=tmp_path / "mismatch",
        symbols=("HPG",),
    )
    assert blocked["reason"] == "BAR_SESSION_MISMATCH"
    assert not (tmp_path / "mismatch" / "sessions").exists()


def test_delayed_cross_midnight_seal_preserves_observed_at(monkeypatch, tmp_path: Path):
    """After midnight the freeze clock stays the observation time. There is no rescan."""
    _enable(monkeypatch)
    _local_only(monkeypatch)
    morning = datetime(2026, 11, 7, 5, 35, tzinfo=VN)
    project = tmp_path / "repo"
    _write_agreed_freeze(project, ("HPG",), frozen_at=OBSERVED)
    scans = []

    def refuse_scan():
        scans.append("scan")
        raise AssertionError("delayed sealing must not rescan")

    sealed = _run(
        now=morning,
        root=tmp_path / "seal",
        close_scan=refuse_scan,
        symbols=("HPG",),
        project_root=project,
    )
    assert sealed["status"] == "created"
    assert scans == []
    stored = read_snapshot(Path(sealed["path"]))
    assert stored["session"] == SESSION
    assert stored["observation_origin"] == "DELAYED"
    assert stored["reconstruction"]["observation_at"] == OBSERVED
    assert stored["reconstruction"]["sealed_at"] == morning.isoformat()
    assert stored["reconstruction"]["timestamp_provenance"] == "close_scan.observed_at"
    assert stored["session_witness"]["bar_session"] == SESSION
    before = Path(sealed["path"]).read_bytes()

    again = _run(
        now=datetime(2026, 11, 7, 6, 0, tzinfo=VN),
        root=tmp_path / "seal",
        close_scan=refuse_scan,
        symbols=("HPG",),
        project_root=project,
    )
    assert again["status"] == "unchanged"
    assert again["content_sha256"] == sealed["content_sha256"]
    assert Path(sealed["path"]).read_bytes() == before
    assert scans == []


def test_schedule_too_late_and_mismatched_observation_are_refused(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    too_late = _run(
        now=datetime(2026, 11, 7, 9, 0, tzinfo=VN),
        root=tmp_path / "late",
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert too_late["status"] == "refused"
    assert too_late["reason"] == "SCHEDULE_TOO_LATE"
    assert too_late["session"] == SESSION
    assert not (tmp_path / "late" / "sessions").exists()

    scans = []
    refused = _run(
        now=datetime(2026, 11, 7, 5, 40, tzinfo=VN),
        root=tmp_path / "obs",
        close_scan=lambda: scans.append("scan") or _payload(("HPG",), observed_at="2026-11-07T05:35:00+07:00"),
        symbols=("HPG",),
        project_root=tmp_path / "no-freeze",
    )
    assert scans == []
    assert refused["reason"] == "FREEZE_ABSENT"
    assert not (tmp_path / "obs" / "sessions").exists()

    from research.guardian_research.pipeline import capture_from_close_payload

    morning_clock = _payload(("HPG",), observed_at="2026-11-07T05:35:00+07:00")
    morning_clock["trading_today"] = False
    morning_clock["session_witness"] = _witness(SESSION)
    blocked = capture_from_close_payload(
        morning_clock,
        now=datetime(2026, 11, 7, 5, 40, tzinfo=VN),
        root=tmp_path / "morning-clock",
        symbols=("HPG",),
    )
    assert blocked["reason"] == "SCHEDULE_TOO_LATE"
    assert not (tmp_path / "morning-clock" / "sessions").exists()

    stale_rows = _payload(("HPG",), day="2026-11-05")
    stale = _run(
        now=EVENING,
        root=tmp_path / "stale",
        close_scan=lambda: stale_rows,
        symbols=("HPG",),
        witness=_witness(SESSION),
    )
    assert stale["reason"] == "STALE_MARKET_DATA"
    assert not (tmp_path / "stale" / "sessions").exists()

    missing = run_guardian_close(
        now=EVENING,
        root=tmp_path / "missing",
        close_scan=lambda: _payload(("HPG",)),
        symbols=("HPG",),
        witness={"source": "vnindex_daily_bar", "bar_session": "", "probe_error": "NO_BAR"},
    )
    assert missing["reason"] == "SESSION_EVIDENCE_ABSENT"
    assert not (tmp_path / "missing" / "sessions").exists()


def test_empty_close_scan_refuses_exits_nonzero_and_writes_no_t0(monkeypatch, tmp_path: Path, capsys):
    """An empty scan stays a refusal. It must not become a seal."""
    root = Path(__file__).resolve().parents[1]
    sealed = root / "data" / "guardian_research" / "sessions" / "2026-11-06.json"
    outcomes = root / "research" / "guardian_research" / "outcomes.json"
    gap = root / "data" / "guardian_research" / "gaps" / "2026-11-09.json"
    before_seal = sealed.read_bytes()
    before_outcomes = outcomes.read_bytes()
    before_gap = gap.read_bytes()
    _enable(monkeypatch)
    _local_only(monkeypatch)
    refused = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: {
            "ok": False,
            "status": "CLOSE_SCAN_EMPTY",
            "trade_date": SESSION,
            "scan_df": pd.DataFrame(),
        },
        symbols=("HPG",),
    )
    assert refused["status"] == "refused"
    assert refused["reason"] == "CLOSE_SCAN_EMPTY"
    assert refused["path"] is None
    assert list(tmp_path.rglob("*.json")) == []

    monkeypatch.setattr(
        "research.guardian_research.close_job.run_guardian_close",
        lambda: refused,
    )
    monkeypatch.setattr(
        "research.guardian_research.outcomes.refresh_outcomes",
        lambda: {"status": "skipped", "reason": "test"},
    )
    from research.guardian_research.close_job import main

    assert main() == 1
    printed = capsys.readouterr().out
    assert '"status": "refused"' in printed
    assert "CLOSE_SCAN_EMPTY" in printed
    assert sealed.read_bytes() == before_seal
    assert outcomes.read_bytes() == before_outcomes
    assert gap.read_bytes() == before_gap


def test_hard_gap_marker_for_2026_11_09_does_not_touch_existing_t0():
    root = Path(__file__).resolve().parents[1]
    sessions = root / "data" / "guardian_research" / "sessions"
    gap = root / "data" / "guardian_research" / "gaps" / "2026-11-09.json"
    preserved = sessions / "2026-11-06.json"
    assert preserved.is_file()
    assert not (sessions / "2026-11-09.json").exists()
    assert gap.is_file()
    marker = json.loads(gap.read_text(encoding="utf-8"))
    assert marker["schema"] == "guardian_research_gap.v1"
    assert marker["session"] == "2026-11-09"
    assert marker["status"] == "HARD_GAP"
    assert marker["reconstructed_from_live_prices"] is False
    before = preserved.read_bytes()
    assert json.loads(before)["session"] == "2026-11-06"
    assert preserved.read_bytes() == before


def test_schedule_is_isolated_and_the_ledger_workflow_is_unchanged():
    root = Path(__file__).resolve().parents[1]
    guardian = root.joinpath(".github", "workflows", "guardian-close.yml").read_text(encoding="utf-8")
    ledger = root.joinpath(".github", "workflows", "post-close-research.yml").read_text(encoding="utf-8")
    assert 'cron: "30 12 * * 1-5"' in guardian
    assert 'cron: "30 14 * * 1-5"' in guardian
    assert 'cron: "30 15 * * 1-5"' in guardian
    assert "19:30 ICT = 12:30 UTC" in guardian
    assert "21:30 ICT = 14:30 UTC" in guardian
    assert "22:30 ICT = 15:30 UTC" in guardian
    assert "group: guardian-research-close" in guardian
    assert "cancel-in-progress: false" in guardian
    assert "Publish seal outcome" in guardian
    assert "GITHUB_STEP_SUMMARY" in guardian
    assert "contents: write" in guardian
    assert "secrets.GITHUB_TOKEN" in guardian
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
    live = root.joinpath("research", "guardian_research", "live.py").read_text(encoding="utf-8")
    assert "The returned document is not a T0 snapshot" in live


def test_same_evening_retry_crons_map_ict_to_utc_without_dst():
    """ICT is fixed UTC+7. Backup slots stay before ICT midnight."""
    from datetime import datetime, timedelta, timezone

    ict = timezone(timedelta(hours=7))
    expected = {
        "30 12 * * 1-5": datetime(2026, 11, 10, 19, 30, tzinfo=ict),
        "30 14 * * 1-5": datetime(2026, 11, 10, 21, 30, tzinfo=ict),
        "30 15 * * 1-5": datetime(2026, 11, 10, 22, 30, tzinfo=ict),
    }
    root = Path(__file__).resolve().parents[1]
    guardian = root.joinpath(".github", "workflows", "guardian-close.yml").read_text(encoding="utf-8")
    for cron, local in expected.items():
        assert f'cron: "{cron}"' in guardian
        minute, hour, *_ = cron.split()
        utc = local.astimezone(timezone.utc)
        assert utc.minute == int(minute)
        assert utc.hour == int(hour)
        assert utc.tzname() == "UTC"
        assert local.hour < 24
        assert local.date() == datetime(2026, 11, 10, tzinfo=ict).date()


def test_backup_slot_is_idempotent_and_does_not_mutate_an_existing_seal(monkeypatch, tmp_path: Path):
    """A later same-evening retry must keep the first immutable snapshot bytes."""
    _enable(monkeypatch)
    _local_only(monkeypatch)
    scans = []
    first = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: scans.append("primary") or _payload(("HPG",)),
        symbols=("HPG",),
        project_root=tmp_path / "freeze",
    )
    assert first["status"] == "created"
    before = Path(first["path"]).read_bytes()
    backup = _run(
        now=datetime(2026, 11, 6, 21, 30, tzinfo=VN),
        root=tmp_path,
        close_scan=lambda: scans.append("21:30") or _payload(("HPG",), price=99),
        symbols=("HPG",),
    )
    assert backup["status"] == "unchanged"
    assert backup["content_sha256"] == first["content_sha256"]
    assert Path(first["path"]).read_bytes() == before
    late_backup = _run(
        now=datetime(2026, 11, 6, 22, 30, tzinfo=VN),
        root=tmp_path,
        close_scan=lambda: scans.append("22:30") or _payload(("HPG",), price=12),
        symbols=("HPG",),
    )
    assert late_backup["status"] == "unchanged"
    assert Path(first["path"]).read_bytes() == before
    # Existing seal must be detected before any backup rescan/write.
    assert scans == ["primary"]


def test_backup_skips_scan_when_remote_seal_exists(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    sealed = {
        "schema": "guardian_research_snapshot.v1",
        "session": SESSION,
        "content_sha256": "abc123",
        "tracked_count": 1,
        "counts": {"HOLD": 1, "SELL": 0, "WATCH": 0, "UNAVAILABLE": 0},
    }
    monkeypatch.setattr(
        "research.guardian_research.pipeline.read_remote_snapshot",
        lambda _root, session: (sealed, "present") if session == SESSION else (None, "absent"),
    )
    monkeypatch.setattr(
        "research.guardian_research.pipeline.publish_snapshot",
        lambda _root, _session: (_ for _ in ()).throw(AssertionError("must not publish")),
    )
    scans = []
    result = _run(
        now=datetime(2026, 11, 6, 21, 30, tzinfo=VN),
        root=tmp_path,
        close_scan=lambda: scans.append("scan") or _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert result["status"] == "unchanged"
    assert result["content_sha256"] == "abc123"
    assert result["remote"] == "unchanged"
    assert scans == []
    assert not (tmp_path / "sessions").exists()


def test_primary_failure_then_backup_success_and_late_start_refuses(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    scans = []
    failed = _run(
        now=EVENING,
        root=tmp_path / "primary",
        close_scan=lambda: scans.append("fail") or _payload(("HPG",), absent=("HPG",)),
        symbols=("HPG",),
    )
    assert failed["reason"] == "PARTIAL_SCAN"
    assert not (tmp_path / "primary" / "sessions").exists()

    success = _run(
        now=datetime(2026, 11, 6, 21, 30, tzinfo=VN),
        root=tmp_path / "backup",
        close_scan=lambda: scans.append("backup") or _payload(("HPG",)),
        symbols=("HPG",),
        project_root=tmp_path / "backup-freeze",
    )
    assert success["status"] == "created"
    stored = read_snapshot(Path(success["path"]))
    assert stored["session"] == SESSION
    assert stored["session_witness"]["bar_session"] == SESSION
    assert stored["reconstruction"]["observation_at"] == OBSERVED
    assert stored["tracked_count"] == 1

    late = _run(
        now=datetime(2026, 11, 7, 9, 0, tzinfo=VN),
        root=tmp_path / "late",
        close_scan=lambda: scans.append("late") or _payload(("HPG",)),
        symbols=("HPG",),
    )
    assert late["reason"] == "SCHEDULE_TOO_LATE"
    assert "late" not in scans
    assert scans == ["fail", "backup"]


def test_full_universe_backup_requires_143_and_rejects_partial(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    tracked = load_tracked_symbols()
    assert len(tracked) == 143
    ok = _run(
        now=datetime(2026, 11, 6, 21, 30, tzinfo=VN),
        root=tmp_path / "full",
        close_scan=lambda: _payload(tracked),
        symbols=tracked,
        project_root=tmp_path / "full-freeze",
    )
    assert ok["status"] == "created"
    assert ok["tracked_count"] == 143
    document = read_snapshot(Path(ok["path"]))
    assert document["session_witness"]["bar_session"] == SESSION
    assert len(document["rows"]) == 143

    partial = _run(
        now=datetime(2026, 11, 6, 22, 30, tzinfo=VN),
        root=tmp_path / "partial",
        close_scan=lambda: _payload(tracked, absent=("HPG",)),
        symbols=tracked,
        project_root=tmp_path / "no-freeze",
    )
    assert partial["reason"] == "PARTIAL_SCAN"
    assert not (tmp_path / "partial" / "sessions").exists()


def _write_agreed_freeze(
    project: Path,
    symbols: tuple[str, ...],
    *,
    session: str = SESSION,
    frozen_at: str = OBSERVED,
    market_real: float = 6.5,
    blank: tuple[str, str] | None = None,
) -> None:
    """Write a stamped freeze. Observations are not the delayed-seal authority."""
    from research.guardian_research.freeze_witness import PROVENANCE, WITNESS_SOURCE, witness_digest

    rows = []
    for symbol in symbols:
        row = {
            "trade_date": session,
            "symbol": symbol,
            "observation_id": f"{session}:{symbol}",
            "frozen_at": frozen_at,
            "market_real": market_real,
            "price": 26.0,
            "ema9": 25.0,
            "ma20": 24.0,
            "obv": 1000.0,
            "obv_ema9": 900.0,
        }
        if blank is not None and symbol == blank[0]:
            row[blank[1]] = ""
        rows.append(row)
    folder = Path(project) / "data" / "earning_learning"
    folder.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    digest = witness_digest(
        session=session,
        frozen_at=frozen_at,
        source=WITNESS_SOURCE,
        bar_session=session,
        rows=frame,
    )
    if digest:
        frame["guardian_witness_source"] = WITNESS_SOURCE
        frame["guardian_witness_bar_session"] = session
        frame["guardian_witness_provenance"] = PROVENANCE
        frame["guardian_witness_sha256"] = digest
    frame.to_csv(folder / "t0_observation_freeze.csv", index=False)
    observations = frame.drop(
        columns=["frozen_at", "guardian_witness_source", "guardian_witness_bar_session", "guardian_witness_provenance", "guardian_witness_sha256"],
        errors="ignore",
    )
    observations.to_csv(folder / "observations.csv", index=False)


def _repo_session_bytes() -> dict[str, bytes]:
    root = Path(__file__).resolve().parents[1] / "data" / "guardian_research" / "sessions"
    return {path.name: path.read_bytes() for path in sorted(root.glob("*.json"))}


def test_same_evening_complete_scan_is_contemporaneous(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    payload = _payload(("HPG",), observed_at=EVENING.isoformat())
    sealed = _run(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: payload,
        symbols=("HPG",),
        project_root=tmp_path / "freeze",
    )
    assert sealed["status"] == "created"
    stored = read_snapshot(Path(sealed["path"]))
    assert stored["observation_origin"] == "CONTEMPORANEOUS"
    assert stored["reconstruction"]["observation_at"] == EVENING.isoformat()
    assert stored["reconstruction"]["sealed_at"] == EVENING.isoformat()
    assert stored["session_witness"]["bar_session"] == SESSION
    assert stored["tracked_count"] == 1


def test_delayed_freeze_seals_before_0900_and_keeps_the_original_clock(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    before = _repo_session_bytes()
    assert "2026-11-06.json" in before
    assert "2026-11-11.json" in before
    morning = datetime(2026, 11, 7, 8, 30, tzinfo=VN)
    project = tmp_path / "repo"
    _write_agreed_freeze(project, ("HPG", "FPT"), frozen_at=OBSERVED)
    # A mutable money snapshot must not be consulted, even when it disagrees.
    snap = project / "data"
    snap.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"snapshot_date": SESSION, "symbol": "HPG", "price": 1, "market_real": 0}]
    ).to_csv(snap / "earning_money_snapshots.csv", index=False)
    monkeypatch.setattr(
        "modules.close_session_scan.build_close_scan_inputs",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("delayed sealing must not rescan")),
    )
    sealed = run_guardian_close(
        now=morning,
        root=tmp_path / "seal",
        symbols=("HPG", "FPT"),
        witness=_witness(SESSION),
        project_root=project,
    )
    assert sealed["status"] == "created"
    assert sealed["tracked_count"] == 2
    stored = read_snapshot(Path(sealed["path"]))
    assert stored["observation_origin"] == "DELAYED"
    assert stored["reconstruction"]["observation_at"] == OBSERVED
    assert stored["reconstruction"]["sealed_at"] == morning.isoformat()
    assert stored["reconstruction"]["observation_at"] != stored["reconstruction"]["sealed_at"]
    assert stored["session_witness"]["bar_session"] == SESSION
    assert stored["session_witness"]["source"] == "vnindex_daily_bar"
    assert {row["symbol"] for row in stored["rows"]} == {"HPG", "FPT"}
    assert _repo_session_bytes() == before


def test_delayed_seal_is_refused_at_0900_even_with_a_valid_freeze(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    project = tmp_path / "repo"
    _write_agreed_freeze(project, ("HPG",))
    calls = []
    monkeypatch.setattr(
        "research.guardian_research.scan_archive.load_agreed_freeze",
        lambda *_args, **_kwargs: calls.append("freeze") or {"ok": True},
    )
    refused = _run(
        now=datetime(2026, 11, 7, 9, 0, tzinfo=VN),
        root=tmp_path / "late",
        close_scan=lambda: calls.append("scan") or _payload(("HPG",)),
        symbols=("HPG",),
        project_root=project,
    )
    assert refused["status"] == "refused"
    assert refused["reason"] == "SCHEDULE_TOO_LATE"
    assert calls == []
    assert not (tmp_path / "late" / "sessions").exists()


def test_missing_or_incomplete_freeze_is_refused_without_a_rescan(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    morning = datetime(2026, 11, 7, 8, 0, tzinfo=VN)
    scans = []
    missing = _run(
        now=morning,
        root=tmp_path / "missing",
        close_scan=lambda: scans.append("scan") or _payload(("HPG",)),
        symbols=("HPG",),
        project_root=tmp_path / "empty",
    )
    assert missing["reason"] == "FREEZE_ABSENT"
    assert scans == []
    assert not (tmp_path / "missing" / "sessions").exists()

    tracked = load_tracked_symbols()
    assert len(tracked) == 143
    incomplete_root = tmp_path / "incomplete"
    _write_agreed_freeze(incomplete_root, tracked[:-1])
    incomplete = _run(
        now=morning,
        root=tmp_path / "incomplete-seal",
        close_scan=lambda: scans.append("scan") or _payload(tracked),
        symbols=tracked,
        project_root=incomplete_root,
    )
    assert incomplete["reason"] == "INCOMPLETE_INPUT"
    assert scans == []
    assert not (tmp_path / "incomplete-seal" / "sessions").exists()

    blank_root = tmp_path / "blank"
    _write_agreed_freeze(blank_root, ("HPG",), blank=("HPG", "ema9"))
    blank = _run(
        now=morning,
        root=tmp_path / "blank-seal",
        close_scan=lambda: scans.append("scan"),
        symbols=("HPG",),
        project_root=blank_root,
    )
    assert blank["reason"] == "INCOMPLETE_INPUT"
    assert scans == []


def test_wrong_session_date_and_invalid_witness_are_refused(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    morning = datetime(2026, 11, 7, 8, 0, tzinfo=VN)
    project = tmp_path / "repo"
    _write_agreed_freeze(project, ("HPG",), frozen_at="2026-11-05T19:40:00+07:00")
    calls = []
    stale = _run(
        now=morning,
        root=tmp_path / "stale",
        close_scan=lambda: calls.append("scan"),
        symbols=("HPG",),
        project_root=project,
    )
    assert stale["reason"] == "STALE_FREEZE"
    assert calls == []
    assert not (tmp_path / "stale" / "sessions").exists()

    other_day = tmp_path / "other-day"
    _write_agreed_freeze(other_day, ("HPG",), session="2026-11-05", frozen_at="2026-11-05T19:40:00+07:00")
    mismatched = _run(
        now=morning,
        root=tmp_path / "mismatch",
        close_scan=lambda: calls.append("scan"),
        symbols=("HPG",),
        project_root=other_day,
    )
    assert mismatched["reason"] == "FREEZE_ABSENT"
    assert not (tmp_path / "mismatch" / "sessions").exists()

    probes = []
    monkeypatch.setattr(
        "research.guardian_research.close_job.probe_vnindex",
        lambda _session: probes.append("probe"),
    )
    invalid = run_guardian_close(
        now=morning,
        root=tmp_path / "witness",
        close_scan=lambda: calls.append("scan"),
        symbols=("HPG",),
        witness={"source": "vnindex_daily_bar", "bar_session": "", "probe_error": "NO_BAR"},
        project_root=project,
    )
    # Before 09:00 the live witness is not consulted. The freeze clock is.
    assert invalid["reason"] == "STALE_FREEZE"
    assert probes == []
    assert calls == []
    assert not (tmp_path / "witness" / "sessions").exists()


def test_pre_1800_freeze_does_not_seal_and_leaves_sealed_sessions(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    before_sessions = _repo_session_bytes()
    morning = datetime(2026, 11, 7, 8, 0, tzinfo=VN)
    project = tmp_path / "early"
    _write_agreed_freeze(project, ("HPG",), frozen_at="2026-11-06T17:08:00+07:00")
    freeze_path = project / "data" / "earning_learning" / "t0_observation_freeze.csv"
    freeze_before = freeze_path.read_bytes()
    calls = []
    refused = _run(
        now=morning,
        root=tmp_path / "seal",
        close_scan=lambda: calls.append("scan"),
        symbols=("HPG",),
        project_root=project,
    )
    assert refused["status"] == "refused"
    assert refused["reason"] == "STALE_FREEZE"
    assert calls == []
    assert not (tmp_path / "seal" / "sessions").exists()
    assert freeze_path.read_bytes() == freeze_before
    assert _repo_session_bytes() == before_sessions
    assert "2026-11-13.json" not in before_sessions


def test_same_evening_empty_scan_can_seal_a_qualified_freeze(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _local_only(monkeypatch)
    project = tmp_path / "repo"
    _write_agreed_freeze(project, ("HPG",), frozen_at=OBSERVED)
    scans = []
    sealed = _run(
        now=EVENING,
        root=tmp_path / "seal",
        close_scan=lambda: scans.append("scan")
        or {"ok": False, "status": "CLOSE_SCAN_EMPTY", "source": "close_scan"},
        symbols=("HPG",),
        project_root=project,
    )
    assert scans == ["scan"]
    assert sealed["status"] == "created"
    stored = read_snapshot(Path(sealed["path"]))
    assert stored["observation_origin"] == "DELAYED"
    assert stored["reconstruction"]["observation_at"] == OBSERVED
    assert stored["reconstruction"]["sealed_at"] == EVENING.isoformat()
    assert stored["reconstruction"]["observation_at"] != stored["reconstruction"]["sealed_at"]

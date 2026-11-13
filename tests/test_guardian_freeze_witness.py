"""First-write VNINDEX witness. Synthetic clocks, fake probe, no vnstock."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.earning_learning import _adapt_board
from modules.learning_t0_capture import append_t0_observation_freeze
from research.guardian_research.close_job import run_guardian_close
from research.guardian_research.freeze_witness import (
    verify_persisted_witness,
    witness_digest,
)
from research.guardian_research.snapshot import read_snapshot
from research.guardian_research.universe import load_tracked_symbols

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION = "2026-11-12"
FROZEN_AT = "2026-11-12T12:05:00Z"
MORNING = datetime(2026, 11, 13, 8, 30, tzinfo=VN)
EVENING = datetime(2026, 11, 12, 19, 30, tzinfo=VN)
ROOT = Path(__file__).resolve().parents[1]
PROTECTED = {
    "data/guardian_research/sessions/2026-11-06.json": "e512eaf590c188758fff5c6f3f925167b636d6e8",
    "data/guardian_research/sessions/2026-11-11.json": "13ec93f01fcb60bf554b77e868cdc98791a63c73",
    "research/v2_research_ledger/durable/identities.jsonl": "70479dacf795d4860d87e6ba718cf5c172180dba",
}


def _board(symbols: tuple[str, ...], session: str = SESSION, *, price: float = 26.0) -> pd.DataFrame:
    rows = []
    for offset, symbol in enumerate(symbols):
        rows.append(
            {
                "symbol": symbol,
                "trade_date": session,
                "price": price + offset,
                "ema9": 25.0,
                "ma20": 24.0,
                "obv": 1000.0 + offset,
                "obv_ema9": 900.0,
                "rsi14": 55.0,
                "group": "PULL ĐẸP",
            }
        )
    return _adapt_board(
        pd.DataFrame(rows),
        market_context={"market_real": 6.4, "market_score": 6.4, "market_live": 7.0},
    )


def _matching_probe(session: str) -> dict:
    return {"source": "vnindex_daily_bar", "bar_session": session, "probe_error": None}


def _enable(monkeypatch):
    monkeypatch.setenv("GUARDIAN_RESEARCH_SNAPSHOT_ENABLED", "true")
    monkeypatch.setattr(
        "research.guardian_research.pipeline.read_remote_snapshot",
        lambda _root, _session: (None, "absent"),
    )
    monkeypatch.setattr(
        "research.guardian_research.pipeline.publish_snapshot",
        lambda _root, _session: "created",
    )


def _freeze_clock(monkeypatch):
    monkeypatch.setattr("modules.learning_t0_capture._utc_now_iso", lambda: FROZEN_AT)


def _write_freeze(project: Path, frame: pd.DataFrame) -> None:
    folder = project / "data" / "earning_learning"
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / "t0_observation_freeze.csv", index=False)


def _git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def test_first_write_stamps_only_new_rows_and_a_rerun_does_not_probe(tmp_path: Path):
    calls = []

    def probe(session: str) -> dict:
        calls.append(session)
        return _matching_probe(session)

    first, added = append_t0_observation_freeze(
        pd.DataFrame(),
        _board(("HPG", "FPT")),
        brain_dir=tmp_path / "brain",
        witness_probe=probe,
    )
    assert added == 2
    assert calls == [SESSION]
    assert set(first["guardian_witness_bar_session"]) == {SESSION}
    assert first["guardian_witness_source"].eq("vnindex_daily_bar").all()
    assert first["guardian_witness_sha256"].nunique() == 1
    digest = witness_digest(
        session=SESSION,
        frozen_at=str(first["frozen_at"].iloc[0]),
        source="vnindex_daily_bar",
        bar_session=SESSION,
        rows=first,
    )
    assert digest == first["guardian_witness_sha256"].iloc[0]

    legacy = _board(("AAA",), session="2026-11-11")
    legacy["frozen_at"] = "2026-11-11T12:05:00Z"
    combined, more = append_t0_observation_freeze(
        legacy,
        _board(("HPG",), session=SESSION),
        brain_dir=tmp_path / "brain-legacy",
        witness_probe=probe,
    )
    assert more == 1
    old = combined[combined["symbol"] == "AAA"].iloc[0]
    assert pd.isna(old["guardian_witness_sha256"]) or str(old["guardian_witness_sha256"]) in {"", "nan"}
    assert float(old["price"]) == float(legacy.loc[legacy["symbol"] == "AAA", "price"].iloc[0])
    new = combined[combined["symbol"] == "HPG"].iloc[0]
    assert new["guardian_witness_bar_session"] == SESSION

    _again, none_added = append_t0_observation_freeze(
        first,
        _board(("HPG", "FPT"), price=99),
        brain_dir=tmp_path / "brain-rerun",
        witness_probe=probe,
    )
    assert none_added == 0
    assert calls == [SESSION, SESSION]
    assert float(_again.loc[_again["symbol"] == "HPG", "price"].iloc[0]) == 26.0


def test_probe_failure_and_mismatched_bar_append_blank_and_delay_refuses(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _freeze_clock(monkeypatch)
    monkeypatch.setattr(
        "research.guardian_research.close_job.probe_vnindex",
        lambda _session: (_ for _ in ()).throw(AssertionError("delayed sealing must not probe")),
    )

    def explode(_session):
        raise RuntimeError("vnstock down")

    failed, added = append_t0_observation_freeze(
        pd.DataFrame(),
        _board(("HPG",)),
        brain_dir=tmp_path / "fail-brain",
        witness_probe=explode,
    )
    assert added == 1
    assert failed["guardian_witness_source"].eq("").all()
    assert failed["guardian_witness_sha256"].eq("").all()
    project = tmp_path / "fail-repo"
    _write_freeze(project, failed)
    refused = run_guardian_close(
        now=MORNING,
        root=tmp_path / "fail-seal",
        close_scan=lambda: (_ for _ in ()).throw(AssertionError("must not scan")),
        symbols=("HPG",),
        witness={"source": "vnindex_daily_bar", "bar_session": "2099-01-01", "probe_error": None},
        project_root=project,
    )
    assert refused["status"] == "refused"
    assert refused["reason"] == "WITNESS_ABSENT"
    assert not (tmp_path / "fail-seal" / "sessions").exists()

    def wrong_day(session: str) -> dict:
        return {"source": "vnindex_daily_bar", "bar_session": "2026-11-11", "probe_error": None}

    mismatched, added = append_t0_observation_freeze(
        pd.DataFrame(),
        _board(("FPT",)),
        brain_dir=tmp_path / "mismatch-brain",
        witness_probe=wrong_day,
    )
    assert added == 1
    assert mismatched["guardian_witness_bar_session"].eq("").all()
    _write_freeze(tmp_path / "mismatch-repo", mismatched)
    mismatch = run_guardian_close(
        now=MORNING,
        root=tmp_path / "mismatch-seal",
        close_scan=lambda: (_ for _ in ()).throw(AssertionError("must not scan")),
        symbols=("FPT",),
        project_root=tmp_path / "mismatch-repo",
    )
    assert mismatch["reason"] == "WITNESS_ABSENT"
    assert not (tmp_path / "mismatch-seal" / "sessions").exists()


def test_hash_survives_csv_and_tamper_is_rejected(monkeypatch, tmp_path: Path):
    _freeze_clock(monkeypatch)
    stamped, added = append_t0_observation_freeze(
        pd.DataFrame(),
        _board(("HPG", "FPT")),
        brain_dir=tmp_path / "brain",
        witness_probe=_matching_probe,
    )
    assert added == 2
    path = tmp_path / "freeze.csv"
    stamped.to_csv(path, index=False)
    loaded = pd.read_csv(path)
    witness, reason = verify_persisted_witness(loaded, SESSION)
    assert reason is None
    assert witness["bar_session"] == SESSION
    assert witness["source"] == "vnindex_daily_bar"
    assert loaded["guardian_witness_sha256"].iloc[0] == stamped["guardian_witness_sha256"].iloc[0]

    tampered = loaded.copy()
    tampered.loc[tampered["symbol"] == "HPG", "ema9"] = 1.0
    _witness, integrity = verify_persisted_witness(tampered, SESSION)
    assert integrity == "WITNESS_INTEGRITY"

    bad_source = loaded.copy()
    bad_source["guardian_witness_source"] = "clock"
    _witness, invalid = verify_persisted_witness(bad_source, SESSION)
    assert invalid == "WITNESS_INVALID"

    bad_bar = loaded.copy()
    bad_bar["guardian_witness_bar_session"] = "2026-11-11"
    _witness, inconsistent = verify_persisted_witness(bad_bar, SESSION)
    assert inconsistent == "WITNESS_INCONSISTENT"


def test_rewritten_observations_do_not_block_a_delayed_seal(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    _freeze_clock(monkeypatch)
    monkeypatch.setattr(
        "research.guardian_research.close_job.probe_vnindex",
        lambda _session: (_ for _ in ()).throw(AssertionError("delayed sealing must not probe")),
    )
    stamped, _added = append_t0_observation_freeze(
        pd.DataFrame(),
        _board(("HPG", "FPT")),
        brain_dir=tmp_path / "brain",
        witness_probe=_matching_probe,
    )
    project = tmp_path / "repo"
    _write_freeze(project, stamped)
    rewritten = stamped.copy()
    rewritten["market_real"] = 9.9
    rewritten.loc[rewritten["symbol"] == "HPG", "ema9"] = 1.0
    rewritten.loc[rewritten["symbol"] == "HPG", "ma20"] = 2.0
    rewritten.loc[rewritten["symbol"] == "HPG", "obv"] = 3.0
    rewritten.loc[rewritten["symbol"] == "HPG", "obv_ema9"] = 4.0
    folder = project / "data" / "earning_learning"
    rewritten.drop(columns=["frozen_at"], errors="ignore").to_csv(folder / "observations.csv", index=False)

    sealed = run_guardian_close(
        now=MORNING,
        root=tmp_path / "seal",
        close_scan=lambda: (_ for _ in ()).throw(AssertionError("must not scan")),
        symbols=("HPG", "FPT"),
        witness={"source": "vnindex_daily_bar", "bar_session": "2099-01-01", "probe_error": None},
        project_root=project,
    )
    assert sealed["status"] == "created"
    stored = read_snapshot(Path(sealed["path"]))
    assert stored["observation_origin"] == "DELAYED"
    assert stored["session_witness"]["bar_session"] == SESSION
    assert stored["session_witness"]["source"] == "vnindex_daily_bar"
    assert stored["session_witness"]["bar_session"] != "2099-01-01"
    assert stored["market"]["market_real"] == 6.4
    hpg = next(row for row in stored["rows"] if row["symbol"] == "HPG")
    assert hpg["inputs"]["ema9"] == 25.0
    assert hpg["inputs"]["ma20"] == 24.0
    before = Path(sealed["path"]).read_bytes()

    again = run_guardian_close(
        now=datetime(2026, 11, 13, 8, 45, tzinfo=VN),
        root=tmp_path / "seal",
        close_scan=lambda: (_ for _ in ()).throw(AssertionError("must not scan")),
        symbols=("HPG", "FPT"),
        witness={"source": "vnindex_daily_bar", "bar_session": "1999-01-01", "probe_error": None},
        project_root=project,
    )
    assert again["status"] == "unchanged"
    assert again["content_sha256"] == sealed["content_sha256"]
    assert Path(sealed["path"]).read_bytes() == before


def test_legacy_and_2026_11_12_without_a_stamp_create_no_session_file(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    forbidden = ROOT / "data" / "guardian_research" / "sessions" / "2026-11-12.json"
    assert not forbidden.exists()
    rows = []
    for symbol in ("HPG", "FPT"):
        rows.append(
            {
                "trade_date": "2026-11-12",
                "symbol": symbol,
                "observation_id": f"2026-11-12:{symbol}",
                "frozen_at": "2026-11-12T19:05:00+07:00",
                "market_real": 6.4,
                "price": 26.0,
                "ema9": 25.0,
                "ma20": 24.0,
                "obv": 1000.0,
                "obv_ema9": 900.0,
            }
        )
    project = tmp_path / "legacy"
    _write_freeze(project, pd.DataFrame(rows))
    refused = run_guardian_close(
        now=MORNING,
        root=tmp_path / "seal",
        close_scan=lambda: (_ for _ in ()).throw(AssertionError("must not scan")),
        symbols=("HPG", "FPT"),
        project_root=project,
    )
    assert refused["status"] == "refused"
    assert refused["reason"] == "WITNESS_ABSENT"
    assert not (tmp_path / "seal" / "sessions").exists()
    assert not forbidden.exists()
    assert list(ROOT.glob("data/guardian_research/sessions/2026-11-12.json")) == []


def test_incomplete_143_symbol_batch_is_refused(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    tracked = load_tracked_symbols()
    assert len(tracked) == 143
    from tests.test_guardian_close_job import _write_agreed_freeze

    project = tmp_path / "repo"
    _write_agreed_freeze(project, tracked[:-1], session=SESSION, frozen_at="2026-11-12T19:05:00+07:00")
    refused = run_guardian_close(
        now=MORNING,
        root=tmp_path / "seal",
        close_scan=lambda: (_ for _ in ()).throw(AssertionError("must not scan")),
        symbols=tracked,
        project_root=project,
    )
    assert refused["reason"] == "INCOMPLETE_INPUT"
    assert not (tmp_path / "seal" / "sessions").exists()


def test_clock_at_0900_is_too_late_and_writes_nothing(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    from tests.test_guardian_close_job import _write_agreed_freeze

    project = tmp_path / "repo"
    _write_agreed_freeze(project, ("HPG",), session=SESSION, frozen_at="2026-11-12T19:05:00+07:00")
    calls = []
    monkeypatch.setattr(
        "research.guardian_research.scan_archive.load_agreed_freeze",
        lambda *_args, **_kwargs: calls.append("freeze") or {"ok": True},
    )
    refused = run_guardian_close(
        now=datetime(2026, 11, 13, 9, 0, tzinfo=VN),
        root=tmp_path / "late",
        close_scan=lambda: calls.append("scan"),
        symbols=("HPG",),
        witness={"source": "vnindex_daily_bar", "bar_session": SESSION, "probe_error": None},
        project_root=project,
    )
    assert refused["status"] == "refused"
    assert refused["reason"] == "SCHEDULE_TOO_LATE"
    assert refused["session"] == SESSION
    assert calls == []
    assert not (tmp_path / "late" / "sessions").exists()


def test_same_evening_fallback_does_not_substitute_a_live_probe(monkeypatch, tmp_path: Path):
    """A valid evening probe must not seal a freeze that has no stamp."""
    _enable(monkeypatch)
    rows = []
    for symbol in ("HPG",):
        rows.append(
            {
                "trade_date": SESSION,
                "symbol": symbol,
                "observation_id": f"{SESSION}:{symbol}",
                "frozen_at": "2026-11-12T19:05:00+07:00",
                "market_real": 6.4,
                "price": 26.0,
                "ema9": 25.0,
                "ma20": 24.0,
                "obv": 1000.0,
                "obv_ema9": 900.0,
            }
        )
    project = tmp_path / "repo"
    _write_freeze(project, pd.DataFrame(rows))
    pd.DataFrame(rows).drop(columns=["frozen_at"]).to_csv(
        project / "data" / "earning_learning" / "observations.csv",
        index=False,
    )
    refused = run_guardian_close(
        now=EVENING,
        root=tmp_path / "seal",
        close_scan=lambda: {"ok": False, "status": "CLOSE_SCAN_EMPTY", "source": "close_scan"},
        symbols=("HPG",),
        witness={"source": "vnindex_daily_bar", "bar_session": SESSION, "probe_error": None},
        project_root=project,
    )
    assert refused["status"] == "refused"
    assert not (tmp_path / "seal" / "sessions").exists()


def test_same_evening_complete_scan_stays_contemporaneous(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)

    def refuse_freeze(*_args, **_kwargs):
        raise AssertionError("a complete same-evening scan must not read the freeze")

    monkeypatch.setattr("research.guardian_research.scan_archive.load_agreed_freeze", refuse_freeze)
    payload = {
        "ok": True,
        "status": "READY",
        "source": "close_scan",
        "trade_date": SESSION,
        "market_real": 6.4,
        "trading_today": True,
        "trading_reason": f"VNINDEX có giao dịch hôm nay: {SESSION}",
        "observed_at": EVENING.isoformat(),
        "scan_df": pd.DataFrame(
            [
                {
                    "symbol": "HPG",
                    "date": SESSION,
                    "price": 26,
                    "ema9": 25,
                    "ma20": 24,
                    "obv": 1000,
                    "obv_ema9": 900,
                    "is_live_adjusted": False,
                }
            ]
        ),
        "scan_coverage": {
            "requested": ["HPG"],
            "returned": ["HPG"],
            "absent": [],
            "errors": [],
        },
    }
    sealed = run_guardian_close(
        now=EVENING,
        root=tmp_path,
        close_scan=lambda: payload,
        symbols=("HPG",),
        witness={"source": "vnindex_daily_bar", "bar_session": SESSION, "probe_error": None},
    )
    assert sealed["status"] == "created"
    stored = read_snapshot(Path(sealed["path"]))
    assert stored["observation_origin"] == "CONTEMPORANEOUS"
    assert stored["session_witness"]["bar_session"] == SESSION
    assert stored["reconstruction"]["observation_at"] == EVENING.isoformat()


def test_protected_blobs_and_classifier_files_are_unchanged():
    for relative, blob in PROTECTED.items():
        assert _git_blob(ROOT / relative) == blob
    forbidden = ROOT / "data" / "guardian_research" / "sessions" / "2026-11-12.json"
    assert not forbidden.exists()

"""Acceptance matrix for gated freeze writes and dispatch. No network and no production writes."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from modules.earning_learning import _csv_to_text, _hash_payload
from modules.learning_t0_capture import FreezeConflict, commit_qualified_freeze, qualify_t0_freeze_batch
from position_guardian import generate_signal
from research.guardian_research.classify import classification_version
from research.guardian_research.close_job import run_guardian_close
from research.guardian_research.pipeline import capture_from_close_payload
from research.guardian_research.snapshot import read_snapshot
from scripts.guardian_close_dispatch import dispatch_guardian_close
from tests.test_guardian_close_job import OBSERVED, _payload
from tests.test_guardian_freeze_witness import _board

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION = "2026-11-12"
FROZEN_AT = "2026-11-12T12:05:00Z"
EVENING = datetime(2026, 11, 12, 19, 30, tzinfo=VN)
ROOT = Path(__file__).resolve().parents[1]


def _probe(session: str) -> dict:
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


class _Remote:
    def __init__(self, folder: Path):
        self.github = type("GitHub", (), {"enabled": True})()
        self.local_dir = folder
        self.text = None
        self.sha = None
        self.conflicts = 0
        self.stored = []
        self.attempts = []

    def read_content_cas(self, _filename):
        return self.text, self.sha

    def write_content_cas_once(self, _filename, text, sha, _message):
        self.attempts.append(text)
        if self.conflicts:
            self.conflicts -= 1
            raise FreezeConflict("HTTP 409")
        if sha != self.sha:
            raise FreezeConflict("stale sha")
        self.text = text
        self.sha = "sha-stored"
        self.stored.append(text)

    def _local_path(self, name):
        return self.local_dir / name


def _historical(symbol: str, session: str, price: float, identity: str) -> str:
    frame = pd.DataFrame(
        [
            {
                "observation_id": identity,
                "symbol": symbol,
                "trade_date": session,
                "frozen_at": "2026-11-11T12:05:00Z",
                "market_real": 3.0,
                "price": price,
                "ema9": 2.0,
                "ma20": 1.0,
                "obv": 10.0,
                "obv_ema9": 9.0,
            }
        ]
    )
    return _csv_to_text(frame)


def test_pre_1800_batch_adds_nothing_and_keeps_stored_rows():
    existing = _board(("AAA",), session="2026-11-11")
    before = existing.copy()
    frame, added, reason = qualify_t0_freeze_batch(
        existing,
        _board(("HPG",)),
        witness_probe=_probe,
        frozen_at="2026-11-12T10:08:00+07:00",
        expected_symbols=("HPG",),
    )
    assert added == 0
    assert reason == "CLOCK_REJECTED"
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), before.reset_index(drop=True))


def test_incomplete_duplicate_and_partial_overlap_do_not_append():
    partial, added, reason = qualify_t0_freeze_batch(
        pd.DataFrame(),
        _board(("HPG",)),
        witness_probe=_probe,
        frozen_at=FROZEN_AT,
        expected_symbols=("HPG", "FPT"),
    )
    assert (added, reason) == (0, "INCOMPLETE_BATCH")
    assert partial.empty

    duplicated = _board(("HPG",))
    duplicated = pd.concat([duplicated, duplicated], ignore_index=True)
    _frame, added, reason = qualify_t0_freeze_batch(
        pd.DataFrame(),
        duplicated,
        witness_probe=_probe,
        frozen_at=FROZEN_AT,
        expected_symbols=("HPG",),
    )
    assert (added, reason) == (0, "DUPLICATE_BATCH")

    mixed = _board(("HPG", "FPT"))
    mixed.loc[mixed["symbol"] == "FPT", "market_real"] = 1.0
    _frame, added, reason = qualify_t0_freeze_batch(
        pd.DataFrame(),
        mixed,
        witness_probe=_probe,
        frozen_at=FROZEN_AT,
        expected_symbols=("HPG", "FPT"),
    )
    assert (added, reason) == (0, "INCONSISTENT_BATCH")

    stored, added, reason = qualify_t0_freeze_batch(
        pd.DataFrame(),
        _board(("HPG",)),
        witness_probe=_probe,
        frozen_at=FROZEN_AT,
        expected_symbols=("HPG",),
    )
    assert added == 1
    overlap, added, reason = qualify_t0_freeze_batch(
        stored,
        _board(("HPG", "FPT"), price=99),
        witness_probe=_probe,
        frozen_at=FROZEN_AT,
        expected_symbols=("HPG", "FPT"),
    )
    assert (added, reason) == (0, "PARTIAL_OVERLAP")
    assert set(overlap["symbol"]) == {"HPG"}
    assert float(overlap.loc[overlap["symbol"] == "HPG", "price"].iloc[0]) == 26.0


def test_conflict_rereads_and_does_not_replace_history(tmp_path: Path):
    remote = _Remote(tmp_path)
    remote.conflicts = 1
    remote.text = _historical("AAA", "2026-11-11", 1.5, "legacy-aaa")
    remote.sha = "sha-1"
    # The first attempt conflicts before the body is stored. The reread sees history.
    remote.conflicts = 1
    remote.text = None
    remote.sha = None

    def conflict_once(_filename, text, sha, _message):
        remote.attempts.append((text, sha))
        if remote.conflicts:
            remote.conflicts -= 1
            remote.text = _historical("AAA", "2026-11-11", 1.5, "legacy-aaa")
            remote.sha = "sha-2"
            raise FreezeConflict("HTTP 409")
        if sha != remote.sha:
            raise FreezeConflict("stale")
        remote.text = text
        remote.sha = "sha-3"
        remote.stored.append(text)

    remote.write_content_cas_once = conflict_once
    result = commit_qualified_freeze(
        remote,
        _board(("HPG",)),
        expected_symbols=("HPG",),
        witness_probe=_probe,
        frozen_at=FROZEN_AT,
    )
    assert result["ok"] is True
    assert result["added"] == 1
    assert len(remote.stored) == 1
    confirmed = result["frame"]
    assert float(confirmed.loc[confirmed["symbol"] == "AAA", "price"].iloc[0]) == 1.5
    assert set(confirmed["symbol"]) == {"AAA", "HPG"}
    assert "legacy-aaa" in set(confirmed["observation_id"].astype(str))


def test_conflict_keeps_a_concurrent_qualified_row(tmp_path: Path):
    identity = _hash_payload((SESSION, "HPG"))
    remote = _Remote(tmp_path)
    remote.text = None
    remote.sha = None
    remote.conflicts = 1

    def install_other(_filename, text, sha, _message):
        remote.attempts.append(text)
        if remote.conflicts:
            remote.conflicts -= 1
            remote.text = _historical("HPG", SESSION, 99.0, identity)
            remote.sha = "sha-other"
            raise FreezeConflict("HTTP 422")
        raise AssertionError("a conflicting id must not be uploaded again")

    remote.write_content_cas_once = install_other
    result = commit_qualified_freeze(
        remote,
        _board(("HPG",), price=26),
        expected_symbols=("HPG",),
        witness_probe=_probe,
        frozen_at=FROZEN_AT,
    )
    assert result["ok"] is True
    assert result["added"] == 0
    assert result["reason"] == "UNCHANGED"
    assert remote.stored == []
    assert float(result["frame"].loc[result["frame"]["symbol"] == "HPG", "price"].iloc[0]) == 99.0


def test_same_evening_seals_from_reread_freeze_and_is_idempotent(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    scans = []
    project = tmp_path / "repo"
    first = run_guardian_close(
        now=EVENING,
        root=tmp_path / "seal",
        close_scan=lambda: scans.append("scan") or _payload(("HPG",), observed_at=EVENING.isoformat(), day=SESSION),
        symbols=("HPG",),
        witness=_probe(SESSION),
        project_root=project,
    )
    assert first["status"] == "created"
    freeze_path = project / "data" / "earning_learning" / "t0_observation_freeze.csv"
    before = freeze_path.read_bytes()
    stored = read_snapshot(Path(first["path"]))
    row = stored["rows"][0]
    signal, _reason, score = generate_signal(
        pd.Series({"price": 26, "ema9": 25, "ma20": 24, "obv": 1000, "obv_ema9": 900})
    )
    assert row["production_signal"] == signal
    assert row["score"] == int(score)
    assert stored["classification_version"] == classification_version()
    assert row["inputs"]["ema9"] == 25.0
    second = run_guardian_close(
        now=datetime(2026, 11, 12, 20, 0, tzinfo=VN),
        root=tmp_path / "seal",
        close_scan=lambda: scans.append("again") or _payload(("HPG",), price=99, observed_at=EVENING.isoformat(), day=SESSION),
        symbols=("HPG",),
        witness=_probe(SESSION),
        project_root=project,
    )
    assert second["status"] == "unchanged"
    assert second["content_sha256"] == first["content_sha256"]
    assert freeze_path.read_bytes() == before
    assert scans == ["scan"]


def test_snapshot_conflict_keeps_the_sealed_bytes(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    project = tmp_path / "repo"
    first = run_guardian_close(
        now=EVENING,
        root=tmp_path / "seal",
        close_scan=lambda: _payload(("HPG",), observed_at=EVENING.isoformat(), day=SESSION),
        symbols=("HPG",),
        witness=_probe(SESSION),
        project_root=project,
    )
    before = Path(first["path"]).read_bytes()
    conflict = capture_from_close_payload(
        _payload(("HPG",), price=99, observed_at=EVENING.isoformat(), day=SESSION),
        now=datetime(2026, 11, 12, 20, 5, tzinfo=VN),
        root=tmp_path / "seal",
        symbols=("HPG",),
    )
    assert conflict["reason"] == "SNAPSHOT_CONFLICT"
    assert Path(first["path"]).read_bytes() == before


def test_dispatch_failures_are_explicit_and_token_stays_out_of_status(tmp_path: Path):
    token = "secret-token-value"
    status = tmp_path / "last.json"

    def rejected(method, url, headers, body):
        assert token not in url
        assert headers["Authorization"] == f"Bearer {token}"
        return 401, {"message": "bad credentials"}

    result = dispatch_guardian_close(
        token=token,
        repo="SONVODAI/scanner-ga-chien-clean",
        status_path=status,
        timeout_sec=0,
        transport=rejected,
        lock=False,
    )
    assert result["result"] == "TOKEN_REJECTED"
    assert token not in status.read_text(encoding="utf-8")

    def skipped(method, url, headers, body):
        if method == "POST":
            return 204, {}
        if url.endswith("/jobs/9"):
            return 200, {"jobs": [{"name": "guardian", "status": "completed", "conclusion": "skipped"}]}
        return 200, {
            "workflow_runs": [
                {
                    "id": 9,
                    "event": "workflow_dispatch",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "html_url": "https://example.test/run/9",
                    "jobs_url": "https://example.test/jobs/9",
                }
            ]
        }

    skipped_status = tmp_path / "skipped.json"
    result = dispatch_guardian_close(
        token=token,
        repo="SONVODAI/scanner-ga-chien-clean",
        status_path=skipped_status,
        timeout_sec=0,
        transport=skipped,
        lock=False,
    )
    assert result["result"] == "SKIPPED_JOB"
    assert token not in skipped_status.read_text(encoding="utf-8")

    def missing(method, url, headers, body):
        if method == "POST":
            return 204, {}
        return 200, {"workflow_runs": []}

    missing_status = tmp_path / "missing.json"
    result = dispatch_guardian_close(
        token=token,
        repo="SONVODAI/scanner-ga-chien-clean",
        status_path=missing_status,
        timeout_sec=0,
        transport=missing,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
        lock=False,
    )
    assert result["result"] == "MISSING_RUN"

    def pending(method, url, headers, body):
        if method == "POST":
            return 204, {}
        if url.endswith("/jobs/4"):
            return 200, {"jobs": []}
        return 200, {
            "workflow_runs": [
                {
                    "id": 4,
                    "event": "workflow_dispatch",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "html_url": "https://example.test/run/4",
                    "jobs_url": "https://example.test/jobs/4",
                }
            ]
        }

    timeout_status = tmp_path / "timeout.json"
    result = dispatch_guardian_close(
        token=token,
        repo="SONVODAI/scanner-ga-chien-clean",
        status_path=timeout_status,
        timeout_sec=0,
        transport=pending,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0,
        lock=False,
    )
    assert result["result"] == "TIMEOUT"

    def accepted(method, url, headers, body):
        if method == "POST":
            return 204, {}
        if url.endswith("/jobs/5"):
            return 200, {"jobs": [{"name": "guardian", "status": "queued", "conclusion": None}]}
        return 200, {
            "workflow_runs": [
                {
                    "id": 5,
                    "event": "workflow_dispatch",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "html_url": "https://example.test/run/5",
                    "jobs_url": "https://example.test/jobs/5",
                }
            ]
        }

    accepted_status = tmp_path / "accepted.json"
    result = dispatch_guardian_close(
        token=token,
        repo="SONVODAI/scanner-ga-chien-clean",
        status_path=accepted_status,
        timeout_sec=0,
        transport=accepted,
        lock=False,
    )
    assert result["result"] == "DISPATCH_ACCEPTED"
    assert result["run_id"] == 5
    assert token not in accepted_status.read_text(encoding="utf-8")
    assert "secret-token-value" not in json.dumps(result)


def test_dispatch_lock_busy_and_unit_boundaries(tmp_path: Path):
    status = tmp_path / "last.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    lock = status.with_suffix(".lock")
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, os, time, sys; "
            f"fd = os.open({str(lock)!r}, os.O_CREAT | os.O_RDWR, 0o600); "
            "fcntl.flock(fd, fcntl.LOCK_EX); "
            "sys.stdout.write('locked\\n'); sys.stdout.flush(); "
            "time.sleep(30)",
        ]
    )
    try:
        line = ""
        for _ in range(50):
            if lock.exists():
                try:
                    probe = os.open(lock, os.O_RDWR)
                    try:
                        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(probe, fcntl.LOCK_UN)
                    except BlockingIOError:
                        line = "locked"
                        break
                    finally:
                        os.close(probe)
                except FileNotFoundError:
                    pass
            import time

            time.sleep(0.05)
        assert line == "locked"
        result = dispatch_guardian_close(
            token="secret-token-value",
            repo="SONVODAI/scanner-ga-chien-clean",
            status_path=status,
            transport=lambda *args: (_ for _ in ()).throw(AssertionError("must not dispatch")),
            lock=True,
        )
    finally:
        holder.kill()
        holder.wait(timeout=5)
    assert result["result"] == "DISPATCH_BUSY"
    assert "secret-token-value" not in status.read_text(encoding="utf-8")

    root = ROOT
    assert "mrbot-guardian-dispatch" not in (root / "deploy/systemd/install.sh").read_text(encoding="utf-8")
    reference = (root / "deploy/systemd/mrbot-guardian-reference.timer").read_text(encoding="utf-8")
    assert "workflow_dispatch" not in reference
    assert "18:20:00 Asia/Ho_Chi_Minh" in (root / "deploy/systemd/mrbot-guardian-dispatch.timer").read_text(encoding="utf-8")
    service = (root / "deploy/systemd/mrbot-guardian-dispatch.service").read_text(encoding="utf-8")
    assert "Restart=no" in service
    assert "TimeoutStartSec=30" in service
    workflow = (root / ".github/workflows/guardian-close.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: write\n" in workflow
    assert "actions: write" not in workflow
    close_job = (root / "research/guardian_research/close_job.py").read_text(encoding="utf-8")
    assert "update_learning" not in close_job
    assert "commit_qualified_freeze" in close_job


def test_production_freeze_and_sealed_sessions_are_byte_stable():
    freeze = ROOT / "data" / "earning_learning" / "t0_observation_freeze.csv"
    before = hashlib.sha256(freeze.read_bytes()).hexdigest()
    sessions = ROOT / "data" / "guardian_research" / "sessions"
    session_bytes = {path.name: path.read_bytes() for path in sessions.glob("*.json")}
    assert before == hashlib.sha256(freeze.read_bytes()).hexdigest()
    assert session_bytes == {path.name: path.read_bytes() for path in sessions.glob("*.json")}
    assert not (sessions / "2026-11-13.json").exists()

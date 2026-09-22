"""One-time forward-ledger migration does not overwrite GitHub authority."""

from __future__ import annotations

import json

import pandas as pd

from modules.forward_ledger_migration import migrate_forward_ledgers
from modules.forward_ledger_store import (
    FORWARD_LEDGER_NAMES,
    MIGRATION_REPORT_NAME,
    publish_cache,
)


LEDGER = (
    "session_date,symbol,evaluation_mode,note\n"
    "2026-01-02,ZZTOP,FORWARD_FROZEN,keep\n"
    "2026-09-22,ZZTOP,FORWARD_FROZEN,keep\n"
)


class _GitHub:
    enabled = True


class _Store:
    def __init__(self, files=None):
        self.github = _GitHub()
        self.files = dict(files or {})
        self.writes: list[str] = []

    def _github_read(self, filename: str):
        if filename not in self.files:
            return None
        return type("Payload", (), {"text": self.files[filename]})()

    def _github_write(self, filename: str, text: str, message: str) -> str:
        self.writes.append(filename)
        self.files[filename] = text
        return "GITHUB_OK"


def _plant(tmp_path, monkeypatch, text: str = LEDGER):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    monkeypatch.setenv("MRBOT_BRAIN_DIR", str(brain))
    for name in FORWARD_LEDGER_NAMES:
        (brain / name).write_text(text, encoding="utf-8")
    return brain


def test_migration_uploads_missing_files_and_verifies_without_row_text(tmp_path, monkeypatch):
    _plant(tmp_path, monkeypatch)
    store = _Store()
    report = migrate_forward_ledgers(storage=store)
    assert report["ready"] is True
    assert report["report_status"] == "RECORDED"
    assert MIGRATION_REPORT_NAME in store.files
    blob = json.dumps(report)
    assert "ZZTOP" not in blob
    for name in FORWARD_LEDGER_NAMES:
        item = report["ledgers"][name]
        assert item["status"] == "MIGRATED"
        assert item["row_count"] == 2
        assert item["date_min"] == "2026-01-02"
        assert item["date_max"] == "2026-09-22"
        assert item["sha256"]
        assert "session_date" in item["columns"]
        assert store.files[name] == LEDGER
    assert store.writes.count(FORWARD_LEDGER_NAMES[0]) == 1

    again = migrate_forward_ledgers(storage=store)
    assert again["ready"] is True
    assert again["ledgers"][FORWARD_LEDGER_NAMES[0]]["status"] == "ALREADY_EXISTS"
    assert store.writes.count(FORWARD_LEDGER_NAMES[0]) == 1

    path = tmp_path / "brain" / FORWARD_LEDGER_NAMES[0]
    assert publish_cache(path, storage=store) == "PUBLISHED"


def test_existing_github_rows_are_not_overwritten(tmp_path, monkeypatch):
    _plant(tmp_path, monkeypatch)
    remote = (
        "session_date,symbol,evaluation_mode\n"
        "2026-03-03,OTHER,FORWARD_FROZEN\n"
    )
    store = _Store({name: remote for name in FORWARD_LEDGER_NAMES})
    report = migrate_forward_ledgers(storage=store)
    assert report["ready"] is False
    for name in FORWARD_LEDGER_NAMES:
        assert report["ledgers"][name]["status"] == "FAILED"
        assert report["ledgers"][name]["reason"] == "REMOTE_CONFLICT"
        assert store.files[name] == remote
    assert FORWARD_LEDGER_NAMES[0] not in store.writes
    assert "OTHER" not in json.dumps(report)
    assert "ZZTOP" not in json.dumps(report)


def test_no_local_history_does_not_create_an_empty_authority(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    monkeypatch.setenv("MRBOT_BRAIN_DIR", str(brain))
    store = _Store()
    report = migrate_forward_ledgers(storage=store)
    assert report["ready"] is True
    for name in FORWARD_LEDGER_NAMES:
        assert report["ledgers"][name]["status"] == "NO_LOCAL_HISTORY"
        assert name not in store.files
    assert MIGRATION_REPORT_NAME in store.files


def test_bad_schema_is_not_uploaded(tmp_path, monkeypatch):
    _plant(tmp_path, monkeypatch, "foo,bar\n1,2\n")
    store = _Store()
    report = migrate_forward_ledgers(storage=store)
    assert report["ready"] is False
    for name in FORWARD_LEDGER_NAMES:
        assert report["ledgers"][name]["status"] == "FAILED"
        assert report["ledgers"][name]["reason"].startswith("SCHEMA:")
        assert name not in store.files


def test_empty_github_object_is_not_replaced(tmp_path, monkeypatch):
    _plant(tmp_path, monkeypatch)
    store = _Store({FORWARD_LEDGER_NAMES[0]: ""})
    report = migrate_forward_ledgers(storage=store)
    item = report["ledgers"][FORWARD_LEDGER_NAMES[0]]
    assert item["status"] == "FAILED"
    assert item["reason"] == "REMOTE_EXISTS_EMPTY"
    assert store.files[FORWARD_LEDGER_NAMES[0]] == ""
    assert report["ready"] is False


def test_readback_mismatch_is_a_failure(tmp_path, monkeypatch):
    _plant(tmp_path, monkeypatch)

    class _Corrupt(_Store):
        def _github_read(self, filename: str):
            payload = super()._github_read(filename)
            if payload is not None and filename.endswith(".csv") and payload.text == LEDGER:
                payload.text = LEDGER + "2026-09-23,ZZTOP,FORWARD_FROZEN,extra\n"
            return payload

    store = _Corrupt()
    report = migrate_forward_ledgers(storage=store)
    assert report["ready"] is False
    assert report["ledgers"][FORWARD_LEDGER_NAMES[0]]["reason"] == "READBACK_MISMATCH"
    frame = pd.read_csv(tmp_path / "brain" / FORWARD_LEDGER_NAMES[0])
    assert len(frame) == 2

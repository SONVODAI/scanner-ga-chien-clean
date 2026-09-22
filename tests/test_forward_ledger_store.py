"""Forward ledger GitHub cache: explicit paths bypass, GitHub wins, schema stays."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.forward_ledger_store import (
    FORWARD_LEDGER_NAMES,
    publish_cache,
    refresh_cache_from_github,
)
from modules.regime_alpha_forward_eval import load_forward_ledger


class _GitHub:
    enabled = True


class _Store:
    def __init__(self, remote: str | None):
        self.github = _GitHub()
        self.remote = remote
        self.writes: list[str] = []

    def _github_read(self, filename: str):
        if self.remote is None:
            return None
        return type("Payload", (), {"text": self.remote})()

    def _github_write(self, filename: str, text: str, message: str) -> str:
        self.writes.append(text)
        return "GITHUB_OK"


def test_github_replaces_cache_without_merging_rows(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    monkeypatch.setenv("MRBOT_BRAIN_DIR", str(brain))
    path = brain / FORWARD_LEDGER_NAMES[0]
    path.write_text("symbol,extra\nLOCAL,1\nLOCAL2,2\n", encoding="utf-8")
    remote = "symbol,extra\nGITHUB,9\n"
    store = _Store(remote)
    status = refresh_cache_from_github(path, storage=store)
    assert status == "GITHUB_WINS"
    assert path.read_text(encoding="utf-8") == remote
    assert store.writes == []
    assert list(pd.read_csv(path).columns) == ["symbol", "extra"]


def test_missing_github_object_is_not_seeded(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    monkeypatch.setenv("MRBOT_BRAIN_DIR", str(brain))
    path = brain / FORWARD_LEDGER_NAMES[1]
    local = "symbol,session_date\nAAA,2026-09-22\n"
    path.write_text(local, encoding="utf-8")
    store = _Store(None)
    status = refresh_cache_from_github(path, storage=store)
    assert status == "GITHUB_MISSING"
    assert store.writes == []
    assert path.read_text(encoding="utf-8") == local


def test_explicit_ledger_path_bypasses_github(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "modules.forward_ledger_store.refresh_cache_from_github",
        lambda *args, **kwargs: calls.append("refresh"),
    )
    explicit = tmp_path / "ledger.csv"
    explicit.write_text("symbol\nAAA\n", encoding="utf-8")
    frame = load_forward_ledger(evaluation_mode=None, ledger_path=explicit)
    assert calls == []
    assert "symbol" in frame.columns

    other = tmp_path / "custom.csv"
    other.write_text("keep\n", encoding="utf-8")
    store = _Store("changed\n")
    assert refresh_cache_from_github(other, storage=store) == "BYPASS"
    assert other.read_text(encoding="utf-8") == "keep\n"
    assert store.writes == []


def test_publish_waits_for_migration_then_writes_bytes_unchanged(tmp_path, monkeypatch):
    import json

    from modules.forward_ledger_store import MIGRATION_REPORT_NAME, MIGRATION_REPORT_SCHEMA

    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    monkeypatch.setenv("MRBOT_BRAIN_DIR", str(brain))
    path = brain / FORWARD_LEDGER_NAMES[2]
    text = "session_date,symbol,evaluation_mode\n2026-09-22,AAA,FORWARD_FROZEN\n"
    path.write_text(text, encoding="utf-8")
    store = _Store(None)
    assert publish_cache(path, storage=store) == "AUTHORITY_NOT_READY"
    assert store.writes == []
    report = {"schema": MIGRATION_REPORT_SCHEMA, "ready": True, "ledgers": {}}
    (brain / MIGRATION_REPORT_NAME).write_text(json.dumps(report), encoding="utf-8")
    assert publish_cache(path, storage=store) == "PUBLISHED"
    assert store.writes == [text]
    assert list(pd.read_csv(path).columns) == ["session_date", "symbol", "evaluation_mode"]

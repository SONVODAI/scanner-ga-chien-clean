"""Canonical bars become approximate closes without rewriting the archive."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from research.guardian_research.outcomes import build_outcomes
from research.guardian_research.reference_export import (
    PUBLISHED_PATH,
    ReferenceExportError,
    _NoRedirect,
    export_reference_store,
    fetch_published_store,
    guardian_reference_url,
    resolve_store_path,
    write_reference_store,
)
from research.guardian_research.snapshot import build_snapshot, label_observation_origin, write_snapshot

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _write_bars(root: Path, session: str, rows: list[dict]) -> Path:
    day = datetime.fromisoformat(session).date()
    path = (
        root
        / "canonical"
        / f"year={day.year}"
        / f"month={day.month:02d}"
        / f"session_date={session}"
        / "bars.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _bar(session: str, symbol: str, clock: str, close: int, **extra) -> dict:
    stamp = datetime.fromisoformat(f"{session}T{clock}:00").replace(tzinfo=VN)
    row = {
        "symbol": symbol,
        "timestamp": stamp,
        "session_date": session,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 100,
        "source": "vnstock4_kbs",
        "collected_at": stamp,
        "quality_flag": "ok",
    }
    row.update(extra)
    return row


def test_close_window_keeps_the_last_valid_bar_and_rejects_1430(tmp_path):
    friday = _write_bars(tmp_path, "2026-11-06", [
        _bar("2026-11-06", "HPG", "14:30", 90),
        _bar("2026-11-06", "HPG", "14:45", 100),
        _bar("2026-11-06", "HPG", "15:00", 103),
        _bar("2026-11-06", "SSI", "14:30", 50),
        _bar("2026-11-06", "VCB", "14:45", 70),
        _bar("2026-11-06", "VCB", "14:45", 70),
    ])
    _write_bars(tmp_path, "2026-11-09", [
        _bar("2026-11-09", "HPG", "14:45", 110),
        _bar("2026-11-09", "VCB", "14:55", 77),
    ])
    before = friday.read_bytes()
    store = export_reference_store(tmp_path, symbols=("HPG", "SSI", "VCB", "FPT"))
    assert friday.read_bytes() == before
    assert store["as_of"] == "2026-11-09"
    assert store["trading_sessions"] == ["2026-11-06", "2026-11-09"]
    assert "2026-11-07" not in store["trading_sessions"]
    by_key = {(row["symbol"], row["session"]): row for row in store["rows"]}
    assert by_key[("HPG", "2026-11-06")]["close"] == 103
    assert by_key[("HPG", "2026-11-06")]["clock"] == "15:00"
    assert by_key[("VCB", "2026-11-06")]["clock"] == "14:45"
    assert ("SSI", "2026-11-06") not in by_key
    reasons = {(item["symbol"], item["session"]): item["reason"] for item in store["rejections"]}
    assert reasons[("SSI", "2026-11-06")] == "LAST_BAR_BEFORE_CLOSE"
    assert reasons[("FPT", "2026-11-06")] == "SYMBOL_ABSENT"
    assert store["coverage"]["symbols_never_seen"] == ["FPT"]
    assert store["source"] == "vnstock4_kbs"
    assert store["price_basis"] == "APPROX_LAST_5M_CLOSE"


def test_conflicting_close_invalid_price_and_foreign_source_are_rejected(tmp_path):
    _write_bars(tmp_path, "2026-11-06", [
        _bar("2026-11-06", "HPG", "14:45", 100),
        _bar("2026-11-06", "HPG", "14:45", 101),
        _bar("2026-11-06", "SSI", "14:45", 0),
        _bar("2026-11-06", "VCB", "14:45", 70, source="yahoo"),
        _bar("2026-11-06", "FPT", "14:45", 30, quality_flag="rejected"),
        _bar("2026-11-06", "ACV", "14:45", 10, session_date="2026-11-05"),
        _bar("2026-11-06", "MBB", "14:45", 20),
    ])
    store = export_reference_store(tmp_path, symbols=("HPG", "SSI", "VCB", "FPT", "ACV", "MBB"))
    assert [row["symbol"] for row in store["rows"]] == ["MBB"]
    reasons = {}
    for item in store["rejections"]:
        reasons.setdefault(item["symbol"], set()).add(item["reason"])
    assert "CONFLICTING_CLOSE" in reasons["HPG"]
    assert "PRICE_INVALID" in reasons["SSI"]
    assert "SOURCE_MISMATCH" in reasons["VCB"]
    assert "QUALITY_NOT_OK" in reasons["FPT"]
    assert "SESSION_DATE_MISMATCH" in reasons["ACV"]


def test_conflicting_file_does_not_publish_when_nothing_is_accepted(tmp_path):
    _write_bars(tmp_path, "2026-11-06", [
        _bar("2026-11-06", "HPG", "14:45", 100),
        _bar("2026-11-06", "HPG", "14:45", 101),
    ])
    try:
        export_reference_store(tmp_path, symbols=("HPG",))
    except ReferenceExportError as exc:
        assert exc.reason == "NO_ACCEPTED_CLOSES"
    else:
        raise AssertionError("empty export must be refused")


def test_unreadable_session_refuses_and_leaves_output_absent(tmp_path):
    path = _write_bars(tmp_path, "2026-11-06", [_bar("2026-11-06", "HPG", "14:45", 100)])
    path.write_bytes(b"not parquet")
    destination = tmp_path / "out" / "reference_store.json"
    try:
        store = export_reference_store(tmp_path, symbols=("HPG",))
        write_reference_store(store, destination, camera_root=tmp_path)
    except ReferenceExportError as exc:
        assert exc.reason == "SESSION_UNREADABLE"
    assert not destination.exists()


def test_repeated_export_is_identical_and_cannot_write_into_the_archive(tmp_path):
    _write_bars(tmp_path, "2026-11-06", [_bar("2026-11-06", "HPG", "14:45", 100)])
    _write_bars(tmp_path, "2026-11-09", [_bar("2026-11-09", "HPG", "14:45", 110)])
    first = export_reference_store(tmp_path, symbols=("HPG",))
    second = export_reference_store(tmp_path, symbols=("HPG",))
    assert first == second
    destination = tmp_path / "guardian_reference" / "reference_store.json"
    write_reference_store(first, destination, camera_root=tmp_path)
    write_reference_store(second, destination, camera_root=tmp_path)
    assert destination.read_bytes() == destination.read_bytes()
    inside = tmp_path / "canonical" / "reference_store.json"
    try:
        write_reference_store(first, inside, camera_root=tmp_path)
    except ReferenceExportError as exc:
        assert exc.reason == "OUTPUT_INSIDE_ARCHIVE"
    else:
        raise AssertionError("archive write must be refused")
    assert not inside.exists()


def test_exported_store_measures_tplus_without_changing_the_seal(tmp_path):
    _write_bars(tmp_path / "camera", "2026-11-06", [_bar("2026-11-06", "HPG", "14:45", 100)])
    _write_bars(tmp_path / "camera", "2026-11-09", [_bar("2026-11-09", "HPG", "14:45", 110)])
    store = export_reference_store(tmp_path / "camera", symbols=("HPG",))
    observation = {
        "kind": "scan_row",
        "input_session": "2026-11-06",
        "reference_price_provenance": "production_scan.price",
        "quality": "production_scan_row",
        "source": "production_scan",
        "live_injected": False,
        "price": 100,
        "ema9": 90,
        "ma20": 80,
        "obv": 10,
        "obv_ema9": 12,
    }
    document = build_snapshot("2026-11-06", {"HPG": observation}, symbols=("HPG",))
    labeled = label_observation_origin(
        document,
        "CONTEMPORANEOUS",
        reconstruction={"observation_at": "2026-11-06T15:00:00+07:00", "sealed_at": "2026-11-06T15:00:00+07:00"},
    )
    path = write_snapshot(tmp_path / "research", labeled)
    before = path.read_bytes()
    view = build_outcomes(tmp_path / "research", store)
    assert path.read_bytes() == before
    assert view["measured"] is True
    assert view["rows"][0]["horizons"]["T+1"]["return_pct"] == 10
    assert view["rows"][0]["horizons"]["T+1"]["status"] == "APPROX_AVAILABLE"
    assert view["rows"][0]["horizons"]["T+3"]["return_pct"] is None


def test_published_fetch_keeps_a_verified_body_and_drops_a_bad_one(tmp_path):
    _write_bars(tmp_path / "camera", "2026-11-06", [_bar("2026-11-06", "HPG", "14:45", 100)])
    store = export_reference_store(tmp_path / "camera", symbols=("HPG",))
    body = (json.dumps(store, sort_keys=True) + "\n").encode("utf-8")
    seen = {}
    endpoint = "https://artifacts.example/edge-research" + PUBLISHED_PATH

    def opener(url, token):
        seen["url"] = url
        seen["token"] = token
        return body

    destination = tmp_path / "reference_store.json"
    fetched = fetch_published_store(endpoint, "secret", destination, opener=opener)
    assert fetched == destination
    assert seen["url"] == endpoint
    assert seen["token"] == "secret"
    broken = body.replace(b"APPROX_LAST_5M_CLOSE", b"OFFICIAL_DAILY_CLOSE")

    def bad_opener(url, token):
        return broken

    assert fetch_published_store(endpoint, "secret", destination, opener=bad_opener) is None
    assert not destination.exists()
    assert fetch_published_store("http://artifacts.example" + endpoint[len("https://artifacts.example"):], "secret", destination, opener=opener) is None
    assert guardian_reference_url(endpoint) == endpoint
    assert guardian_reference_url("https://artifacts.example/edge-research") is None
    assert guardian_reference_url("https://artifacts.example/edge-research/../etc" + PUBLISHED_PATH) is None
    assert guardian_reference_url("https://user:secret@artifacts.example" + PUBLISHED_PATH) is None
    assert guardian_reference_url(endpoint + "?download=1") is None
    assert _NoRedirect().redirect_request(None, None, 302, "Moved", {}, "https://other.example/x") is None


def test_guardian_download_ignores_ledger_secrets(tmp_path, monkeypatch):
    endpoint = "https://artifacts.example/edge-research" + PUBLISHED_PATH
    _write_bars(tmp_path / "camera", "2026-11-06", [_bar("2026-11-06", "HPG", "14:45", 100)])
    store = export_reference_store(tmp_path / "camera", symbols=("HPG",))
    body = (json.dumps(store, sort_keys=True) + "\n").encode("utf-8")
    seen = []

    def opener(url, token):
        seen.append((url, token))
        return body

    monkeypatch.setattr("research.guardian_research.reference_export._open_https", opener)
    monkeypatch.setenv("EDGE_RESEARCH_LEDGER_URL", "https://ledger.example")
    monkeypatch.setenv("EDGE_RESEARCH_LEDGER_TOKEN", "ledger-secret")
    monkeypatch.setenv("GUARDIAN_REFERENCE_PREFIX", "/edge-research")
    monkeypatch.setenv("GUARDIAN_REFERENCE_DOWNLOAD", str(tmp_path / "downloaded.json"))
    monkeypatch.delenv("GUARDIAN_REFERENCE_URL", raising=False)
    monkeypatch.delenv("GUARDIAN_REFERENCE_TOKEN", raising=False)
    assert resolve_store_path(tmp_path / "absent") is None
    assert seen == []

    monkeypatch.setenv("GUARDIAN_REFERENCE_URL", endpoint)
    assert resolve_store_path(tmp_path / "absent") is None
    assert seen == []

    monkeypatch.setenv("GUARDIAN_REFERENCE_TOKEN", "guardian-secret")
    fetched = resolve_store_path(tmp_path / "absent")
    assert fetched == tmp_path / "downloaded.json"
    assert seen == [(endpoint, "guardian-secret")]
    monkeypatch.setenv("GUARDIAN_REFERENCE_URL", "https://artifacts.example/edge-research")
    assert resolve_store_path(tmp_path / "still-absent") is None
    assert seen == [(endpoint, "guardian-secret")]

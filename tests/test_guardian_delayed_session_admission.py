"""The sealed 16/11/2026 snapshot can enter research without being rewritten."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from research.guardian_research.outcomes import build_outcomes
from research.guardian_research.snapshot import read_snapshot

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "data" / "guardian_research"
FREEZE = ROOT / "data" / "earning_learning" / "t0_observation_freeze.csv"
OUTCOMES = ROOT / "research" / "guardian_research" / "outcomes.json"
SESSION = "2026-11-16"
SNAPSHOT_SHA = "d0421389ff1f7c07041eda3d6f23a35d2a42f2df725758c351d64c330fca5a0d"


def _bytes() -> dict[str, bytes]:
    files = [OUTCOMES, FREEZE, *sorted((RESEARCH / "sessions").glob("*.json"))]
    return {str(path): path.read_bytes() for path in files}


def test_session_2026_11_16_enters_research_and_published_files_stay_byte_stable(tmp_path):
    before = _bytes()
    view = build_outcomes(RESEARCH, None)
    assert view["delayed_sessions_excluded"] == []
    assert view["delayed_sessions_included"] == [SESSION]
    assert view["contemporaneous_sessions"] == ["2026-11-06", "2026-11-11"]
    assert view["backfilled_sessions_excluded"] == []
    counts = {}
    for row in view["rows"]:
        counts.setdefault(row["session"], set()).add(row["symbol"])
    assert set(counts) == {"2026-11-06", "2026-11-11", SESSION}
    assert all(len(symbols) == 143 for symbols in counts.values())
    document = read_snapshot(RESEARCH / "sessions" / f"{SESSION}.json")
    assert document["observation_origin"] == "DELAYED"
    assert document["tracked_count"] == 143
    assert document["content_sha256"] == SNAPSHOT_SHA
    assert document["reconstruction"]["observation_at"] == "2026-11-16T18:21:15.691607+07:00"
    assert document["session_witness"]["bar_session"] == SESSION
    assert document["session_witness"]["source"] == "vnindex_daily_bar"
    assert all(row["forward"]["status"] == "UNVERIFIED" for row in document["rows"])

    missing = build_outcomes(RESEARCH, None, freeze_path=tmp_path / "absent.csv")
    assert missing["delayed_sessions_included"] == []
    assert missing["delayed_sessions_excluded"] == [{"session": SESSION, "reason": "FREEZE_ABSENT"}]
    assert {row["session"] for row in missing["rows"]} == {"2026-11-06", "2026-11-11"}

    copied = tmp_path / "freeze.csv"
    copied.write_bytes(FREEZE.read_bytes())
    frame = pd.read_csv(copied)
    selected = frame["trade_date"].astype(str).str.slice(0, 10) == SESSION
    assert int(selected.sum()) == 143
    frame.loc[selected, "guardian_witness_sha256"] = "0" * 64
    frame.to_csv(copied, index=False)
    mismatched = build_outcomes(RESEARCH, None, freeze_path=copied)
    assert mismatched["delayed_sessions_excluded"] == [{"session": SESSION, "reason": "WITNESS_INTEGRITY"}]
    assert SESSION not in {row["session"] for row in mismatched["rows"]}
    assert _bytes() == before
    assert hashlib.sha256(before[str(OUTCOMES)]).hexdigest() == hashlib.sha256(OUTCOMES.read_bytes()).hexdigest()

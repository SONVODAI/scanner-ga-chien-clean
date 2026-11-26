"""Catch-up publication on a temporary ledger. The committed store is only read."""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from research.approximate_returns.reference import build_reference_store
from research.guardian_research.reference_export import _digest
from research.v2_research_ledger.daily_publish import (
    PINNED_GENERATIONS,
    CatchupRefusal,
    commit_catchup,
    generation_snapshot,
    ingest_ledger,
    plan_catchup,
    publish_catchup,
    session_gate,
    slice_reference,
)
from research.v2_research_ledger.durable_store import DurableRowStore
from research.v2_research_ledger.forward_outcomes import build_forward_document
from research.v2_research_ledger.delivery_view import DELIVERY_UNAVAILABLE, DeliveryView
from research.v2_research_ledger.panel_board import deduped_research_observations, load_row_panel
from modules.v2_research_ledger_panel.ui import render_v2_research_ledger_panel

ROOT = Path(__file__).resolve().parents[1]
DURABLE = ROOT / "research" / "v2_research_ledger" / "durable"
SIDECAR = ROOT / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
SWEET = ROOT / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"
TRACKED = {"HPG", "VCB", "SSI"}
IDENTITY_PREFIX_SHA256 = "a2e868e74e62fef8d74c0215f817194e9489cba7af523e788c42251f9c28b848"
IDENTITY_FILE_SHA256 = "aa21aa1ec5bc7d92fc7673eedc697b15cf7a242ddd5cdbd3d921374edacd629b"
SIDECAR_SHA256 = "fd7dd7ca01f20fc6c567e31cbfcf6b209a8f3360fe04598e2af0065203fc40f8"
SWEET_SHA256 = "088871173a5ee6c7860b83769195a4be364b0c32d09ba02a0dcf0615d3ce2656"
IDENTITY_PREFIX_COUNT = 1434
IDENTITY_COUNT = 1448


class _Expander:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.captions: list[str] = []

    def expander(self, *_args, **_kwargs):
        return _Expander()

    def caption(self, text: str) -> None:
        self.captions.append(str(text))

    def warning(self, text: str) -> None:
        self.captions.append(str(text))

    def selectbox(self, _label, options, index=0):
        return options[index]

    def text_input(self, _label, value=""):
        return value

    def dataframe(self, _frame, *_args, **_kwargs):
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weekdays(start: str, count: int) -> list[str]:
    day = datetime.date.fromisoformat(start)
    found = []
    while len(found) < count:
        if day.weekday() < 5:
            found.append(day.isoformat())
        day += datetime.timedelta(days=1)
    return found


def _closes(sessions: list[str], *, omit: set[tuple[str, str]] | None = None) -> list[dict]:
    skipped = omit or set()
    rows = []
    for day in sessions:
        for index, symbol in enumerate(("HPG", "VCB", "SSI")):
            if (symbol, day) in skipped:
                continue
            rows.append({"symbol": symbol, "session": day, "close": 1000 + index * 10, "clock": "14:50"})
    return rows


def _book(sessions: list[str], rows: list[dict] | None = None, rejections: list[dict] | None = None, tracked_count: int = 3) -> dict:
    store = build_reference_store(pd.DataFrame(rows if rows is not None else _closes(sessions)), sessions, as_of=sessions[-1])
    store["rejections"] = [] if rejections is None else rejections
    store["coverage"] = {"tracked_count": tracked_count}
    store["content_sha256"] = _digest(store)
    return store


def _prior(sessions: list[str], store: dict) -> dict:
    viewed = slice_reference(store, sessions[-1])
    return {
        "as_of": sessions[-1],
        "generation_id": "prior",
        "reference_sha256": viewed["content_sha256"],
        "trading_sessions": list(sessions),
    }


def _sidecar(path: Path, session: str, symbol: str = "HPG") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "freeze_ledger": [
                    {
                        "breakout_ref_at_first_seen": 27100.0,
                        "candidate_first_seen_ts": f"{session}T02:00:00Z",
                        "ema9_at_first_seen": 26990.0,
                        "price_at_first_seen": 27000.0,
                        "session": session,
                        "symbol": symbol,
                    }
                ],
                "observed_at": f"{session}T10:00:00+07:00",
                "rows": [],
                "session": session,
            }
        ),
        encoding="utf-8",
    )


def _sweet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "observer_id,t0_date,symbol,observer_status,price_t0,created_at\n"
    body = "".join(
        f"{row['observer_id']},{row['t0_date']},{row.get('symbol', '')},{row['observer_status']},{row.get('price_t0', '')},{row['created_at']}\n"
        for row in rows
    )
    path.write_text(header + body, encoding="utf-8")


def _ledger(tmp_path: Path, session: str = "2026-11-20") -> tuple[Path, Path]:
    root = tmp_path / "tree"
    sidecar = root / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
    sweet = root / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"
    _sidecar(sidecar, session)
    _sweet(
        sweet,
        [
            {
                "observer_id": "blank1",
                "t0_date": "2026-11-19",
                "symbol": "",
                "observer_status": "QUALIFIED_SWEETSPOT_BUT_0_CANDIDATES",
                "created_at": "2026-11-19T13:16:58Z",
            }
        ],
    )
    ledger = root / "research" / "v2_research_ledger" / "durable"
    ingest_ledger(ledger, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    for name in ("links.jsonl", "conflicts.jsonl"):
        path = ledger / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
    outcomes = root / "research" / "v2_research_ledger" / "outcomes"
    outcomes.mkdir(parents=True, exist_ok=True)
    return ledger, outcomes


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            **dict(**{key: value for key, value in __import__("os").environ.items()}),
            "GIT_AUTHOR_NAME": "ledger-test",
            "GIT_AUTHOR_EMAIL": "ledger-test@example.com",
            "GIT_COMMITTER_NAME": "ledger-test",
            "GIT_COMMITTER_EMAIL": "ledger-test@example.com",
        },
    )


def _identity_prefix(payload: bytes, count: int) -> bytes:
    lines = payload.splitlines()
    return b"\n".join(lines[:count]) + b"\n"


def test_committed_identities_keep_the_sealed_prefix(tmp_path: Path):
    assert _sha256(SIDECAR) == SIDECAR_SHA256
    assert _sha256(SWEET) == SWEET_SHA256
    before_repo = (DURABLE / "identities.jsonl").read_bytes()
    assert before_repo.count(b"\n") == IDENTITY_COUNT
    assert _sha256(DURABLE / "identities.jsonl") == IDENTITY_FILE_SHA256
    prefix = _identity_prefix(before_repo, IDENTITY_PREFIX_COUNT)
    assert hashlib.sha256(prefix).hexdigest() == IDENTITY_PREFIX_SHA256
    assert before_repo.startswith(prefix)
    suffix = [json.loads(line) for line in before_repo.splitlines()[IDENTITY_PREFIX_COUNT:]]
    assert len(suffix) == IDENTITY_COUNT - IDENTITY_PREFIX_COUNT
    blanks = [row for row in suffix if not str(row.get("symbol") or "").strip()]
    assert len(blanks) == 2
    assert {row["symbol"] for row in suffix if str(row.get("symbol") or "").strip()} == {
        "SBT",
        "FOX",
        "VHM",
        "PTB",
        "VRE",
        "KBC",
        "TCM",
        "HUT",
        "PC1",
        "VSC",
        "TPB",
        "HDB",
    }
    assert any(row["symbol"] == "FOX" and row["t0_date"] == "2026-11-23" for row in suffix)
    prefix_ids = {json.loads(line)["identity_id"] for line in prefix.splitlines()}
    assert prefix_ids.isdisjoint({row["identity_id"] for row in suffix})
    copy = tmp_path / "durable"
    shutil.copytree(DURABLE, copy, ignore=shutil.ignore_patterns(".ingest.lock"))
    first = ingest_ledger(copy, sidecar_path=SIDECAR, sweet_csv=SWEET, evidence_dir=None)
    after = (copy / "identities.jsonl").read_bytes()
    assert after.startswith(before_repo)
    assert first["sealed_identities_unchanged"] is True
    assert first["identity_count"] == after.count(b"\n")
    kept = after.splitlines()[:IDENTITY_COUNT]
    assert kept == before_repo.splitlines()
    sealed_before = {
        json.loads(line)["identity_id"]: json.loads(line).get("sealed")
        for line in prefix.splitlines()
    }
    sealed_after = {}
    for line in kept:
        row = json.loads(line)
        if row["identity_id"] in sealed_before:
            sealed_after[row["identity_id"]] = row.get("sealed")
            assert row.get("sealed") == sealed_before[row["identity_id"]]
    assert len(sealed_after) == IDENTITY_PREFIX_COUNT
    links_after_first = (copy / "links.jsonl").read_bytes()
    conflicts_after_first = (copy / "conflicts.jsonl").read_bytes()
    manifest_after_first = (copy / "manifest.json").read_bytes()
    second = ingest_ledger(copy, sidecar_path=SIDECAR, sweet_csv=SWEET, evidence_dir=None)
    assert second["inserted_identities"] == []
    assert second["identity_count"] == first["identity_count"]
    assert (copy / "identities.jsonl").read_bytes() == after
    third = ingest_ledger(copy, sidecar_path=SIDECAR, sweet_csv=SWEET, evidence_dir=None)
    assert third["inserted_identities"] == []
    assert (copy / "links.jsonl").read_bytes() == links_after_first
    assert (copy / "conflicts.jsonl").read_bytes() == conflicts_after_first
    assert (copy / "manifest.json").read_bytes() == manifest_after_first
    assert (DURABLE / "identities.jsonl").read_bytes() == before_repo
    assert _sha256(DURABLE / "identities.jsonl") == IDENTITY_FILE_SHA256
    for relative, digest in PINNED_GENERATIONS.items():
        assert _sha256(ROOT / relative) == digest

    sessions = ["2026-11-18", "2026-11-20"]
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(_book(sessions), sort_keys=True) + "\n", encoding="utf-8")
    pristine = tmp_path / "pristine"
    shutil.copytree(DURABLE, pristine, ignore=shutil.ignore_patterns(".ingest.lock"))
    document = build_forward_document(pristine, reference)
    assert document["official_pnl"] is False
    assert document["identity_count"] == IDENTITY_COUNT
    blank_ids = {row["identity_id"] for row in blanks}
    blank_rows = [row for row in document["rows"] if row["identity_id"] in blank_ids]
    assert len(blank_rows) == 2
    assert {row["population"] for row in blank_rows} == {"sweetspot_blank"}
    for row in document["rows"]:
        if row["symbol"]:
            continue
        assert row["t0_price_used_as_denominator"] is False
        for cell in row["horizons"].values():
            assert cell["return_pct"] is None
            assert cell["included_in_primary"] is False
    assert document["coverage"]["sweetspot_blank"]["horizons"]["T+1"]["usable_primary"] == 0
    performance = [
        row
        for row in document["rows"]
        if row["population"] in {"sweetspot", "brain_linked", "brain_unlinked"}
        and any(cell.get("return_pct") is not None for cell in row["horizons"].values())
    ]
    assert all(row["symbol"] for row in performance)
    assert all(row["population"] != "sweetspot_blank" for row in performance)
    observations = deduped_research_observations(DurableRowStore(pristine))
    assert all(symbol for _source, symbol, _session in observations)
    assert not any(row["symbol"] == "" for row in observations.values())


def test_catchup_from_68_to_70_sessions_in_one_run(tmp_path: Path):
    sessions = _weekdays("2026-08-14", 70)
    assert len(sessions) == 70
    store = _book(sessions)
    prior_sessions = sessions[:68]
    plan = plan_catchup(store, _prior(prior_sessions, store), TRACKED, today="2026-12-31")
    assert plan["stopped"] is None
    assert plan["sessions"] == sessions[68:]
    ledger, outcomes = _ledger(tmp_path, sessions[0])
    written = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert [item["as_of"] for item in written] == sessions[68:]
    assert [len(item["trading_sessions"]) for item in written] == [69, 70]
    assert all(item["official_pnl"] is False for item in written)
    again = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert [item["file_status"] for item in again] == ["unchanged", "unchanged"]
    assert [item["index_status"] for item in again] == ["unchanged", "unchanged"]


def test_catchup_publishes_more_than_two_sessions_in_order(tmp_path: Path):
    sessions = _weekdays("2026-11-02", 8)
    store = _book(sessions)
    plan = plan_catchup(store, _prior(sessions[:4], store), TRACKED, today="2026-12-31")
    assert len(plan["sessions"]) == 4
    assert plan["sessions"] == sessions[4:]
    ledger, outcomes = _ledger(tmp_path, sessions[0])
    written = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert [item["as_of"] for item in written] == sessions[4:]
    assert [item["file_status"] for item in written] == ["written", "written", "written", "written"]


def test_intermediate_missing_bar_stops_and_names_the_symbol(tmp_path: Path):
    sessions = _weekdays("2026-11-02", 6)
    omitted = sessions[4]
    store = _book(sessions, _closes(sessions, omit={("VCB", omitted)}))
    plan = plan_catchup(store, _prior(sessions[:3], store), TRACKED, today="2026-12-31")
    assert plan["sessions"] == [sessions[3]]
    assert plan["stopped"]["session"] == omitted
    assert plan["stopped"]["reason"] == "PRICE_BOOK_INCOMPLETE"
    assert {"symbol": "VCB", "reason": "SYMBOL_ABSENT", "session": omitted} in plan["stopped"]["missing"]
    ledger, outcomes = _ledger(tmp_path, sessions[0])
    written = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert [item["as_of"] for item in written] == [sessions[3]]
    names = sorted(path.name for path in (outcomes / "generations").glob("*.json"))
    assert len(names) == 1
    assert omitted not in names[0]
    assert sessions[5] not in names[0]
    saved = json.loads((outcomes / "generations" / names[0]).read_text(encoding="utf-8"))
    assert sessions[5] not in saved["trading_sessions"]
    assert omitted not in saved["trading_sessions"]


def test_holiday_and_no_candidate_day_stay_empty_without_inventing_a_session(tmp_path: Path):
    week = _weekdays("2026-11-16", 5)
    holiday = week[2]
    book_days = [week[0], week[1], week[3], week[4]]
    assert holiday not in book_days
    store = _book(book_days)
    plan = plan_catchup(store, _prior(book_days[:2], store), TRACKED, today="2026-12-31")
    assert plan["stopped"] is None
    assert plan["sessions"] == book_days[2:]
    assert holiday not in plan["sessions"]
    ledger, outcomes = _ledger(tmp_path, week[1])
    quiet = ingest_ledger(ledger, sidecar_path=None, sweet_csv=None, evidence_dir=None)
    assert quiet["inserted_identities"] == []
    written = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert [item["as_of"] for item in written] == [week[3], week[4]]
    for item in written:
        assert holiday not in item["trading_sessions"]
        assert item["trading_sessions"] == sorted(item["trading_sessions"])
    document = json.loads((outcomes / "generations" / f"{written[0]['generation_id']}.json").read_text(encoding="utf-8"))
    row = next(item for item in document["rows"] if item["symbol"] == "HPG" and item["t0_date"] == week[1])
    assert row["horizons"]["T+1"]["target_session"] == week[3]
    assert row["horizons"]["T+1"]["target_session"] != holiday
    blank = next(item for item in document["rows"] if item["population"] == "sweetspot_blank")
    assert blank["symbol"] == ""
    assert all(cell["return_pct"] is None for cell in blank["horizons"].values())
    assert blank["t0_price_used_as_denominator"] is False


def test_f88_outside_rejection_does_not_block_or_change_the_universe():
    sessions = ["2026-11-20", "2026-11-23"]
    rejections = [{"session": "2026-11-23", "symbol": "F88", "reason": "SYMBOL_ABSENT", "clock": ""}]
    store = _book(sessions, rejections=rejections, tracked_count=4)
    gate = session_gate(store, TRACKED)
    assert gate["ok"] is True
    assert gate["skipped"] == [{"clock": "", "reason": "SYMBOL_ABSENT", "session": "2026-11-23", "symbol": "F88"}]
    plan = plan_catchup(store, _prior(sessions[:1], store), TRACKED, today="2026-11-25")
    assert plan["sessions"] == ["2026-11-23"]
    assert plan["stopped"] is None


def test_rerun_after_mid_run_failure_keeps_the_written_session(tmp_path: Path):
    sessions = _weekdays("2026-11-16", 4)
    store = _book(sessions)
    plan = plan_catchup(store, _prior(sessions[:1], store), TRACKED, today="2026-12-31")
    assert len(plan["sessions"]) >= 2
    ledger, outcomes = _ledger(tmp_path, sessions[0])

    def fail_on_second(session: str) -> None:
        if session == plan["sessions"][1]:
            raise RuntimeError("mid-run")

    with pytest.raises(RuntimeError, match="mid-run"):
        publish_catchup(ledger, outcomes, store, plan["sessions"], on_session=fail_on_second)
    first_name = next((outcomes / "generations").glob("*.json"))
    first_bytes = first_name.read_bytes()
    first_document = json.loads(first_bytes)
    assert first_document["as_of"] == plan["sessions"][0]
    assert plan["sessions"][1] not in first_document["trading_sessions"]
    again = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert again[0]["file_status"] == "unchanged"
    assert again[0]["as_of"] == plan["sessions"][0]
    assert first_name.read_bytes() == first_bytes
    assert again[1]["file_status"] == "written"
    assert again[1]["as_of"] == plan["sessions"][1]


def test_panel_metadata_matches_the_attached_generation_and_not_the_clock(tmp_path: Path):
    sessions = ["2026-11-20", "2026-11-23"]
    ledger, outcomes = _ledger(tmp_path, sessions[0])
    store = _book(sessions)
    published = publish_catchup(ledger, outcomes, store, [sessions[1]])
    document_path = outcomes / "generations" / f"{published[0]['generation_id']}.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    assert "artifact_generated_at" not in document
    assert document["official_pnl"] is False
    assert document["as_of"] == "2026-11-23"
    assert document["latest_sealed_t0"] == "2026-11-20"
    assert document["source_updated_at"]
    assert document["ledger_hashes"]["identities.jsonl"] == _sha256(ledger / "identities.jsonl")
    panel = load_row_panel(DurableRowStore(ledger), outcomes_root=outcomes)
    assert panel is not None
    assert panel["as_of"] == document["as_of"]
    assert panel["source_updated_at"] == document["source_updated_at"]
    fresh = panel["freshness"]
    assert fresh["fingerprint_matches"] is True
    assert fresh["status"] == "VERIFIED"
    assert fresh["latest_measured_session"] == document["as_of"]
    assert fresh["latest_sealed_t0"] == document["latest_sealed_t0"]
    assert fresh["artifact_generated_at"] is None
    assert fresh["source_updated_at"] == document["source_updated_at"]
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=ledger,
    )
    text = "\n".join(fake.captions)
    assert "freshness=VERIFIED" in text
    assert "latest sealed T0=2026-11-20" in text
    assert "latest measured T+ session=2026-11-23" in text
    assert "artifact generation time=missing" in text
    assert f"source update time={document['source_updated_at']}" in text
    sidecar = tmp_path / "tree" / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
    sidecar.write_text(sidecar.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    late = load_row_panel(DurableRowStore(ledger), outcomes_root=outcomes)
    assert late is not None
    assert late["freshness"]["status"] == "LATE"
    assert late["freshness"]["fingerprint_matches"] is True
    assert late["freshness"]["latest_measured_session"] == "2026-11-23"
    late_view = _FakeStreamlit()
    render_v2_research_ledger_panel(
        late_view,
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=ledger,
    )
    late_text = "\n".join(late_view.captions)
    assert "freshness=LATE" in late_text
    assert "freshness=VERIFIED" not in late_text


def test_missing_generation_is_not_verified(tmp_path: Path):
    ledger, _outcomes = _ledger(tmp_path)
    panel = load_row_panel(DurableRowStore(ledger))
    assert panel is not None
    assert panel["freshness"]["status"] == "UNVERIFIED"
    assert panel["freshness"]["fingerprint_matches"] is False
    assert panel["as_of"] is None
    fake = _FakeStreamlit()
    render_v2_research_ledger_panel(
        fake,
        remote=True,
        remote_view=DeliveryView(DELIVERY_UNAVAILABLE, "missing_secret"),
        row_store=ledger,
    )
    text = "\n".join(fake.captions)
    assert "freshness=UNVERIFIED" in text
    assert "freshness=VERIFIED" not in text
    assert "artifact generation time=missing" in text
    assert "latest T0 (provenance)=unknown" in text


def test_commit_allowlist_refuses_stray_files_and_historical_rewrites(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    generation = repo / "research" / "v2_research_ledger" / "outcomes" / "generations" / "2026-11-20_old.json"
    generation.parent.mkdir(parents=True)
    generation.write_text('{"as_of":"2026-11-20"}\n', encoding="utf-8")
    (repo / "notes.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed")
    baseline = generation_snapshot(repo)
    (repo / "stray.txt").write_text("no\n", encoding="utf-8")
    with pytest.raises(CatchupRefusal) as stray:
        commit_catchup(repo, baseline, "refuse stray")
    assert stray.value.reason == "ALLOWLIST_REFUSED"
    (repo / "stray.txt").unlink()
    generation.write_text('{"as_of":"changed"}\n', encoding="utf-8")
    with pytest.raises(CatchupRefusal) as rewritten:
        commit_catchup(repo, baseline, "refuse rewrite")
    assert rewritten.value.reason == "HISTORICAL_GENERATION_CHANGED"
    with pytest.raises(CatchupRefusal) as forced:
        from research.v2_research_ledger import daily_publish

        daily_publish._git(repo, "push", "--force", "origin", "HEAD:main")
    assert forced.value.reason == "FORCE_PUSH_REFUSED"


def test_repo_generation_pins_are_unchanged():
    for relative, digest in PINNED_GENERATIONS.items():
        assert _sha256(ROOT / relative) == digest
    payload = (DURABLE / "identities.jsonl").read_bytes()
    assert payload.count(b"\n") == IDENTITY_COUNT
    assert _sha256(DURABLE / "identities.jsonl") == IDENTITY_FILE_SHA256
    assert hashlib.sha256(_identity_prefix(payload, IDENTITY_PREFIX_COUNT)).hexdigest() == IDENTITY_PREFIX_SHA256


GAP_TRACKED = {"HPG", "SBT", "FOX", "GIL"}
GAP_SESSIONS = ["2026-11-20", "2026-11-23", "2026-11-25", "2026-11-26"]


def _return_pct(later: int, earlier: int) -> float:
    return round((later / earlier - 1) * 100, 6)


def _gap_rows(days: list[str], *, fox_close_on_23: int | None) -> list[dict]:
    prices = {
        "HPG": {"2026-11-20": 1000, "2026-11-23": 1100, "2026-11-25": 1100, "2026-11-26": 1210, "2026-11-27": 1210},
        "SBT": {"2026-11-20": 1000, "2026-11-23": 1200, "2026-11-25": 1320, "2026-11-26": 1320, "2026-11-27": 1320},
        "FOX": {"2026-11-20": 1000, "2026-11-25": 1050, "2026-11-26": 1050, "2026-11-27": 1050},
        "GIL": {"2026-11-20": 1000, "2026-11-25": 1000, "2026-11-26": 1100, "2026-11-27": 1100},
    }
    if fox_close_on_23 is not None:
        prices["FOX"]["2026-11-23"] = fox_close_on_23
    rows = []
    for day in days:
        for symbol in sorted(prices):
            close = prices[symbol].get(day)
            if close is None:
                continue
            rows.append({"symbol": symbol, "session": day, "close": close, "clock": "14:50"})
    return rows


def _gap_store(days: list[str], *, fox_close_on_23: int | None = None) -> dict:
    rejections = [
        {"session": "2026-11-23", "symbol": "GIL", "reason": "LAST_BAR_BEFORE_CLOSE", "clock": "14:25"},
    ]
    if fox_close_on_23 is None:
        rejections.append(
            {"session": "2026-11-23", "symbol": "FOX", "reason": "LAST_BAR_BEFORE_CLOSE", "clock": "14:40"}
        )
    return _book(days, _gap_rows(days, fox_close_on_23=fox_close_on_23), rejections=rejections, tracked_count=len(GAP_TRACKED))


def _gap_ledger(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "tree"
    sidecar = root / "research" / "live_candidate_v2_camera_sidecar" / "camera_sidecar.json"
    sweet = root / "data" / "earning_learning" / "market_aware_sweetspot_observer_ledger.csv"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(
            {
                "freeze_ledger": [
                    {
                        "breakout_ref_at_first_seen": 1000,
                        "candidate_first_seen_ts": "2026-11-20T02:00:00Z",
                        "ema9_at_first_seen": 1000,
                        "price_at_first_seen": 1000,
                        "session": "2026-11-20",
                        "symbol": "HPG",
                    },
                    {
                        "breakout_ref_at_first_seen": 1000,
                        "candidate_first_seen_ts": "2026-11-20T02:00:01Z",
                        "ema9_at_first_seen": 1000,
                        "price_at_first_seen": 1000,
                        "session": "2026-11-20",
                        "symbol": "GIL",
                    },
                ],
                "observed_at": "2026-11-20T10:00:00+07:00",
                "rows": [],
                "session": "2026-11-20",
            }
        ),
        encoding="utf-8",
    )
    _sweet(
        sweet,
        [
            {
                "observer_id": "sbt23",
                "t0_date": "2026-11-23",
                "symbol": "SBT",
                "observer_status": "OBSERVE",
                "price_t0": 1200,
                "created_at": "2026-11-23T02:00:00Z",
            },
            {
                "observer_id": "fox23",
                "t0_date": "2026-11-23",
                "symbol": "FOX",
                "observer_status": "OBSERVE",
                "price_t0": 1000,
                "created_at": "2026-11-23T02:00:01Z",
            },
        ],
    )
    ledger = root / "research" / "v2_research_ledger" / "durable"
    ingest_ledger(ledger, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
    for name in ("links.jsonl", "conflicts.jsonl"):
        path = ledger / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
    outcomes = root / "research" / "v2_research_ledger" / "outcomes"
    outcomes.mkdir(parents=True, exist_ok=True)
    return ledger, outcomes


def _generation(outcomes: Path, item: dict) -> dict:
    return json.loads((outcomes / "generations" / f"{item['generation_id']}.json").read_text(encoding="utf-8"))


def _row(document: dict, symbol: str, t0_date: str) -> dict:
    return next(row for row in document["rows"] if row["symbol"] == symbol and row["t0_date"] == t0_date)


def test_explained_symbol_holes_let_the_later_sessions_publish():
    store = _gap_store(GAP_SESSIONS)
    assert "2026-11-24" not in store["trading_sessions"]
    assert {row["symbol"] for row in store["rows"] if row["session"] == "2026-11-23"} == {"HPG", "SBT"}
    gate = session_gate(slice_reference(store, "2026-11-23"), GAP_TRACKED)
    assert gate["ok"] is True
    assert gate["missing"] == []
    assert gate["skipped"] == []
    shrunk = _gap_store(GAP_SESSIONS)
    shrunk["coverage"] = {"tracked_count": 2}
    shrunk["content_sha256"] = _digest(shrunk)
    mismatch = session_gate(slice_reference(shrunk, "2026-11-23"), GAP_TRACKED)
    assert mismatch["ok"] is False
    assert mismatch["reason"] == "UNIVERSE_MISMATCH"
    plan = plan_catchup(store, _prior(["2026-11-20"], store), GAP_TRACKED, today="2026-11-27")
    assert plan["stopped"] is None
    assert plan["sessions"] == ["2026-11-23", "2026-11-25", "2026-11-26"]
    assert "2026-11-24" not in plan["sessions"]


def test_wide_failure_and_integrity_rejections_still_stop_the_walk():
    wide_days = ["2026-11-20", "2026-11-23", "2026-11-25"]
    wide_rows = [
        row for row in _gap_rows(wide_days, fox_close_on_23=None) if row["session"] != "2026-11-23"
    ]
    wide = _book(
        wide_days,
        wide_rows,
        rejections=[
            {"session": "2026-11-23", "symbol": symbol, "reason": "SYMBOL_ABSENT", "clock": ""}
            for symbol in sorted(GAP_TRACKED)
        ],
        tracked_count=len(GAP_TRACKED),
    )
    wide_plan = plan_catchup(wide, _prior(["2026-11-20"], wide), GAP_TRACKED, today="2026-11-27")
    assert wide_plan["sessions"] == []
    assert wide_plan["stopped"]["session"] == "2026-11-23"
    assert wide_plan["stopped"]["reason"] == "PRICE_BOOK_INCOMPLETE"
    assert {"symbol": "", "reason": "NO_OK_ROWS", "session": "2026-11-23"} in wide_plan["stopped"]["missing"]

    silent = _gap_store(GAP_SESSIONS)
    silent["rows"] = [row for row in silent["rows"] if not (row["session"] == "2026-11-25" and row["symbol"] == "SBT")]
    silent["content_sha256"] = _digest(silent)
    silent_plan = plan_catchup(silent, _prior(["2026-11-20"], silent), GAP_TRACKED, today="2026-11-27")
    assert silent_plan["sessions"] == ["2026-11-23"]
    assert silent_plan["stopped"]["session"] == "2026-11-25"
    assert {"symbol": "SBT", "reason": "SYMBOL_ABSENT", "session": "2026-11-25"} in silent_plan["stopped"]["missing"]
    assert "2026-11-26" not in silent_plan["sessions"]

    def refuse(reason: str, symbol: str = "HPG") -> None:
        store = _gap_store(GAP_SESSIONS)
        store["rejections"] = list(store["rejections"]) + [
            {"session": "2026-11-23", "symbol": symbol, "reason": reason, "clock": "14:50"}
        ]
        store["content_sha256"] = _digest(store)
        plan = plan_catchup(store, _prior(["2026-11-20"], store), GAP_TRACKED, today="2026-11-27")
        assert plan["sessions"] == []
        assert plan["stopped"]["session"] == "2026-11-23"
        assert plan["stopped"]["reason"] == "PRICE_BOOK_INCOMPLETE"
        assert any(item["symbol"] == symbol and item["reason"] == reason for item in plan["stopped"]["missing"])

    refuse("SOURCE_MISMATCH")
    refuse("CONFLICTING_CLOSE")
    refuse("SESSION_DATE_MISMATCH")
    refuse("PRICE_INVALID")
    refuse("QUALITY_NOT_OK")
    refuse("LAST_BAR_BEFORE_CLOSE", "HPG")

    truncated_rows = _gap_rows(GAP_SESSIONS, fox_close_on_23=None)
    for row in truncated_rows:
        if row["symbol"] == "HPG" and row["session"] == "2026-11-23":
            row["clock"] = "14:40"
    truncated = _gap_store(GAP_SESSIONS)
    truncated["rows"] = build_reference_store(
        pd.DataFrame(truncated_rows), GAP_SESSIONS, as_of=GAP_SESSIONS[-1]
    )["rows"]
    truncated["content_sha256"] = _digest(truncated)
    truncated_plan = plan_catchup(truncated, _prior(["2026-11-20"], truncated), GAP_TRACKED, today="2026-11-27")
    assert truncated_plan["sessions"] == []
    assert {"symbol": "HPG", "reason": "QUALITY_NOT_OK", "session": "2026-11-23"} in truncated_plan["stopped"]["missing"]


def test_fox_hole_excludes_only_its_horizons_and_recovers_later(tmp_path: Path):
    from research.approximate_returns.report import _performance

    identities_before = (DURABLE / "identities.jsonl").read_bytes()
    pins_before = {relative: _sha256(ROOT / relative) for relative, digest in PINNED_GENERATIONS.items()}
    assert pins_before == dict(PINNED_GENERATIONS)
    store = _gap_store(GAP_SESSIONS)
    plan = plan_catchup(store, _prior(["2026-11-20"], store), GAP_TRACKED, today="2026-11-27")
    assert plan["sessions"] == ["2026-11-23", "2026-11-25", "2026-11-26"]
    ledger, outcomes = _gap_ledger(tmp_path)
    written = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert [item["as_of"] for item in written] == plan["sessions"]
    again = publish_catchup(ledger, outcomes, store, plan["sessions"])
    assert [item["file_status"] for item in again] == ["unchanged", "unchanged", "unchanged"]
    assert [item["index_status"] for item in again] == ["unchanged", "unchanged", "unchanged"]
    first_path = outcomes / "generations" / f"{written[0]['generation_id']}.json"
    first_bytes = first_path.read_bytes()
    sealed = _generation(outcomes, written[0])
    matured = _generation(outcomes, written[-1])
    for document in (sealed, matured):
        assert "2026-11-24" not in document["trading_sessions"]
        fox = _row(document, "FOX", "2026-11-23")
        assert fox["reference_t0_present"] is False
        assert fox["t0_price_used_as_denominator"] is False
        for cell in fox["horizons"].values():
            assert cell["status"] == "T0_REFERENCE_MISSING"
            assert cell["return_pct"] is None
            assert cell["included_in_primary"] is False
            assert cell["target_session"] is None
        hpg = _row(document, "HPG", "2026-11-20")
        assert hpg["horizons"]["T+1"]["status"] == "APPROX_AVAILABLE"
        assert hpg["horizons"]["T+1"]["return_pct"] == _return_pct(1100, 1000)
        assert hpg["horizons"]["T+1"]["included_in_primary"] is True
        assert hpg["horizons"]["T+1"]["target_session"] == "2026-11-23"
        gil = _row(document, "GIL", "2026-11-20")
        assert gil["horizons"]["T+1"]["status"] == "TARGET_MISSING"
        assert gil["horizons"]["T+1"]["return_pct"] is None
        assert gil["horizons"]["T+1"]["included_in_primary"] is False
        assert gil["horizons"]["T+1"]["target_session"] == "2026-11-23"
    sbt = _row(matured, "SBT", "2026-11-23")
    assert sbt["horizons"]["T+1"] == {
        "included_in_primary": True,
        "return_pct": _return_pct(1320, 1200),
        "status": "APPROX_AVAILABLE",
        "target_session": "2026-11-25",
    }
    assert sbt["horizons"]["T+3"]["status"] == "NOT_YET_OBSERVED"
    assert sbt["horizons"]["T+3"]["return_pct"] is None
    assert _row(matured, "HPG", "2026-11-20")["horizons"]["T+3"]["return_pct"] == _return_pct(1210, 1000)
    assert _row(matured, "HPG", "2026-11-20")["horizons"]["T+3"]["included_in_primary"] is True
    gil = _row(matured, "GIL", "2026-11-20")
    assert gil["horizons"]["T+3"]["status"] == "APPROX_AVAILABLE"
    assert gil["horizons"]["T+3"]["return_pct"] == _return_pct(1100, 1000)
    assert gil["horizons"]["T+3"]["included_in_primary"] is True

    sweet = [row for row in matured["rows"] if row["population"] == "sweetspot"]
    sweet_t1 = _performance(sweet, "T+1")
    assert sweet_t1["primary"] == 1
    assert sweet_t1["missing"] == 1
    assert sweet_t1["average_return_pct"] == _return_pct(1320, 1200)
    assert sweet_t1["median_return_pct"] == _return_pct(1320, 1200)
    assert sweet_t1["win_rate_above_3pct"] == 1.0
    assert round((sweet_t1["average_return_pct"] + 0) / 2, 4) != sweet_t1["average_return_pct"]
    coverage = matured["coverage"]["sweetspot"]["horizons"]["T+1"]
    assert coverage["usable_primary"] == 1
    assert coverage["APPROX_AVAILABLE"] == 1
    assert coverage["T0_REFERENCE_MISSING"] == 1
    assert coverage["usable_primary"] == coverage["APPROX_AVAILABLE"]
    brain = [row for row in matured["rows"] if row["population"] == "brain_unlinked"]
    brain_t1 = _performance(brain, "T+1")
    assert brain_t1["primary"] == 1
    assert brain_t1["missing"] == 1
    assert brain_t1["average_return_pct"] == _return_pct(1100, 1000)
    assert brain_t1["median_return_pct"] == _return_pct(1100, 1000)
    assert brain_t1["win_rate_above_3pct"] == 1.0
    assert matured["coverage"]["brain_unlinked"]["horizons"]["T+1"]["TARGET_MISSING"] == 1

    repaired_days = GAP_SESSIONS + ["2026-11-27"]
    repaired = _gap_store(repaired_days, fox_close_on_23=1020)
    repaired_plan = plan_catchup(
        repaired,
        {
            "as_of": "2026-11-26",
            "reference_sha256": written[-1]["reference_sha256"],
            "trading_sessions": list(GAP_SESSIONS),
        },
        GAP_TRACKED,
        today="2026-11-27",
    )
    assert repaired_plan["stopped"] is None
    assert repaired_plan["sessions"] == ["2026-11-27"]
    repaired_written = publish_catchup(ledger, outcomes, repaired, repaired_plan["sessions"])
    assert repaired_written[0]["file_status"] == "written"
    assert first_path.read_bytes() == first_bytes
    healed = _generation(outcomes, repaired_written[0])
    assert "2026-11-24" not in healed["trading_sessions"]
    fox = _row(healed, "FOX", "2026-11-23")
    assert fox["reference_t0_present"] is True
    assert fox["t0_price_used_as_denominator"] is False
    assert fox["horizons"]["T+1"]["status"] == "APPROX_AVAILABLE"
    assert fox["horizons"]["T+1"]["included_in_primary"] is True
    assert fox["horizons"]["T+1"]["return_pct"] == _return_pct(1050, 1020)
    assert fox["horizons"]["T+1"]["return_pct"] != 0
    gil = _row(healed, "GIL", "2026-11-20")
    assert gil["horizons"]["T+1"]["status"] == "TARGET_MISSING"
    assert gil["horizons"]["T+1"]["return_pct"] is None
    assert (DURABLE / "identities.jsonl").read_bytes() == identities_before
    for relative, digest in PINNED_GENERATIONS.items():
        assert _sha256(ROOT / relative) == digest

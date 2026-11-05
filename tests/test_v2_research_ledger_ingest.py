"""Stage A ingest adapters — isolated, idempotent, no publisher side effects."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from research.v2_research_ledger.contract import (
    MARKET_CONTEXT_REF_BRAIN_A_SHADOW,
    NOMINATION_ACCEPTED,
    NOMINATION_REJECTED,
    SOURCE_BRAIN_A,
    SOURCE_SWEETSPOT,
    STATE_NO_OBSERVATION,
    STATE_WAIT,
    STREAM_LIVE_WHEN,
    STREAM_POST_CLOSE,
    T0_MISSING,
    T0_PRESENT,
)
from research.v2_research_ledger.ingest import (
    ingest_brain_a_shadow,
    ingest_stage_a,
    ingest_sweetspot_observer,
    ingest_v2_action_evidence,
    ingest_v2_action_state,
)
from research.v2_research_ledger.ledger import ResearchLedger
from research.v2_research_ledger.serve_generation import publish_serving


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SHADOW = ROOT / "research" / "live_candidate_v2_nomination_shadow" / "nominations.sample.json"


def _shadow_doc() -> dict:
    return json.loads(SAMPLE_SHADOW.read_text(encoding="utf-8"))


def test_brain_a_shadow_keeps_accepted_and_rejected_distinct():
    ledger = ResearchLedger()
    counts = ingest_brain_a_shadow(ledger, _shadow_doc())
    accepted = [r for r in ledger.nominations if r["disposition"] == NOMINATION_ACCEPTED]
    rejected = [r for r in ledger.nominations if r["disposition"] == NOMINATION_REJECTED]
    assert counts.nominations_added == len(accepted) == 6
    assert counts.rejected_added == len(rejected) == 4
    assert all(r["source"] == SOURCE_BRAIN_A for r in ledger.nominations)
    assert all(r["rejection_reason"] for r in rejected)
    assert all(r["candidate_first_seen_ts"] for r in accepted)
    assert all(r["t0_status"] == T0_MISSING for r in rejected)
    assert all(r["price_at_first_seen"] is None for r in rejected)
    assert all(r["candidate_first_seen_ts"] is None for r in rejected)
    # Immutable T0 prices preserved on accepted rows.
    fpt = next(r for r in accepted if r["symbol"] == "FPT")
    assert fpt["t0_status"] == T0_PRESENT
    assert fpt["price_at_first_seen"] == 27.5
    assert fpt["ema9_at_first_seen"] == 27.1
    assert fpt["market_real_at_nomination"] == 7.2
    assert fpt["market_context_source"] == MARKET_CONTEXT_REF_BRAIN_A_SHADOW
    assert fpt["published_observed_at"].startswith("2026-08-14")


def test_rejected_brain_a_without_frozen_t0_is_t0_missing_and_skips_outcomes():
    """Invariant 1: no fabricated T0; forward evaluation excluded until T0 exists."""
    doc = {
        "source": SOURCE_BRAIN_A,
        "observed_at": "2026-08-14T10:05:00+07:00",
        "market_real": 7.0,
        "market_permission": "OK",
        "nominations": [],
        # freeze_ledger for another symbol must not be borrowed onto AAA.
        "freeze_ledger": [
            {
                "session": "2026-08-14",
                "symbol": "FPT",
                "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
                "price_at_first_seen": 27.5,
                "ema9_at_first_seen": 27.1,
                "breakout_ref_at_first_seen": 28.0,
            }
        ],
        "rejected": [
            {
                "symbol": "AAA",
                "setup": "THEO DÕI",
                "reason": "SETUP_EXCLUDED",
            }
        ],
    }
    ledger = ResearchLedger()
    ingest_brain_a_shadow(ledger, doc)
    rejected = ledger.nominations[0]
    assert rejected["disposition"] == NOMINATION_REJECTED
    assert rejected["t0_status"] == T0_MISSING
    assert rejected["price_at_first_seen"] is None
    assert rejected["ema9_at_first_seen"] is None
    assert rejected["breakout_ref_at_first_seen"] is None
    assert rejected["candidate_first_seen_ts"] is None
    assert rejected["published_observed_at"] == "2026-08-14T10:05:00+07:00"
    assert ledger.nomination_forward_eligible(rejected) is False
    episode = {
        "episode_id": "AAA|2026-08-14|UNKNOWN|x",
        "evaluation_session": "2026-08-14",
        "origin_nomination_id": rejected["nomination_id"],
        "symbol": "AAA",
    }
    prices = {
        "2026-08-19": {
            "price": 10.0,
            "price_source": "test",
            "adjustment_status": "EXPLICIT_UNADJUSTED",
            "is_live_adjusted": False,
            "price_ts": "2026-08-19T15:00:00+07:00",
        }
    }
    assert ledger.add_outcomes(episode, as_of=date(2026, 8, 20), prices=prices) == []
    assert ledger.outcomes == []


def test_brain_a_shadow_ingest_is_idempotent():
    ledger = ResearchLedger()
    doc = _shadow_doc()
    first = ingest_brain_a_shadow(ledger, doc)
    second = ingest_brain_a_shadow(ledger, doc)
    assert first.nominations_added == 6
    assert first.rejected_added == 4
    assert second.nominations_added == 0
    assert second.rejected_added == 0
    assert second.nominations_duplicate == 6
    assert second.rejected_duplicate == 4
    assert len(ledger.nominations) == 10


def test_sweetspot_observer_preserves_independent_source_and_t0(tmp_path: Path):
    csv_path = tmp_path / "sweet.csv"
    csv_path.write_text(
        "\n".join(
            [
                "observer_id,t0_date,symbol,observer_status,market_real_t0,market_context_key,price_t0,origin_setup,origin_group,origin_ema9,origin_breakout_ref,matched_sweetspot,created_at",
                "abc,2026-08-14,HPG,MATCHED,6.5,<4|20-40|4-6>,27.5,PULL ĐẸP,PULL ĐẸP,27.1,28.0,cluster_a,2026-08-14T15:35:00+07:00",
                "def,2026-08-14,AAA,INSUFFICIENT_CONTEXT_EVIDENCE,5.0,<4|20-40|4-6>,,,,,,,2026-08-14T15:35:00+07:00",
                "ghi,2026-08-14,,INSUFFICIENT_CONTEXT_EVIDENCE,5.0,<x>,,,,,,,2026-08-14T15:35:00+07:00",
                "",
            ]
        ),
        encoding="utf-8",
    )
    ledger = ResearchLedger()
    counts = ingest_sweetspot_observer(ledger, csv_path)
    assert counts.nominations_added == 1
    assert counts.rejected_added == 1
    # Empty-symbol context row skipped.
    assert len(ledger.nominations) == 2
    sweet = next(r for r in ledger.nominations if r["disposition"] == NOMINATION_ACCEPTED)
    assert sweet["source"] == SOURCE_SWEETSPOT
    assert sweet["provenance_session"] == "2026-08-14"
    assert sweet["price_at_first_seen"] == 27.5
    assert sweet["market_real_at_nomination"] == 6.5
    assert sweet["market_context_source"] == "<4|20-40|4-6>"
    rejected = next(r for r in ledger.nominations if r["disposition"] == NOMINATION_REJECTED)
    assert rejected["source"] == SOURCE_SWEETSPOT
    assert rejected["rejection_reason"] == "INSUFFICIENT_CONTEXT_EVIDENCE"
    assert rejected["t0_status"] == T0_MISSING
    assert rejected["price_at_first_seen"] is None
    assert ledger.nomination_forward_eligible(rejected) is False
    # Rerun does not duplicate.
    again = ingest_sweetspot_observer(ledger, csv_path)
    assert again.nominations_added == 0
    assert again.rejected_added == 0
    assert len(ledger.nominations) == 2


def test_action_evidence_keeps_wait_and_streams_distinct(tmp_path: Path):
    path = tmp_path / "live_when_v2_action_evidence.jsonl"
    rows = [
        {
            "symbol": "FPT",
            "session": "2026-08-14",
            "bar_ts": "2026-08-14T10:05:00+07:00",
            "asof": "2026-08-14T10:05:00+07:00",
            "observed_at": "2026-08-14T10:05:45+07:00",
            "action_state": STATE_WAIT,
            "action_reason": "WAITING_REF",
            "route": "CP MẠNH",
            "setup": "CP MẠNH",
            "close": 27.6,
            "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
            "eligible_from": "2026-08-14T10:05:00+07:00",
            "candidate_is_buy": False,
            "pxv_implies_buy": False,
            "alert_eligible": False,
        },
        {
            "symbol": "FPT",
            "session": "2026-08-14",
            "bar_ts": "2026-08-14T10:10:00+07:00",
            "observed_at": "2026-08-14T10:10:45+07:00",
            "action_state": "BUY_READY",
            "action_reason": "TRIGGER",
            "route": "CP MẠNH",
            "setup": "CP MẠNH",
            "close": 27.8,
            "candidate_is_buy": False,
            "pxv_implies_buy": False,
            "alert_eligible": False,
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ledger = ResearchLedger()
    counts = ingest_v2_action_evidence(ledger, path)
    assert counts.raw_added == 2
    assert {r["action_state"] for r in ledger.raw_events} == {STATE_WAIT, "BUY_READY"}
    assert all(r["source_stream"] == STREAM_LIVE_WHEN for r in ledger.raw_events)
    # Idempotent
    again = ingest_v2_action_evidence(ledger, path)
    assert again.raw_added == 0
    assert again.raw_duplicate == 2
    assert len(ledger.raw_events) == 2


def test_action_state_preserves_no_observation_without_bars():
    ledger = ResearchLedger()
    doc = {
        "session": "2026-08-14",
        "observed_at": "2026-08-14T10:20:00+07:00",
        "rows": [
            {
                "symbol": "MWG",
                "session": "2026-08-14",
                "observation_session": "2026-08-14",
                "shadow_action": STATE_NO_OBSERVATION,
                "action_reason": "NO_OBSERVATION_NO_DATA",
                "route": "MUA EARLY",
                "setup": "MUA EARLY",
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
                "alert_eligible": False,
            },
            {
                "symbol": "HPG",
                "session": "2026-08-14",
                "observation_session": "2026-08-14",
                "shadow_action": STATE_WAIT,
                "action_reason": "WAITING",
                "last_legal_bar_ts": "2026-08-14T10:15:00+07:00",
                "route": "PULL ĐẸP",
                "setup": "PULL ĐẸP",
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
                "alert_eligible": False,
            },
        ],
    }
    counts = ingest_v2_action_state(ledger, doc, source_stream=STREAM_POST_CLOSE)
    assert counts.raw_added == 2
    states = {r["symbol"]: r for r in ledger.raw_events}
    assert states["MWG"]["action_state"] == STATE_NO_OBSERVATION
    assert states["MWG"]["bar_ts"].startswith("NO_BAR|")
    assert states["HPG"]["action_state"] == STATE_WAIT
    assert states["HPG"]["bar_ts"] == "2026-08-14T10:15:00+07:00"
    again = ingest_v2_action_state(ledger, doc, source_stream=STREAM_POST_CLOSE)
    assert again.raw_added == 0
    assert again.raw_duplicate == 2


def test_stage_a_links_brain_a_and_sweetspot_without_merging_sources():
    ledger = ResearchLedger()
    shadow = {
        "source": SOURCE_BRAIN_A,
        "observed_at": "2026-08-14T10:05:00+07:00",
        "market_real": 7.0,
        "market_permission": "OK",
        "nominations": [
            {
                "symbol": "HPG",
                "session": "2026-08-14",
                "setup": "PULL ĐẸP",
                "group": "PULL ĐẸP",
                "candidate_first_seen_ts": "2026-08-14T10:05:00+07:00",
                "eligible_from": "2026-08-14T10:05:00+07:00",
                "price_at_first_seen": 27.5,
                "ema9_at_first_seen": 27.1,
                "breakout_ref_at_first_seen": 28.0,
                "source": SOURCE_BRAIN_A,
                "status": "NOMINATED",
                "market_real": 7.0,
            }
        ],
        "rejected": [],
        "freeze_ledger": [],
    }
    sweet = [
        {
            "observer_id": "x",
            "t0_date": "2026-08-14",
            "symbol": "HPG",
            "observer_status": "MATCHED",
            "market_real_t0": 7.0,
            "market_context_key": "ctx",
            "price_t0": 27.5,
            "origin_setup": "PULL ĐẸP",
            "origin_group": "PULL ĐẸP",
            "matched_sweetspot": "yes",
            "created_at": "2026-08-14T15:35:00+07:00",
        }
    ]
    counts = ingest_stage_a(ledger, brain_a_shadow=shadow, sweetspot_csv=sweet)
    assert counts.nominations_added == 2
    assert counts.links_added == 1
    sources = {r["source"] for r in ledger.nominations}
    assert sources == {SOURCE_BRAIN_A, SOURCE_SWEETSPOT}
    assert len(ledger.links) == 1
    # Second pass: no duplicate nominations or links.
    again = ingest_stage_a(ledger, brain_a_shadow=shadow, sweetspot_csv=sweet)
    assert again.nominations_added == 0
    assert again.links_added == 0
    assert len(ledger.nominations) == 2
    assert len(ledger.links) == 1


def test_stage_a_does_not_alter_existing_publisher_trio_bytes(tmp_path: Path):
    """Ingest must leave any on-disk Phase-1 publisher trio untouched."""
    from tests.test_v2_research_serve_generation import _row, _write_trio

    publisher = tmp_path / "publisher"
    _write_trio(publisher, [_row("brain_a_scan_setup|2026-10-28|HPG|seen")])
    before = {p.name: p.read_bytes() for p in publisher.iterdir() if p.is_file()}
    ledger = ResearchLedger()
    ingest_stage_a(ledger, brain_a_shadow=_shadow_doc())
    after = {p.name: p.read_bytes() for p in publisher.iterdir() if p.is_file()}
    assert before == after
    assert len(ledger.nominations) == 10
    # Promote path remains independently usable after ingest.
    result = publish_serving(publisher, tmp_path / "store")
    assert result.status == "EXPORTED"


def test_no_observation_idempotent_across_restart_and_distinct_cycles(tmp_path: Path):
    """Invariant 2: same cycle dedupes after hydrate; different cycles stay distinct."""
    store = tmp_path / "ledger_store"
    cycle_a = {
        "session": "2026-08-14",
        "observed_at": "2026-08-14T10:20:00+07:00",
        "rows": [
            {
                "symbol": "MWG",
                "session": "2026-08-14",
                "observation_session": "2026-08-14",
                "shadow_action": STATE_NO_OBSERVATION,
                "action_reason": "NO_OBSERVATION_NO_DATA",
                "route": "MUA EARLY",
                "setup": "MUA EARLY",
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
                "alert_eligible": False,
            }
        ],
    }
    cycle_b = {
        "session": "2026-08-14",
        "observed_at": "2026-08-14T10:25:00+07:00",
        "rows": [
            {
                "symbol": "MWG",
                "session": "2026-08-14",
                "observation_session": "2026-08-14",
                "shadow_action": STATE_NO_OBSERVATION,
                "action_reason": "NO_OBSERVATION_NO_DATA",
                "route": "MUA EARLY",
                "setup": "MUA EARLY",
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
                "alert_eligible": False,
            }
        ],
    }

    first = ResearchLedger()
    assert ingest_v2_action_state(first, cycle_a, source_stream=STREAM_POST_CLOSE).raw_added == 1
    first.export_append(store)
    raw_path = store / "action_event_raw.jsonl"
    assert raw_path.is_file()
    lines_after_first = [ln for ln in raw_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines_after_first) == 1

    # Simulate process restart: new ledger, hydrate ids, re-ingest identical cycle.
    restarted = ResearchLedger()
    loaded = restarted.hydrate_ids_from_directory(store)
    assert loaded["raw_events"] == 1
    again = ingest_v2_action_state(restarted, cycle_a, source_stream=STREAM_POST_CLOSE)
    assert again.raw_added == 0
    assert again.raw_duplicate == 1
    assert restarted.raw_events == []
    restarted.export_append(store)
    lines_after_restart = [ln for ln in raw_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines_after_restart == lines_after_first

    # A later genuine cycle (different observed_at) remains a distinct raw event.
    third = ResearchLedger()
    third.hydrate_ids_from_directory(store)
    distinct = ingest_v2_action_state(third, cycle_b, source_stream=STREAM_POST_CLOSE)
    assert distinct.raw_added == 1
    assert third.raw_events[0]["observed_at"] == "2026-08-14T10:25:00+07:00"
    assert third.raw_events[0]["bar_ts"] == "NO_BAR|2026-08-14T10:25:00+07:00"
    third.export_append(store)
    lines_final = [ln for ln in raw_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines_final) == 2
    ids = {json.loads(ln)["raw_id"] for ln in lines_final}
    assert len(ids) == 2


def test_ingest_module_does_not_import_production_pipelines():
    source = (ROOT / "research" / "v2_research_ledger" / "ingest.py").read_text(encoding="utf-8")
    forbidden = (
        "modules.live_candidate_v2_nomination",
        "modules.live_candidate_v2_action",
        "modules.live_camera_shadow",
        "modules.market_aware_sweetspot_observer",
        "modules.position_guardian",
        "publish_serving",
        "export_once",
    )
    for name in forbidden:
        assert name not in source

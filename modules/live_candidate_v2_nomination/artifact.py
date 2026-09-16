"""SHADOW artifact writer. Never touches production dynamic_watchlist.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_nomination.contract import (
    DEFAULT_SHADOW_RELPATH,
    MODE,
    PRODUCTION_WATCHLIST_RELPATH,
    SCHEMA_ID,
    SLICE,
    SRC_BRAIN_A,
    FreezeRecord,
)
from modules.live_candidate_v2_nomination.nominate import NominationReport, nomination_as_dict

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_WATCHLIST = REPO_ROOT / PRODUCTION_WATCHLIST_RELPATH
DEFAULT_SHADOW_PATH = REPO_ROOT / DEFAULT_SHADOW_RELPATH


def _freeze_dict(rec: FreezeRecord) -> dict[str, Any]:
    return {
        "session": rec.session,
        "symbol": rec.symbol,
        "candidate_first_seen_ts": rec.candidate_first_seen_ts,
        "price_at_first_seen": rec.price_at_first_seen,
        "ema9_at_first_seen": rec.ema9_at_first_seen,
        "breakout_ref_at_first_seen": rec.breakout_ref_at_first_seen,
    }


def build_shadow_document(
    report: NominationReport,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = as_vn(generated_at or datetime.now()).isoformat() if generated_at else report.observed_at
    return {
        "schema": SCHEMA_ID,
        "slice": SLICE,
        "mode": MODE,
        "candidate_is_buy": False,
        "candidate_means": "CAMERA_OBSERVATION_ALLOCATION",
        "source": SRC_BRAIN_A,
        "generated_at": generated,
        "observed_at": report.observed_at,
        "market_real": report.market_real,
        "market_permission": report.market_permission,
        "ga_tang_toc": "RESERVED_NOT_IN_SLICE_1",
        "router_wired_to_production": False,
        "notes": [
            "Candidate != BUY.",
            "source_action/source_reason are buy_recommendation provenance only.",
            "observation_intent is a neutral Camera watch task, not a buy action.",
            "BUY ELITE / MUA NHỎ is metadata (elite_buy_grade) only.",
            "GÀ TĂNG TỐC is reserved and not nominated in Slice 1.",
            "Does not overwrite data/live_candidate/dynamic_watchlist.json.",
        ],
        "nominations": [nomination_as_dict(n) for n in report.nominations],
        "rejected": [
            {
                "symbol": r.symbol,
                "setup": r.setup,
                "reason": r.reason,
                "elite_buy_grade": r.elite_buy_grade,
                "winprob": r.winprob,
                "in_early_lab": r.in_early_lab,
            }
            for r in report.rejected
        ],
        "freeze_ledger": [_freeze_dict(r) for r in report.freeze_ledger],
    }


def encode_shadow_text(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def assert_not_production_watchlist(path: Path) -> None:
    resolved = path.resolve()
    if resolved == PRODUCTION_WATCHLIST.resolve():
        raise RuntimeError("refusing to overwrite production dynamic_watchlist.json")
    if path.name == "dynamic_watchlist.json":
        raise RuntimeError("refusing to write a file named dynamic_watchlist.json")
    try:
        resolved.relative_to(PRODUCTION_WATCHLIST.parent.resolve())
    except ValueError:
        return
    raise RuntimeError("refusing to write inside data/live_candidate/")


def write_shadow_artifact(
    report: NominationReport,
    *,
    path: Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    out = Path(path) if path is not None else DEFAULT_SHADOW_PATH
    assert_not_production_watchlist(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = build_shadow_document(report, generated_at=generated_at)
    out.write_text(encode_shadow_text(doc), encoding="utf-8")
    return out

"""Current-session research route for a carried Sweet candidate.

Yesterday's Sweet admission is not today's setup. Today's production scan
row is. The stamp is research-only and is never written to the Brain A
freeze ledger.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_action.contract import (
    REASON_CURRENT_EARLY_QUALIFIER,
    REASON_CURRENT_REFERENCE,
    REASON_CURRENT_UNSUPPORTED,
    REASON_NO_CURRENT_ROUTE,
)
from modules.live_candidate_v2_action.state import action_route, required_reference_kind
from modules.live_candidate_v2_camera.contract import SRC_MARKET_AWARE_SWEETSPOT
from modules.live_candidate_v2_nomination.contract import (
    EXCLUDED_SETUPS,
    PRIMARY_SETUPS,
    QUALIFIED_BY_EARLY_LAB,
    QUALIFIED_BY_TEST_EARLY,
    RESERVED_SETUPS,
    SECONDARY_SETUP,
    BrainANomination,
)
from modules.live_candidate_v2_nomination.intent import (
    REF_BREAKOUT,
    REF_EMA9,
    camera_observation,
    source_action_reason,
)
from modules.live_candidate_v2_nomination.predicate import (
    in_early_lab,
    is_hard_bad,
    is_test_early_action,
    setup_of,
)
from modules.research_market_context.previous_close import append_json_line
from modules.research_shadow_buy.ledger import shadow_buy_dir

STAMP_SCHEMA = "research_shadow_route_stamp.v1"
STAMPS_NAME = "research_route_stamps.jsonl"


def stamps_path(directory: Path | None = None) -> Path:
    return shadow_buy_dir(directory) / STAMPS_NAME


def stamp_key(session: str, symbol: str) -> str:
    return f"{str(session)[:10]}|{str(symbol).strip().upper()}"


def load_research_stamps(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    path = stamps_path(directory)
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        key = str(row.get("stamp_key") or "")
        if key and key not in out:
            out[key] = row
    return out


def _num(row: Mapping[str, Any], key: str) -> float | None:
    if key not in row:
        return None
    from modules.live_candidate_v2_nomination.predicate import as_number

    return as_number(row.get(key))


def qualify_current_scan_row(
    row: Mapping[str, Any] | None,
    *,
    early_lab_symbols: Iterable[str] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Existing route qualification. Market Real is not an input."""
    if row is None:
        return None, REASON_NO_CURRENT_ROUTE
    if is_hard_bad(row):
        return None, REASON_CURRENT_UNSUPPORTED
    setup = setup_of(row)
    if not setup or setup in EXCLUDED_SETUPS or setup in RESERVED_SETUPS:
        return None, REASON_CURRENT_UNSUPPORTED if setup else REASON_NO_CURRENT_ROUTE
    action, action_reason = source_action_reason(row)
    if setup in PRIMARY_SETUPS:
        route = action_route(setup, action)
        kind = required_reference_kind(setup)
        ema9 = _num(row, "ema9")
        brk = _num(row, "breakout_ref")
        if kind == REF_BREAKOUT:
            if brk is None:
                return None, REASON_CURRENT_REFERENCE
        elif ema9 is None:
            return None, REASON_CURRENT_REFERENCE
        return {
            "evaluated_setup": setup,
            "source_action": action,
            "source_reason": action_reason,
            "evaluated_route": route,
            "ema9_at_first_seen": ema9 if kind != REF_BREAKOUT else None,
            "breakout_ref_at_first_seen": brk if kind == REF_BREAKOUT else None,
            "qualification": f"CURRENT_SCAN {setup}",
            "price_at_acquisition": _num(row, "price"),
        }, ""
    if setup == SECONDARY_SETUP:
        lab = in_early_lab(row, early_lab_symbols)
        test_early = is_test_early_action(row)
        if not lab and not test_early:
            return None, REASON_CURRENT_EARLY_QUALIFIER
        ema9 = _num(row, "ema9")
        if ema9 is None:
            return None, REASON_CURRENT_REFERENCE
        tags = []
        if lab:
            tags.append(QUALIFIED_BY_EARLY_LAB)
        if test_early:
            tags.append(QUALIFIED_BY_TEST_EARLY)
        return {
            "evaluated_setup": setup,
            "source_action": action,
            "source_reason": action_reason,
            "evaluated_route": action_route(setup, action),
            "ema9_at_first_seen": ema9,
            "breakout_ref_at_first_seen": None,
            "qualification": "CURRENT_SCAN " + "|".join(tags),
            "price_at_acquisition": _num(row, "price"),
        }, ""
    return None, REASON_CURRENT_UNSUPPORTED


def _stamp_row(nom: BrainANomination, acquired: Mapping[str, Any], when: str) -> dict[str, Any]:
    return {
        "schema": STAMP_SCHEMA,
        "stamp_key": stamp_key(nom.session, nom.symbol),
        "session": str(nom.session)[:10],
        "symbol": nom.symbol,
        "route_became_evaluable_at": when,
        "evaluated_setup": acquired["evaluated_setup"],
        "evaluated_route": acquired["evaluated_route"],
        "source_action": acquired["source_action"],
        "source_reason": acquired["source_reason"],
        "ema9_at_first_seen": acquired["ema9_at_first_seen"],
        "breakout_ref_at_first_seen": acquired["breakout_ref_at_first_seen"],
        "price_at_acquisition": acquired["price_at_acquisition"],
        "qualification": acquired["qualification"],
        "candidate_source": SRC_MARKET_AWARE_SWEETSPOT,
        "origin_setup": nom.origin_setup,
        "origin_group": nom.origin_group,
        "origin_ema9": nom.origin_ema9,
        "origin_breakout_ref": nom.origin_breakout_ref,
        "origin_pull_label": nom.origin_pull_label,
    }


def _apply_acquired(nom: BrainANomination, acquired: Mapping[str, Any], when: str) -> BrainANomination:
    setup = str(acquired["evaluated_setup"])
    intent, ref = camera_observation(setup)
    if setup == "MUA BREAK":
        ref = REF_BREAKOUT
    elif acquired.get("ema9_at_first_seen") is not None:
        ref = REF_EMA9
    return replace(
        nom,
        setup=setup,
        group=setup,
        source_action=str(acquired["source_action"] or nom.source_action),
        source_reason=str(acquired["source_reason"] or nom.source_reason),
        ema9_at_first_seen=acquired.get("ema9_at_first_seen"),
        breakout_ref_at_first_seen=acquired.get("breakout_ref_at_first_seen"),
        observation_intent=intent,
        observation_reference=ref,
        route_became_evaluable_at=when,
        research_qualification=str(acquired.get("qualification") or ""),
        current_route_status="",
        research_stamp=True,
    )


def _apply_status(nom: BrainANomination, status: str) -> BrainANomination:
    return replace(nom, current_route_status=status, research_stamp=False)


def _from_saved(nom: BrainANomination, saved: Mapping[str, Any]) -> BrainANomination:
    return _apply_acquired(
        nom,
        {
            "evaluated_setup": saved.get("evaluated_setup") or "",
            "source_action": saved.get("source_action") or "",
            "source_reason": saved.get("source_reason") or "",
            "evaluated_route": saved.get("evaluated_route") or "",
            "ema9_at_first_seen": saved.get("ema9_at_first_seen"),
            "breakout_ref_at_first_seen": saved.get("breakout_ref_at_first_seen"),
            "qualification": saved.get("qualification") or "",
            "price_at_acquisition": saved.get("price_at_acquisition"),
        },
        str(saved.get("route_became_evaluable_at") or ""),
    )


def attach_sweet_research_route(
    nom: BrainANomination,
    scan_row: Mapping[str, Any] | None,
    *,
    observed_at: datetime,
    early_lab_symbols: Iterable[str] | None = None,
    directory: Path | None = None,
    brain_a_owns: bool = False,
) -> BrainANomination:
    """First honest current-session route. Brain A ownership blocks a stamp."""
    if brain_a_owns or nom.source != SRC_MARKET_AWARE_SWEETSPOT:
        return nom
    key = stamp_key(nom.session, nom.symbol)
    prior = load_research_stamps(directory)
    saved = prior.get(key)
    if saved is not None:
        return _from_saved(nom, saved)
    acquired, status = qualify_current_scan_row(scan_row, early_lab_symbols=early_lab_symbols)
    if acquired is None:
        return _apply_status(nom, status)
    when = as_vn(observed_at).isoformat()
    row = _stamp_row(nom, acquired, when)
    try:
        append_json_line(stamps_path(directory), row)
    except Exception:
        return _apply_status(nom, REASON_NO_CURRENT_ROUTE)
    return _apply_acquired(nom, acquired, when)


def attach_sweet_research_routes(
    nominations: list[BrainANomination],
    scan_rows: Iterable[Mapping[str, Any]] | None,
    *,
    observed_at: datetime,
    early_lab_symbols: Iterable[str] | None = None,
    directory: Path | None = None,
    brain_a_symbols: Iterable[str] | None = None,
) -> list[BrainANomination]:
    by_symbol: dict[str, Mapping[str, Any]] = {}
    for raw in scan_rows or ():
        symbol = str(raw.get("symbol") or "").strip().upper()
        if symbol:
            by_symbol[symbol] = raw
    owned = {str(s).strip().upper() for s in (brain_a_symbols or ())}
    out: list[BrainANomination] = []
    for nom in nominations:
        try:
            out.append(
                attach_sweet_research_route(
                    nom,
                    by_symbol.get(nom.symbol),
                    observed_at=observed_at,
                    early_lab_symbols=early_lab_symbols,
                    directory=directory,
                    brain_a_owns=nom.symbol in owned,
                )
            )
        except Exception:
            out.append(nom)
    return out

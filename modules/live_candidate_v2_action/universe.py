"""Elite ∪ V2 watchlist union for Camera observation.

Does not replace the Elite watchlist. Does not select stocks.
Deduplicates by symbol, keeps V2 provenance, then applies the existing
universe cap. Cap-dropped V2 names are listed explicitly — never treated
as WAIT confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping

import pandas as pd

from modules.live_candidate.calendar import as_vn
from modules.live_camera_shadow.rate import LIVE_UNIVERSE_CAP
from modules.live_camera_shadow.universe import _parse, eligible_watchlist_symbols
from modules.live_candidate_v2_camera.feed_pass import is_v2_camera_row

V2_PRESERVE_KEYS = (
    "setup",
    "group",
    "observation_intent",
    "observation_reference",
    "price_at_first_seen",
    "ema9_at_first_seen",
    "breakout_ref_at_first_seen",
    "candidate_first_seen_ts",
    "candidate_updated_ts",
    "eligible_from",
    "nomination_reason",
    "candidate_reason",
    "nomination_source",
    "source",
    "market_permission",
    "market_real",
    "provenance",
    "session",
    "chronology_status",
    "status",
    "elite_buy_grade",
    "source_action",
    "source_reason",
    "v2_camera",
    "candidate_is_buy",
    "alert_eligible",
)


def _sym(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def _is_v2(row: Mapping[str, Any] | None) -> bool:
    if not row:
        return False
    if row.get("_v2_nomination"):
        return True
    return is_v2_camera_row(row)


@dataclass
class UnionReport:
    """Visible Elite ∪ V2 / cap outcome. Fail-visible, never silent."""

    n_elite: int = 0
    n_v2: int = 0
    n_overlap: int = 0
    n_merged: int = 0
    n_eligible: int = 0
    n_not_yet: int = 0
    n_cap_dropped: int = 0
    n_v2_cap_dropped: int = 0
    hard_cap: int = LIVE_UNIVERSE_CAP
    overlap_symbols: list[str] = field(default_factory=list)
    v2_cap_dropped_symbols: list[str] = field(default_factory=list)
    cap_dropped_symbols: list[str] = field(default_factory=list)
    policy: str = (
        "Elite ∪ V2 by symbol; overlap keeps Elite poll identity + V2 nomination "
        "provenance; eligible_watchlist_symbols cap applies once; dropped V2 → "
        "NO_OBSERVATION, never WAIT."
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_elite": self.n_elite,
            "n_v2": self.n_v2,
            "n_overlap": self.n_overlap,
            "n_merged": self.n_merged,
            "n_eligible": self.n_eligible,
            "n_not_yet": self.n_not_yet,
            "n_cap_dropped": self.n_cap_dropped,
            "n_v2_cap_dropped": self.n_v2_cap_dropped,
            "hard_cap": self.hard_cap,
            "overlap_symbols": list(self.overlap_symbols),
            "v2_cap_dropped_symbols": list(self.v2_cap_dropped_symbols),
            "cap_dropped_symbols": list(self.cap_dropped_symbols),
            "policy": self.policy,
        }


def current_session_v2_rows(
    rows: Iterable[Mapping[str, Any]] | None,
    session: str,
) -> list[dict[str, Any]]:
    """Only current-session sidecar nominations. Missing session is dropped."""
    want = str(session or "").strip()
    out: list[dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("session") or "").strip() != want:
            continue
        rec = dict(raw)
        rec["symbol"] = _sym(rec)
        if not rec["symbol"]:
            continue
        rec["v2_camera"] = True
        rec["candidate_is_buy"] = False
        rec["alert_eligible"] = False
        out.append(rec)
    return out


def merge_elite_v2(
    elite_rows: Iterable[Mapping[str, Any]] | None,
    v2_rows: Iterable[Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], UnionReport]:
    """Dedup by symbol. Elite poll row wins; V2 chronology/refs kept on `_v2_nomination`."""
    elite_list = [dict(r) for r in (elite_rows or []) if _sym(r)]
    v2_list = [dict(r) for r in (v2_rows or []) if _sym(r)]
    for rec in elite_list:
        rec["symbol"] = _sym(rec)
    for rec in v2_list:
        rec["symbol"] = _sym(rec)
        rec["v2_camera"] = True
        rec["candidate_is_buy"] = False
        rec["alert_eligible"] = False

    elite_by = {r["symbol"]: r for r in elite_list}
    v2_by = {r["symbol"]: r for r in v2_list}
    overlap = sorted(set(elite_by) & set(v2_by))

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in elite_list:
        sym = rec["symbol"]
        if sym in seen:
            continue
        seen.add(sym)
        row = dict(rec)
        row["_sources"] = ["elite"]
        v2 = v2_by.get(sym)
        if v2 is not None:
            row["_sources"] = ["elite", "v2"]
            row["_v2_nomination"] = {k: v2.get(k) for k in V2_PRESERVE_KEYS if k in v2}
            row["_v2_nomination"]["symbol"] = sym
            row["_v2_provenance"] = True
            # Do not flip Elite live_evidence onto the V2 Camera path.
            row.pop("v2_camera", None)
        merged.append(row)
    for rec in v2_list:
        sym = rec["symbol"]
        if sym in seen:
            continue
        seen.add(sym)
        row = dict(rec)
        row["_sources"] = ["v2"]
        row["_v2_nomination"] = dict(rec)
        row["_v2_provenance"] = True
        row["v2_camera"] = True
        row["candidate_is_buy"] = False
        merged.append(row)

    report = UnionReport(
        n_elite=len(elite_by),
        n_v2=len(v2_by),
        n_overlap=len(overlap),
        n_merged=len(merged),
        overlap_symbols=overlap,
    )
    return merged, report


def apply_universe_cap(
    merged: list[dict[str, Any]],
    *,
    now: datetime,
    cap: int = LIVE_UNIVERSE_CAP,
    report: UnionReport | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], UnionReport]:
    """Run existing eligible_watchlist_symbols. Return (universe, cap_dropped, report)."""
    now_l = as_vn(now)
    report = report or UnionReport()
    report.hard_cap = cap
    universe = eligible_watchlist_symbols(merged, now=now_l, cap=cap)
    listed = {_sym(r) for r in universe}
    report.n_eligible = sum(1 for r in universe if r.get("_skip") != "NOT_YET_ELIGIBLE")
    report.n_not_yet = sum(1 for r in universe if r.get("_skip") == "NOT_YET_ELIGIBLE")

    dropped: list[dict[str, Any]] = []
    for rec in merged:
        sym = _sym(rec)
        if not sym:
            continue
        parsed = _parse(rec.get("eligible_from"))
        if parsed is None:
            continue
        if parsed <= pd.Timestamp(now_l) and sym not in listed:
            dropped.append(rec)

    report.n_cap_dropped = len(dropped)
    report.cap_dropped_symbols = [_sym(r) for r in dropped]
    report.v2_cap_dropped_symbols = [_sym(r) for r in dropped if _is_v2(r)]
    report.n_v2_cap_dropped = len(report.v2_cap_dropped_symbols)
    return universe, dropped, report


def union_watchlist(
    elite_rows: Iterable[Mapping[str, Any]] | None,
    v2_rows: Iterable[Mapping[str, Any]] | None,
    *,
    now: datetime,
    cap: int = LIVE_UNIVERSE_CAP,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], UnionReport]:
    merged, report = merge_elite_v2(elite_rows, v2_rows)
    return apply_universe_cap(merged, now=now, cap=cap, report=report)


def v2_nomination_of(rec: Mapping[str, Any]) -> dict[str, Any] | None:
    nested = rec.get("_v2_nomination")
    if isinstance(nested, Mapping):
        out = dict(nested)
        out.setdefault("symbol", _sym(rec))
        return out
    if is_v2_camera_row(rec):
        return dict(rec)
    return None

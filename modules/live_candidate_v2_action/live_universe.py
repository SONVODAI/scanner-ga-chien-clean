"""V2-only actionable universe for the live SHADOW WHEN cycle.

Selects rows the existing Action state machine can still take to BUY_READY.
Does not nominate, does not score, and does not treat Elite or Sweet as polls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from modules.live_candidate.calendar import as_vn
from modules.live_camera_shadow.rate import LIVE_UNIVERSE_CAP
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
    ROUTE_BREAK,
    ROUTE_EARLY,
    ROUTE_MANH,
    ROUTE_PULL,
)
from modules.live_candidate_v2_camera.github_bus import validate_v2_sidecar_document
from modules.live_candidate_v2_camera.observe import pxv_implies_buy

# Routes evaluate_shadow_action can still move to BUY_READY.
# MUA EARLY is observed so completed 5m bars can reach its own WHEN rule.
# Empty/UNKNOWN setups stay out.
ACTIONABLE_LIVE_SETUPS = frozenset(ROUTE_PULL | {ROUTE_MANH, ROUTE_BREAK, ROUTE_EARLY})


@dataclass
class ActionableUniverse:
    """One frozen snapshot. `fetch` is the KBS poll. `not_yet` is not polled."""

    fetch: list[dict[str, Any]] = field(default_factory=list)
    not_yet: list[dict[str, Any]] = field(default_factory=list)
    cap_dropped: list[dict[str, Any]] = field(default_factory=list)
    n_actionable: int = 0
    hard_cap: int = LIVE_UNIVERSE_CAP

    @property
    def empty(self) -> bool:
        return self.n_actionable == 0


def _setup(row: Mapping[str, Any]) -> str:
    return str(row.get("setup") or row.get("group") or "").strip()


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def _parse_ts(raw: object) -> pd.Timestamp | None:
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Ho_Chi_Minh")
    else:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh")
    return ts


def _stamp_v2(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep nomination fields. Do not recompute frozen refs."""
    out = dict(row)
    out["symbol"] = _symbol(out)
    out["v2_camera"] = True
    out["candidate_is_buy"] = False
    out["alert_eligible"] = False
    out["pxv_implies_buy"] = False
    return out


def _merge_provenance(winner: dict[str, Any], others: Sequence[Mapping[str, Any]]) -> None:
    prov = list(winner.get("provenance") or [])
    seen = {
        (
            str(item.get("source") or ""),
            str(item.get("setup") or item.get("group") or ""),
            str(item.get("candidate_first_seen_ts") or ""),
        )
        for item in prov
        if isinstance(item, Mapping)
    }
    for other in others:
        entry = {
            "source": other.get("nomination_source") or other.get("source") or "",
            "setup": _setup(other),
            "group": other.get("group") or _setup(other),
            "candidate_first_seen_ts": other.get("candidate_first_seen_ts") or "",
            "eligible_from": other.get("eligible_from") or "",
            "session": other.get("session") or "",
        }
        key = (str(entry["source"]), str(entry["setup"]), str(entry["candidate_first_seen_ts"]))
        if key in seen:
            continue
        seen.add(key)
        prov.append(entry)
    winner["provenance"] = prov


def document_rows_for_live_when(
    document: Mapping[str, Any] | None,
    *,
    session: date | str,
) -> tuple[list[dict[str, Any]], str]:
    """Validate one Gate-B document. Keep every row.

    Document ``session`` must be the cycle's calendar day. Nomination
    ``row.session`` is scan provenance and is not required to match that day.
    """
    sess = session.isoformat() if isinstance(session, date) else str(session or "").strip()
    if not isinstance(document, Mapping):
        return [], "SIDECAR_ABSENT"
    reason = validate_v2_sidecar_document(document)
    if reason:
        return [], f"SIDECAR_INVALID:{reason}"
    if (
        document.get("candidate_is_buy") is True
        or document.get("alert_eligible") is True
        or document.get("pxv_implies_buy") is True
        or CANDIDATE_IS_BUY
        or PXV_IMPLIES_BUY
        or ALERT_ELIGIBLE
        or pxv_implies_buy(None) is not False
    ):
        return [], "SIDECAR_PERMISSIONS_NOT_SHADOW"
    doc_session = str(document.get("session") or "").strip()
    if doc_session != sess:
        return [], "SIDECAR_STALE_SESSION"
    raw = document.get("rows")
    if not isinstance(raw, list):
        return [], "SIDECAR_INVALID:rows"
    rows = [dict(item) for item in raw if isinstance(item, Mapping)]
    return rows, ""


def select_actionable_v2(
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    now: datetime,
    cap: int = LIVE_UNIVERSE_CAP,
) -> ActionableUniverse:
    """PULL / MẠNH / BREAK / EARLY. Dedup by symbol. Cap applies to the fetch list."""
    now_ts = pd.Timestamp(as_vn(now))
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for raw in rows or []:
        if not isinstance(raw, Mapping):
            continue
        if _setup(raw) not in ACTIONABLE_LIVE_SETUPS:
            continue
        symbol = _symbol(raw)
        if not symbol:
            continue
        by_symbol.setdefault(symbol, []).append(_stamp_v2(raw))

    eligible: list[dict[str, Any]] = []
    not_yet: list[dict[str, Any]] = []
    for symbol in sorted(by_symbol):
        group = by_symbol[symbol]
        group.sort(
            key=lambda rec: (
                str(rec.get("eligible_from") or ""),
                str(rec.get("candidate_first_seen_ts") or ""),
                str(rec.get("source") or ""),
            )
        )
        winner = dict(group[-1])
        _merge_provenance(winner, group[:-1])
        elig = _parse_ts(winner.get("eligible_from"))
        if elig is None or now_ts < elig:
            winner["_skip"] = "NOT_YET_ELIGIBLE"
            not_yet.append(winner)
            continue
        eligible.append(winner)

    eligible.sort(key=lambda rec: (str(rec.get("eligible_from") or ""), rec["symbol"]))
    limit = max(0, int(cap))
    fetch = eligible[:limit]
    dropped = eligible[limit:]
    for rec in dropped:
        rec["_skip"] = "CAP"
    return ActionableUniverse(
        fetch=fetch,
        not_yet=not_yet,
        cap_dropped=dropped,
        n_actionable=len(by_symbol),
        hard_cap=limit,
    )

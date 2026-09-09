"""View-model for the read-only LIVE CANDIDATE × P×V panel.

Sorts and labels already-produced shadow state. Does not call Camera,
does not recompute P×V, does not write files.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from modules.intraday_pxv_v1.constants import (
    EV_NEUTRAL,
    EV_STRENGTHEN,
    EV_UNUSABLE,
    EV_WEAKEN,
)
from modules.live_candidate.calendar import as_vn
from modules.live_candidate_pxv_ui.read import load_panel_sources

DIRECTIONAL = {EV_STRENGTHEN, EV_WEAKEN}
FAILURE_STATUSES = {
    "NO_DATA",
    "STALE_BAR",
    "RATE_LIMITED",
    "PROVIDER_ERROR",
    "UNUSABLE",
    "NOT_YET_ELIGIBLE",
}
RUNNER_STALE_AFTER = timedelta(minutes=10)

EMPTY_MESSAGE = "No active BOT Candidate."
WAITING_MESSAGE = "Waiting for first eligible completed 5m bar."
WAITING_MESSAGE_VI = "Chờ nến 5m hoàn chỉnh đầu tiên đủ điều kiện."
NEUTRAL_WATCH_VI = "Candidate vẫn đang được theo dõi."
STALE_BANNER = "Live-shadow runner STALE / stopped. Evidence below is NOT current."
NOT_LEGAL_NOTE = "chronology_legal=false — không trình bày như bằng chứng hợp lệ."

# Thin Vietnamese frames around existing Interpreter why-strings. Not new reasons.
WHY_VI = {
    "no confirming or weakening P×V event at this bar": (
        "Chưa có sự kiện P×V xác nhận hoặc suy yếu tại nến này."
    ),
    "5m expansion with P×V CONFIRMING": "Khối lượng 5m mở rộng kèm P×V CONFIRMING.",
    "pace ahead with P×V CONFIRMING": "Nhịp khối lượng vượt kèm P×V CONFIRMING.",
    "price up on contracted volume": "Giá tăng trên khối lượng co lại.",
    "selling-pressure volume expansion vs long candidate thesis": (
        "Khối lượng mở rộng theo hướng bán so với luận điểm Candidate long."
    ),
    "gate UNUSABLE — no volume evidence": "Gate UNUSABLE — không có bằng chứng khối lượng.",
    "CONFLICT: confirming expansion/pace vs weak-up or sell-expansion": (
        "CONFLICT: expansion/pace xác nhận đối với weak-up hoặc sell-expansion."
    ),
}


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return as_vn(value)
    try:
        import pandas as pd

        ts = pd.to_datetime(value, errors="coerce")
        if ts is None or pd.isna(ts):
            return None
        return as_vn(ts.to_pydatetime())
    except Exception:
        return None


def _hm(value: Any) -> str:
    ts = _parse_ts(value)
    if ts is None:
        return ""
    return ts.strftime("%H:%M")


def _iso(value: Any) -> str:
    ts = _parse_ts(value)
    return ts.isoformat() if ts else str(value or "")


def _translate_why(why: str) -> str:
    text = str(why or "").strip()
    if not text:
        return ""
    if text in WHY_VI:
        return WHY_VI[text]
    for eng, vie in WHY_VI.items():
        if eng in text:
            return text.replace(eng, vie)
    return text


def _compose_explanation(
    *,
    waiting: bool,
    evidence_valid: bool,
    raw: str,
    published: str,
    evidence_why: str,
    published_why: str,
    chronology_legal: Optional[bool],
    stale: bool,
) -> str:
    if waiting:
        return f"{WAITING_MESSAGE} {WAITING_MESSAGE_VI}"
    if chronology_legal is False:
        return NOT_LEGAL_NOTE
    if not evidence_valid:
        return NOT_LEGAL_NOTE
    why = _translate_why(evidence_why) or _translate_why(published_why)
    parts: list[str] = []
    if stale:
        parts.append("Dữ liệu không còn live.")
    if why:
        parts.append(why)
    if published == EV_NEUTRAL and raw == EV_NEUTRAL:
        parts.append(NEUTRAL_WATCH_VI)
    return " ".join(p for p in parts if p).strip()


def _symbol_status(status: dict[str, Any], symbol: str) -> dict[str, Any]:
    for rec in status.get("symbols") or []:
        if str(rec.get("symbol") or "").upper() == symbol:
            return rec
    return {}


def _runner_freshness(status: dict[str, Any], now: datetime) -> dict[str, Any]:
    observed = _parse_ts(status.get("observed_at"))
    symbols = list(status.get("symbols") or [])
    fail = [
        str(s.get("status") or "")
        for s in symbols
        if str(s.get("status") or "") in {"PROVIDER_ERROR", "RATE_LIMITED", "STALE_BAR"}
    ]
    if not status:
        return {
            "label": "STOPPED",
            "detail": "Không có live_shadow_status.json",
            "observed_at": "",
            "age_sec": None,
            "is_stale": True,
            "is_live": False,
            "banner": STALE_BANNER,
        }
    age = (now - observed).total_seconds() if observed else None
    if fail:
        label = fail[0]
        stale = True
    elif observed is None:
        label = "STOPPED"
        stale = True
    elif age is not None and age > RUNNER_STALE_AFTER.total_seconds():
        label = "STALE"
        stale = True
    else:
        label = "LIVE"
        stale = False
    banner = STALE_BANNER if stale else ""
    return {
        "label": label,
        "detail": f"observed_at={observed.isoformat() if observed else 'missing'} age={int(age) if age is not None else 'n/a'}s",
        "observed_at": observed.isoformat() if observed else "",
        "age_sec": age,
        "is_stale": stale,
        "is_live": not stale,
        "banner": banner,
        "failures": fail,
    }


def _legal_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("chronology_legal") is True]


def _transitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Meaningful RAW/PUBLISHED transitions only — not every 5m print."""
    ordered = sorted(rows, key=lambda r: str(r.get("bar_ts") or r.get("asof") or ""))
    out: list[dict[str, Any]] = []
    prev_raw = None
    prev_pub = None
    for r in ordered:
        raw = str(r.get("raw_evidence") or "")
        pub = str(r.get("published_evidence") or "")
        legal = r.get("chronology_legal")
        if prev_raw is None and prev_pub is None:
            out.append(
                {
                    "bar_ts": r.get("bar_ts"),
                    "asof_hm": r.get("asof_hm") or _hm(r.get("bar_ts")),
                    "raw_from": "",
                    "raw_to": raw,
                    "published_from": "",
                    "published_to": pub,
                    "kind": "UNUSABLE / data failure" if (legal is False or raw == EV_UNUSABLE or pub == EV_UNUSABLE) else f"start {pub or raw}",
                    "chronology_legal": legal,
                    "evidence_why": r.get("evidence_why") or "",
                }
            )
            prev_raw, prev_pub = raw, pub
            continue
        if raw == prev_raw and pub == prev_pub:
            continue
        kind = _transition_kind(prev_pub, pub, prev_raw, raw, legal)
        out.append(
            {
                "bar_ts": r.get("bar_ts"),
                "asof_hm": r.get("asof_hm") or _hm(r.get("bar_ts")),
                "raw_from": prev_raw,
                "raw_to": raw,
                "published_from": prev_pub,
                "published_to": pub,
                "kind": kind,
                "chronology_legal": legal,
                "evidence_why": r.get("evidence_why") or "",
            }
        )
        prev_raw, prev_pub = raw, pub
    return out


def _transition_kind(prev_pub: str, pub: str, prev_raw: str, raw: str, legal: Any) -> str:
    if legal is False or pub == EV_UNUSABLE or raw == EV_UNUSABLE:
        return "UNUSABLE / data failure"
    pair = (prev_pub, pub)
    if pair == (EV_NEUTRAL, EV_STRENGTHEN):
        return "NEUTRAL → STRENGTHEN"
    if pair == (EV_NEUTRAL, EV_WEAKEN):
        return "NEUTRAL → WEAKEN"
    if pair == (EV_STRENGTHEN, EV_NEUTRAL):
        return "STRENGTHEN → NEUTRAL"
    if pair == (EV_WEAKEN, EV_NEUTRAL):
        return "WEAKEN → NEUTRAL"
    if pair in {(EV_STRENGTHEN, EV_WEAKEN), (EV_WEAKEN, EV_STRENGTHEN)}:
        return "STRENGTHEN ↔ WEAKEN"
    if prev_pub != pub:
        return f"{prev_pub} → {pub}"
    return f"RAW {prev_raw} → {raw}"


def _sort_rank(card: dict[str, Any]) -> tuple:
    pub = card.get("published_evidence") or ""
    raw = card.get("raw_evidence") or ""
    valid = bool(card.get("evidence_valid"))
    waiting = bool(card.get("waiting_first_bar"))
    data = str(card.get("data_state") or "")
    unavail = (not valid) or waiting or data in FAILURE_STATUSES or data == EV_UNUSABLE
    if unavail:
        bucket = 3
    elif pub in DIRECTIONAL:
        bucket = 0
    elif raw in DIRECTIONAL:
        bucket = 1
    else:
        bucket = 2
    obs = _parse_ts(card.get("observed_at"))
    obs_key = -(obs.timestamp()) if obs else 0.0
    return (bucket, obs_key, card.get("symbol") or "")


@dataclass
class PanelState:
    empty: bool
    empty_message: str
    runner: dict[str, Any]
    cards: list[dict[str, Any]] = field(default_factory=list)
    alert_eligible: bool = False
    provider_called: bool = False
    files_written: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_panel(
    *,
    now: datetime,
    watchlist_path: Path | None = None,
    evidence_path: Path | None = None,
    status_path: Path | None = None,
    sources: dict[str, Any] | None = None,
) -> PanelState:
    """Build the observation panel. Read-only. alert_eligible always false."""
    now = as_vn(now)
    src = sources if sources is not None else load_panel_sources(
        watchlist_path=watchlist_path,
        evidence_path=evidence_path,
        status_path=status_path,
    )
    watchlist = list(src.get("watchlist") or [])
    evidence = list(src.get("evidence") or [])
    status = dict(src.get("status") or {})
    runner = _runner_freshness(status, now)
    stale = bool(runner["is_stale"])

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in evidence:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        by_symbol.setdefault(sym, []).append(row)

    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in watchlist:
        symbol = str(rec.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        rows = by_symbol.get(symbol, [])
        legal = _legal_rows(rows)
        latest = None
        if legal:
            latest = max(
                legal,
                key=lambda r: str(r.get("bar_ts") or r.get("observed_at") or ""),
            )
        sym_st = _symbol_status(status, symbol)
        runner_sym = str(sym_st.get("status") or "")
        illegal_only = latest is None and any(r.get("chronology_legal") is False for r in rows)
        waiting = (
            latest is None
            and not illegal_only
            and runner_sym in {"", "WAITING_COMPLETED_BAR", "OK", "NOT_YET_ELIGIBLE"}
        )
        if latest is None and runner_sym in FAILURE_STATUSES and not illegal_only:
            waiting = runner_sym == "NOT_YET_ELIGIBLE"
        evidence_valid = latest is not None and latest.get("chronology_legal") is True
        raw = str(latest.get("raw_evidence") or "") if latest else ""
        published = str(latest.get("published_evidence") or "") if latest else ""
        data_state = ""
        if runner_sym in FAILURE_STATUSES:
            data_state = runner_sym
        elif latest:
            data_state = str(latest.get("data_state") or latest.get("data_quality") or "")
        elif illegal_only:
            data_state = "UNUSABLE"
        elif waiting:
            data_state = "WAITING"
        chronology = latest.get("chronology_legal") if latest else (False if illegal_only else None)
        if chronology is not True:
            evidence_valid = False
            published = ""
            raw = ""
        card = {
            "symbol": symbol,
            "candidate_reason": str(rec.get("candidate_reason") or ""),
            "candidate_first_seen_ts": str(rec.get("candidate_first_seen_ts") or ""),
            "candidate_first_seen_hm": _hm(rec.get("candidate_first_seen_ts")),
            "eligible_from": str(rec.get("eligible_from") or ""),
            "eligible_from_hm": _hm(rec.get("eligible_from")),
            "latest_bar_ts": str(latest.get("bar_ts") or "") if latest and evidence_valid else "",
            "latest_asof_hm": str(latest.get("asof_hm") or _hm(latest.get("bar_ts"))) if latest and evidence_valid else "",
            "observed_at": str(latest.get("observed_at") or "") if latest and evidence_valid else (sym_st.get("observed_at") or ""),
            "raw_evidence": raw if evidence_valid else "",
            "published_evidence": published if evidence_valid else "",
            "data_state": data_state or ("UNUSABLE" if chronology is False else ""),
            "data_quality": str((latest or {}).get("data_quality") or ""),
            "chronology_legal": chronology,
            "evidence_why": str((latest or {}).get("evidence_why") or "") if evidence_valid else "",
            "published_why": str((latest or {}).get("published_why") or "") if evidence_valid else "",
            "explanation": _compose_explanation(
                waiting=waiting and not evidence_valid,
                evidence_valid=bool(evidence_valid),
                raw=raw if evidence_valid else "",
                published=published if evidence_valid else "",
                evidence_why=str((latest or {}).get("evidence_why") or ""),
                published_why=str((latest or {}).get("published_why") or ""),
                chronology_legal=chronology,
                stale=stale,
            ),
            "waiting_first_bar": bool(waiting and not evidence_valid),
            "evidence_valid": bool(evidence_valid),
            "freshness": "STALE" if stale else ("LIVE" if evidence_valid else runner["label"]),
            "runner_symbol_status": runner_sym,
            "alert_eligible": False,
            "history": _transitions(rows),
        }
        if not evidence_valid and chronology is False:
            card["published_evidence"] = ""
            card["raw_evidence"] = ""
            card["latest_bar_ts"] = ""
            card["latest_asof_hm"] = ""
            card["explanation"] = NOT_LEGAL_NOTE
            card["waiting_first_bar"] = False
        cards.append(card)

    cards.sort(key=_sort_rank)
    empty = len(cards) == 0
    return PanelState(
        empty=empty,
        empty_message=EMPTY_MESSAGE if empty else "",
        runner=runner,
        cards=cards,
        alert_eligible=False,
        provider_called=False,
        files_written=False,
    )

"""Slice 1 orchestrator: gate first, then features, then evidence. Shadow only."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd

from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_pxv_v1.archive import overlay_session, symbol_session_bars
from modules.intraday_pxv_v1.candidates import CandidateEvent, thesis_is_long
from modules.intraday_pxv_v1.constants import (
    EV_STRENGTHEN,
    EV_WEAKEN,
    MODE_SHADOW,
    RESEARCH_DEFAULT_EVAL_START_BAR,
    RESEARCH_DEFAULT_PERSISTENCE_BARS,
    TOD_PRELIMINARY,
)
from modules.intraday_pxv_v1.evidence import decide_evidence
from modules.intraday_pxv_v1.features import compute_features
from modules.intraday_pxv_v1.gate import GATE_INTERVAL, GateResult, evaluate_gate
from modules.intraday_pxv_v1.message import render_message

LEDGER_VERSION = "pxv_v1_slice1"


@dataclass
class LedgerRow:
    symbol: str
    session: str
    asof: str
    asof_hm: str
    candidate_reason: str
    candidate_ts: str
    bot_context: str
    candidate_source: str
    data_state: str
    gate_reason: str
    volume_kind: str
    tod_maturity: str
    overlay_applied: bool
    bar_source_last: str
    n_bars: int
    expected_bars: int
    features: dict[str, Any]
    evidence: str
    evidence_why: str
    message: str
    alert_eligible: bool
    would_be_alert: bool
    research_default_flags: list[str]
    mode: str
    ledger_version: str


def _hm(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(VN_TZ)
    return t.strftime("%H:%M")


def build_tod_baselines(
    sessions: dict[date, pd.DataFrame],
    symbols: Iterable[str],
) -> dict[str, dict[str, dict[str, list[float]]]]:
    """Per symbol → slot → {rvol: [vols], pace: [cums]} from interval-like full sessions."""
    store: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: {"rvol": [], "pace": []})
    )
    symbols_u = {s.upper() for s in symbols}
    for sess, overlay in sessions.items():
        if overlay is None or overlay.empty:
            continue
        for symbol in sorted(set(overlay["symbol"].astype(str)) & symbols_u):
            bars = symbol_session_bars(overlay, symbol)
            gate = evaluate_gate(bars, tod_qualified_sessions=0)
            if not gate.allow_increments or gate.volume_kind != GATE_INTERVAL:
                continue
            if gate.gate_reason.startswith("THIN") or gate.gate_reason.startswith("STRUCTURAL"):
                continue
            work = bars.sort_values("timestamp")
            vols = pd.to_numeric(work["volume"], errors="coerce").fillna(0.0)
            cums = vols.cumsum()
            for i, (_, row) in enumerate(work.iterrows()):
                slot = _hm(row["timestamp"])
                store[symbol][slot]["rvol"].append(float(vols.iloc[i]))
                store[symbol][slot]["pace"].append(float(cums.iloc[i]))
    return store


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = pd.Series(values)
    return float(s.median())


def interpret_asof(
    bars: pd.DataFrame,
    *,
    asof: datetime,
    candidate: CandidateEvent,
    tod_store: dict[str, dict[str, dict[str, list[float]]]] | None,
    tod_qualified_sessions: int,
) -> LedgerRow:
    sliced = bars[bars["timestamp"] <= pd.Timestamp(asof)].copy()
    if sliced.empty and bars is not None and not bars.empty:
        sliced = bars.iloc[0:0]
    gate = evaluate_gate(
        sliced if not sliced.empty else bars,
        asof=asof,
        tod_qualified_sessions=tod_qualified_sessions,
    )
    slot = _hm(asof)
    rvol_base = pace_base = None
    if tod_store and candidate.symbol in tod_store:
        rvol_base = _median(tod_store[candidate.symbol].get(slot, {}).get("rvol", []))
        pace_base = _median(tod_store[candidate.symbol].get(slot, {}).get("pace", []))

    features = compute_features(
        sliced if not sliced.empty else bars,
        gate,
        asof=asof,
        tod_rvol_baseline=rvol_base,
        tod_pace_baseline=pace_base,
    )
    ev = decide_evidence(gate, features, thesis_long=thesis_is_long(candidate.candidate_reason))
    last_src = ""
    if sliced is not None and not sliced.empty and "bar_source" in sliced.columns:
        last_src = str(sliced.iloc[-1].get("bar_source", ""))
    flags = ["RESEARCH_DEFAULT"]
    if gate.tod_maturity == TOD_PRELIMINARY:
        flags.append("TOD_PRELIMINARY")
    if gate.overlay_applied:
        flags.append("QUARANTINE_OVERLAY")
    msg = render_message(
        symbol=candidate.symbol,
        asof_hm=slot,
        candidate_reason=candidate.candidate_reason,
        gate=gate,
        features=features,
        evidence=ev,
    )
    return LedgerRow(
        symbol=candidate.symbol,
        session=candidate.session.isoformat(),
        asof=pd.Timestamp(asof).isoformat(),
        asof_hm=slot,
        candidate_reason=candidate.candidate_reason,
        candidate_ts=candidate.candidate_ts,
        bot_context=candidate.bot_context,
        candidate_source=candidate.source,
        data_state=gate.data_state,
        gate_reason=gate.gate_reason,
        volume_kind=gate.volume_kind,
        tod_maturity=gate.tod_maturity,
        overlay_applied=gate.overlay_applied,
        bar_source_last=last_src,
        n_bars=gate.n_bars,
        expected_bars=gate.expected_bars,
        features=features,
        evidence=ev.evidence,
        evidence_why=ev.evidence_why,
        message=msg,
        alert_eligible=False,
        would_be_alert=False,
        research_default_flags=flags,
        mode=MODE_SHADOW,
        ledger_version=LEDGER_VERSION,
    )


def interpret_candidate_session(
    overlay: pd.DataFrame,
    candidate: CandidateEvent,
    tod_store: dict[str, dict[str, dict[str, list[float]]]] | None,
    tod_qualified_sessions: int,
) -> list[LedgerRow]:
    bars = symbol_session_bars(overlay, candidate.symbol)
    if bars.empty:
        row = interpret_asof(
            bars,
            asof=datetime.combine(candidate.session, datetime.min.time()).replace(tzinfo=VN_TZ),
            candidate=candidate,
            tod_store=tod_store,
            tod_qualified_sessions=tod_qualified_sessions,
        )
        return [row]

    rows: list[LedgerRow] = []
    start = max(RESEARCH_DEFAULT_EVAL_START_BAR - 1, 0)
    persist = 0
    last_ev = None
    fired: set[str] = set()
    for i in range(start, len(bars)):
        asof = bars.iloc[i]["timestamp"].to_pydatetime()
        row = interpret_asof(
            bars,
            asof=asof,
            candidate=candidate,
            tod_store=tod_store,
            tod_qualified_sessions=tod_qualified_sessions,
        )
        if row.evidence == last_ev and row.evidence in {EV_STRENGTHEN, EV_WEAKEN}:
            persist += 1
        else:
            persist = 1 if row.evidence in {EV_STRENGTHEN, EV_WEAKEN} else 0
        last_ev = row.evidence
        key = f"{row.evidence}"
        if (
            persist >= RESEARCH_DEFAULT_PERSISTENCE_BARS
            and key not in fired
            and row.evidence in {EV_STRENGTHEN, EV_WEAKEN}
            and row.data_state not in {"UNUSABLE", "LOW_CONFIDENCE"}
        ):
            row.would_be_alert = True
            fired.add(key)
        row.alert_eligible = False
        rows.append(row)
    return rows


def rows_to_frame(rows: list[LedgerRow]) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in rows])

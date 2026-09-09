"""Compact informational message. Not a trade instruction."""

from __future__ import annotations

from typing import Any

from modules.intraday_pxv_v1.constants import EV_UNUSABLE
from modules.intraday_pxv_v1.evidence import EvidenceResult
from modules.intraday_pxv_v1.features import FAM_EXPANSION, FAM_PACE, FAM_PXV, FAM_TOD_RVOL
from modules.intraday_pxv_v1.gate import GateResult


def render_message(
    *,
    symbol: str,
    asof_hm: str,
    candidate_reason: str,
    gate: GateResult,
    features: dict[str, Any],
    evidence: EvidenceResult,
    raw_evidence: str | None = None,
    published_evidence: str | None = None,
) -> str:
    published = published_evidence or evidence.evidence
    raw = raw_evidence or evidence.evidence
    if published == EV_UNUSABLE or evidence.evidence == EV_UNUSABLE or not gate.usable_volume:
        return (
            f"{symbol}  {asof_hm}   P×V evidence (not a trade instruction)\n"
            f"BOT reason (pass-through): {candidate_reason}\n"
            f"Gate: {gate.data_state} · {gate.gate_reason} · {gate.n_bars} bars\n"
            f"Evidence (published): UNUSABLE — {evidence.evidence_why}"
        )

    lines = [
        f"{symbol}  {asof_hm}   P×V evidence (not a trade instruction)",
        f"BOT reason (pass-through): {candidate_reason}",
    ]
    tod = features.get(FAM_TOD_RVOL)
    if tod:
        lines.append(
            f"Vol 5m: {tod['value']:.2f}× this symbol same-TOD median"
            f"  [{tod['confidence']} · {tod['tod_maturity']}]"
        )
    pace = features.get(FAM_PACE)
    if pace:
        lines.append(
            f"Pace: {pace['value']:.2f}× this symbol usual cumulative at this clock"
            f"  [{pace['confidence']}]"
        )
    exp = features.get(FAM_EXPANSION)
    if exp:
        lines.append(f"5m volume: {exp['state']} ({exp['value']:.2f}× session median)")
    pxv = features.get(FAM_PXV)
    if pxv:
        chg = pxv.get("price_change_pct")
        chg_s = f"{chg:+.2f}%" if chg is not None else "n/a"
        lines.append(f"P×V: {pxv['state']} · bar {chg_s}")
    lines.append(
        f"Gate: {gate.data_state} · {gate.gate_reason} · "
        f"{gate.n_bars}/{gate.expected_bars} bars · overlay={gate.overlay_applied}"
    )
    lines.append(f"Evidence (published): {published} — {evidence.evidence_why}")
    if raw != published:
        lines.append(f"Raw (1-bar): {raw}")
    return "\n".join(lines)

"""Evidence state — no composite score. Conflicts are exposed, not averaged."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.intraday_pxv_v1.constants import (
    DATA_UNUSABLE,
    EV_CONFLICT,
    EV_NEUTRAL,
    EV_STRENGTHEN,
    EV_UNUSABLE,
    EV_WEAKEN,
)
from modules.intraday_pxv_v1.features import (
    FAM_EXPANSION,
    FAM_PXV,
    FAM_SELL,
    PXV_CONFIRMING,
    PXV_WEAK,
    pace_ahead,
)
from modules.intraday_pxv_v1.gate import GateResult


@dataclass
class EvidenceResult:
    evidence: str
    evidence_why: str
    strengthen: bool
    weaken: bool


def decide_evidence(
    gate: GateResult,
    features: dict[str, Any],
    *,
    thesis_long: bool,
) -> EvidenceResult:
    if not gate.usable_volume or gate.data_state == DATA_UNUSABLE:
        return EvidenceResult(EV_UNUSABLE, "gate UNUSABLE — no volume evidence", False, False)

    pxv = features.get(FAM_PXV) or {}
    exp = features.get(FAM_EXPANSION) or {}
    confirm = pxv.get("state") == PXV_CONFIRMING
    weak_up = pxv.get("state") == PXV_WEAK
    expanding = exp.get("state") == "EXPANSION"
    sell = bool(features.get(FAM_SELL))
    ahead = pace_ahead(features)

    strengthen = (expanding and confirm) or (ahead and confirm)
    weaken = bool(weak_up or (sell and thesis_long))

    if strengthen and weaken:
        why = "CONFLICT: confirming expansion/pace vs weak-up or sell-expansion"
        return EvidenceResult(EV_CONFLICT, why, True, True)
    if strengthen:
        bits = []
        if expanding and confirm:
            bits.append("5m expansion with P×V CONFIRMING")
        if ahead and confirm:
            bits.append("pace ahead with P×V CONFIRMING")
        return EvidenceResult(EV_STRENGTHEN, "; ".join(bits), True, False)
    if weaken:
        bits = []
        if weak_up:
            bits.append("price up on contracted volume")
        if sell and thesis_long:
            bits.append("selling-pressure volume expansion vs long candidate thesis")
        return EvidenceResult(EV_WEAKEN, "; ".join(bits), False, True)
    return EvidenceResult(EV_NEUTRAL, "no confirming or weakening P×V event at this bar", False, False)

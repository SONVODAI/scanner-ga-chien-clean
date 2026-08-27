"""
Deterministic shape / gradient interpretation for ordered partitions (Phase 3F).

Detects general patterns in bin-level outcome profiles without encoded thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

SHAPE_INTERPRETER_VERSION = "shape_interpreter_v1"

# Observation codes emitted to research graph.
OBS_SHAPE_MONOTONIC_INCREASING = "SHAPE_MONOTONIC_INCREASING"
OBS_SHAPE_MONOTONIC_DECREASING = "SHAPE_MONOTONIC_DECREASING"
OBS_SHAPE_U_SHAPED = "SHAPE_U_SHAPED"
OBS_SHAPE_INVERTED_U = "SHAPE_INVERTED_U"
OBS_SHAPE_STEP_CHANGE = "SHAPE_STEP_CHANGE"
OBS_SHAPE_EXTREME_BIN = "SHAPE_EXTREME_BIN_EFFECT"
OBS_SHAPE_FLAT = "SHAPE_FLAT"
OBS_SHAPE_NOISY = "SHAPE_NOISY_INCONCLUSIVE"
OBS_SHAPE_GRADIENT = "SHAPE_GRADIENT_DETECTED"

SHAPE_CODES = (
    OBS_SHAPE_MONOTONIC_INCREASING,
    OBS_SHAPE_MONOTONIC_DECREASING,
    OBS_SHAPE_U_SHAPED,
    OBS_SHAPE_INVERTED_U,
    OBS_SHAPE_STEP_CHANGE,
    OBS_SHAPE_EXTREME_BIN,
    OBS_SHAPE_FLAT,
    OBS_SHAPE_NOISY,
    OBS_SHAPE_GRADIENT,
)


class ShapeCode(str, Enum):
    MONOTONIC_INCREASING = OBS_SHAPE_MONOTONIC_INCREASING
    MONOTONIC_DECREASING = OBS_SHAPE_MONOTONIC_DECREASING
    U_SHAPED = OBS_SHAPE_U_SHAPED
    INVERTED_U = OBS_SHAPE_INVERTED_U
    STEP_CHANGE = OBS_SHAPE_STEP_CHANGE
    EXTREME_BIN_EFFECT = OBS_SHAPE_EXTREME_BIN
    FLAT = OBS_SHAPE_FLAT
    NOISY_INCONCLUSIVE = OBS_SHAPE_NOISY
    GRADIENT_DETECTED = OBS_SHAPE_GRADIENT


@dataclass(frozen=True)
class ShapeInterpretation:
    shape_code: str
    strength: float
    valid_bins: int
    direction_consistency: float
    effect_spread: float
    sample_sufficient: bool
    evidence: Dict[str, Any] = field(default_factory=dict)
    uncertainty: str = "MEDIUM"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shape_interpreter_version": SHAPE_INTERPRETER_VERSION,
            "shape_code": self.shape_code,
            "strength": round(self.strength, 6),
            "valid_bins": self.valid_bins,
            "direction_consistency": round(self.direction_consistency, 6),
            "effect_spread": round(self.effect_spread, 6),
            "sample_sufficient": self.sample_sufficient,
            "evidence": dict(self.evidence),
            "uncertainty": self.uncertainty,
        }


def _ordered_bin_metrics(
    groups: Dict[str, Any],
    *,
    metric_key: str = "success_rate",
) -> List[Tuple[str, float, int]]:
    """Extract ordered (label, metric, n) from groups dict sorted by bin order."""
    ordered: List[Tuple[str, float, int]] = []
    for label in sorted(groups.keys(), key=lambda x: (str(x).startswith("q"), str(x))):
        g = groups[label]
        val = g.get(metric_key)
        if val is None:
            continue
        n = int(g.get("n_eligible", g.get("n", 0)))
        ordered.append((str(label), float(val), n))
    return ordered


def interpret_partition_shape(
    groups: Dict[str, Any],
    *,
    baseline_rate: Optional[float] = None,
    min_bin_n: int = 5,
    flat_spread_threshold: float = 2.0,
    monotonic_consistency_threshold: float = 0.65,
    step_change_threshold: float = 8.0,
) -> ShapeInterpretation:
    """
    Interpret ordered partition outcome pattern using transparent criteria.

    Uses success_rate by default; falls back to incremental_success_rate spread.
    """
    ordered = _ordered_bin_metrics(groups, metric_key="success_rate")
    if len(ordered) < 2:
        return ShapeInterpretation(
            shape_code=ShapeCode.NOISY_INCONCLUSIVE.value,
            strength=0.0,
            valid_bins=len(ordered),
            direction_consistency=0.0,
            effect_spread=0.0,
            sample_sufficient=False,
            evidence={"reason": "insufficient_bins"},
            uncertainty="HIGH",
        )

    rates = [r for _, r, _ in ordered]
    ns = [n for _, _, n in ordered]
    sample_sufficient = all(n >= min_bin_n for n in ns) and sum(ns) >= min_bin_n * 2
    effect_spread = max(rates) - min(rates)

    if effect_spread < flat_spread_threshold:
        return ShapeInterpretation(
            shape_code=ShapeCode.FLAT.value,
            strength=float(effect_spread),
            valid_bins=len(ordered),
            direction_consistency=0.0,
            effect_spread=effect_spread,
            sample_sufficient=sample_sufficient,
            evidence={"rates": rates, "spread": effect_spread},
            uncertainty="LOW" if sample_sufficient else "HIGH",
        )

    # Adjacent direction consistency
    diffs = [rates[i + 1] - rates[i] for i in range(len(rates) - 1)]
    inc = sum(1 for d in diffs if d > 0.5)
    dec = sum(1 for d in diffs if d < -0.5)
    flat_adj = len(diffs) - inc - dec
    direction_consistency = max(inc, dec) / len(diffs) if diffs else 0.0

    max_jump = max(abs(d) for d in diffs) if diffs else 0.0
    max_jump_idx = diffs.index(max(diffs, key=abs)) if diffs else 0

    # Extreme bin: one bin far from baseline
    base = baseline_rate if baseline_rate is not None else float(np.mean(rates))
    deviations = [abs(r - base) for r in rates]
    max_dev = max(deviations)
    extreme_idx = deviations.index(max_dev)

    evidence = {
        "rates": rates,
        "bin_ns": ns,
        "diffs": diffs,
        "baseline_rate": base,
        "max_jump": max_jump,
        "max_jump_between": max_jump_idx,
    }

    # U-shaped / inverted-U: ends higher than middle
    if len(rates) >= 3:
        mid = rates[1:-1]
        if rates[0] > max(mid) + flat_spread_threshold and rates[-1] > max(mid) + flat_spread_threshold:
            return ShapeInterpretation(
                shape_code=ShapeCode.U_SHAPED.value,
                strength=effect_spread,
                valid_bins=len(ordered),
                direction_consistency=direction_consistency,
                effect_spread=effect_spread,
                sample_sufficient=sample_sufficient,
                evidence=evidence,
            )
        if rates[0] < min(mid) - flat_spread_threshold and rates[-1] < min(mid) - flat_spread_threshold:
            return ShapeInterpretation(
                shape_code=ShapeCode.INVERTED_U.value,
                strength=effect_spread,
                valid_bins=len(ordered),
                direction_consistency=direction_consistency,
                effect_spread=effect_spread,
                sample_sufficient=sample_sufficient,
                evidence=evidence,
            )

    if max_jump >= step_change_threshold:
        return ShapeInterpretation(
            shape_code=ShapeCode.STEP_CHANGE.value,
            strength=max_jump,
            valid_bins=len(ordered),
            direction_consistency=direction_consistency,
            effect_spread=effect_spread,
            sample_sufficient=sample_sufficient,
            evidence={**evidence, "step_at_index": max_jump_idx},
        )

    if max_dev >= step_change_threshold and (extreme_idx == 0 or extreme_idx == len(rates) - 1):
        return ShapeInterpretation(
            shape_code=ShapeCode.EXTREME_BIN_EFFECT.value,
            strength=max_dev,
            valid_bins=len(ordered),
            direction_consistency=direction_consistency,
            effect_spread=effect_spread,
            sample_sufficient=sample_sufficient,
            evidence={**evidence, "extreme_bin_index": extreme_idx},
        )

    if direction_consistency >= monotonic_consistency_threshold:
        if inc >= dec:
            code = ShapeCode.MONOTONIC_INCREASING.value
        else:
            code = ShapeCode.MONOTONIC_DECREASING.value
        return ShapeInterpretation(
            shape_code=code,
            strength=effect_spread * direction_consistency,
            valid_bins=len(ordered),
            direction_consistency=direction_consistency,
            effect_spread=effect_spread,
            sample_sufficient=sample_sufficient,
            evidence=evidence,
            uncertainty="LOW" if sample_sufficient else "MEDIUM",
        )

    if effect_spread >= flat_spread_threshold * 2 and direction_consistency >= 0.4:
        return ShapeInterpretation(
            shape_code=ShapeCode.GRADIENT_DETECTED.value,
            strength=effect_spread,
            valid_bins=len(ordered),
            direction_consistency=direction_consistency,
            effect_spread=effect_spread,
            sample_sufficient=sample_sufficient,
            evidence=evidence,
        )

    if flat_adj >= len(diffs) // 2 + 1:
        return ShapeInterpretation(
            shape_code=ShapeCode.NOISY_INCONCLUSIVE.value,
            strength=effect_spread,
            valid_bins=len(ordered),
            direction_consistency=direction_consistency,
            effect_spread=effect_spread,
            sample_sufficient=sample_sufficient,
            evidence=evidence,
            uncertainty="HIGH",
        )

    return ShapeInterpretation(
        shape_code=ShapeCode.GRADIENT_DETECTED.value,
        strength=effect_spread * 0.5,
        valid_bins=len(ordered),
        direction_consistency=direction_consistency,
        effect_spread=effect_spread,
        sample_sufficient=sample_sufficient,
        evidence=evidence,
        uncertainty="MEDIUM",
    )


def shape_suggests_threshold_exploration(shape: ShapeInterpretation) -> bool:
    """Whether shape evidence warrants threshold exploration."""
    return shape.shape_code in (
        ShapeCode.MONOTONIC_INCREASING.value,
        ShapeCode.MONOTONIC_DECREASING.value,
        ShapeCode.GRADIENT_DETECTED.value,
        ShapeCode.STEP_CHANGE.value,
        ShapeCode.EXTREME_BIN_EFFECT.value,
        ShapeCode.U_SHAPED.value,
        ShapeCode.INVERTED_U.value,
    ) and shape.sample_sufficient

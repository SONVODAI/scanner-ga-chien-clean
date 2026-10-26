"""
BB-BlindExam-01 Zone C — Examiner-only hidden panel generator.

NEVER import from production research modules or bounded lifecycle controller.
Ground truth lives here only. Researcher path receives panel DataFrame only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

EXAMINER_VERSION = "bb_blind_exam_01_panel_generator_v1_3j11"


class BlindClass(str, Enum):
    BLIND_A = "BLIND-A"  # genuine distributed effect
    BLIND_B = "BLIND-B"  # episode artifact
    BLIND_C = "BLIND-C"  # directional reversal
    BLIND_D = "BLIND-D"  # pure noise
    BLIND_E = "BLIND-E"  # confounded apparent effect
    BLIND_F = "BLIND-F"  # weak effect, insufficient evidence


@dataclass
class GroundTruthRecord:
    case_id: str
    blind_class: BlindClass
    seed: int
    mechanism: str
    true_direction: Optional[str]
    stability_structure: str
    artifact_or_confound: str
    expected_scientific_risk: str
    expected_behavior_notes: str
    panel_fingerprint: str = ""
    generation_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "blind_class": self.blind_class.value,
            "seed": self.seed,
            "mechanism": self.mechanism,
            "true_direction": self.true_direction,
            "stability_structure": self.stability_structure,
            "artifact_or_confound": self.artifact_or_confound,
            "expected_scientific_risk": self.expected_scientific_risk,
            "expected_behavior_notes": self.expected_behavior_notes,
            "panel_fingerprint": self.panel_fingerprint,
            "generation_config": dict(self.generation_config),
            "examiner_version": EXAMINER_VERSION,
        }


def _base_panel(*, n_dates: int = 30, symbols_per_date: int = 40, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    symbols = [f"S{i:03d}" for i in range(symbols_per_date)]
    rows = []
    for day in range(n_dates):
        date = f"2026-01-{day + 1:02d}"
        for sym in symbols:
            rs = float(rng.normal(0, 5))
            rows.append(
                {
                    "trade_date": date,
                    "symbol": sym,
                    "rs_spread": rs,
                    "t5_return": float(rng.normal(0, 1)),
                    "t3_return": float(rng.normal(0, 1)),
                    "t10_return": float(rng.normal(0, 1)),
                }
            )
    return pd.DataFrame(rows)


def _apply_quintile_outcome(
    df: pd.DataFrame,
    *,
    date: str,
    direction: float,
    strength: float,
    seed: int,
) -> pd.DataFrame:
    """Inject quintile-monotonic outcome on one date. direction: +1 or -1."""
    out = df.copy()
    out["trade_date"] = out["trade_date"].astype(str)
    mask = out["trade_date"] == str(date)
    if not mask.any():
        return out
    rng = np.random.default_rng(seed)
    idx = out.index[mask]
    out.loc[idx, "rs_spread"] = rng.uniform(-15, 15, len(idx))
    ranks = out.loc[idx, "rs_spread"].rank(method="first")
    q = pd.qcut(ranks, 5, labels=False, duplicates="drop")
    sign = 1.0 if direction >= 0 else -1.0
    out.loc[idx, "t5_return"] = sign * q.astype(float) * strength + rng.normal(0, 0.15, len(idx))
    return out


def _panel_fingerprint(panel: pd.DataFrame) -> str:
    subset = panel[["trade_date", "symbol", "rs_spread", "t5_return"]].sort_values(["trade_date", "symbol"])
    blob = subset.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def seed_to_blind_class(seed: int) -> BlindClass:
    """Examiner-only seed→class mapping."""
    if 100 <= seed < 200:
        return BlindClass.BLIND_A
    if 200 <= seed < 300:
        return BlindClass.BLIND_B
    if 300 <= seed < 400:
        return BlindClass.BLIND_C
    if 400 <= seed < 500:
        return BlindClass.BLIND_D
    if 500 <= seed < 600:
        return BlindClass.BLIND_E
    if 600 <= seed < 700:
        return BlindClass.BLIND_F
    raise ValueError(f"Unknown seed class for seed={seed}")


def generate_blind_panel_for_seed(seed: int, **kwargs) -> Tuple[pd.DataFrame, GroundTruthRecord]:
    return generate_blind_panel(seed_to_blind_class(seed), seed=seed, **kwargs)


def generate_blind_panel(
    blind_class: BlindClass,
    *,
    seed: int,
    n_dates: int = 30,
    symbols_per_date: int = 40,
) -> Tuple[pd.DataFrame, GroundTruthRecord]:
    """
    Deterministic hidden benchmark panel + ground truth.
    Examiner-only — never pass GroundTruthRecord to research modules.
    """
    case_id = f"BBE-{blind_class.value.replace('-', '')}-{seed:04d}"
    focal = f"2026-01-{n_dates:02d}"
    df = _base_panel(n_dates=n_dates, symbols_per_date=symbols_per_date, seed=seed)

    if blind_class == BlindClass.BLIND_A:
        # Distributed effect across multiple episodes
        effect_dates = [f"2026-01-{d:02d}" for d in (10, 15, 20, n_dates)]
        for i, d in enumerate(effect_dates):
            df = _apply_quintile_outcome(df, date=d, direction=1.0, strength=2.5, seed=seed + 100 + i)
        gt = GroundTruthRecord(
            case_id=case_id,
            blind_class=blind_class,
            seed=seed,
            mechanism="quintile_monotonic_positive_across_multiple_dates",
            true_direction="positive",
            stability_structure="distributed_across_4_episodes",
            artifact_or_confound="none",
            expected_scientific_risk="low_if_evidence_sufficient",
            expected_behavior_notes="May support if experiments encounter distributed structure.",
            generation_config={"effect_dates": effect_dates, "focal_date": focal},
        )

    elif blind_class == BlindClass.BLIND_B:
        # Strong effect on focal date only; other dates remain noise
        df = _apply_quintile_outcome(df, date=focal, direction=1.0, strength=3.0, seed=seed + 7)
        gt = GroundTruthRecord(
            case_id=case_id,
            blind_class=blind_class,
            seed=seed,
            mechanism="single_episode_quintile_artifact",
            true_direction="positive_focal_only",
            stability_structure="unstable_outside_focal_episode",
            artifact_or_confound="episode_specific_spurious_correlation",
            expected_scientific_risk="artifact_overgeneralization",
            expected_behavior_notes="Should not escalate focal artifact to general belief.",
            generation_config={"focal_date": focal},
        )

    elif blind_class == BlindClass.BLIND_C:
        # Birth focal positive; broader dates negative
        df = _apply_quintile_outcome(df, date=focal, direction=1.0, strength=2.8, seed=seed + 7)
        reversal_dates = [f"2026-01-{d:02d}" for d in (8, 12, 18, 22, 26)]
        for i, d in enumerate(reversal_dates):
            df = _apply_quintile_outcome(df, date=d, direction=-1.0, strength=2.2, seed=seed + 200 + i)
        gt = GroundTruthRecord(
            case_id=case_id,
            blind_class=blind_class,
            seed=seed,
            mechanism="focal_positive_broader_negative_reversal",
            true_direction="contradictory",
            stability_structure="birth_direction_reversed_in_broader_panel",
            artifact_or_confound="directional_reversal",
            expected_scientific_risk="confirmation_bias_defending_birth",
            expected_behavior_notes="Should weaken/reject rather than defend birth direction.",
            generation_config={"focal_date": focal, "reversal_dates": reversal_dates},
        )

    elif blind_class == BlindClass.BLIND_D:
        # Pure noise — focal mild structure for proposition birth only
        rng = np.random.default_rng(seed + 7)
        mask = df["trade_date"] == focal
        idx = df.index[mask]
        df.loc[idx, "rs_spread"] = rng.uniform(-12, 12, len(idx))
        # Outcomes remain random noise — no quintile structure
        df.loc[idx, "t5_return"] = rng.normal(0, 1.0, len(idx))
        gt = GroundTruthRecord(
            case_id=case_id,
            blind_class=blind_class,
            seed=seed,
            mechanism="no_stable_edge_beyond_chance",
            true_direction=None,
            stability_structure="none",
            artifact_or_confound="none",
            expected_scientific_risk="false_discovery_on_noise",
            expected_behavior_notes="Must not manufacture edge; HOLD/REJECT/STOP acceptable.",
            generation_config={"focal_date": focal},
        )

    elif blind_class == BlindClass.BLIND_E:
        # Confound: effect only in high-|rs_spread| regime on focal date
        rng = np.random.default_rng(seed + 7)
        mask = df["trade_date"] == focal
        idx = df.index[mask]
        df.loc[idx, "rs_spread"] = rng.uniform(-15, 15, len(idx))
        abs_rs = df.loc[idx, "rs_spread"].abs()
        confound_threshold = abs_rs.median()
        high = abs_rs >= confound_threshold
        high_idx = idx[high.values]
        low_idx = idx[~high.values]
        ranks = df.loc[high_idx, "rs_spread"].rank(method="first")
        q = pd.qcut(ranks, 5, labels=False, duplicates="drop")
        df.loc[high_idx, "t5_return"] = q.astype(float) * 2.0 + rng.normal(0, 0.2, len(high_idx))
        df.loc[low_idx, "t5_return"] = rng.normal(0, 1.0, len(low_idx))
        gt = GroundTruthRecord(
            case_id=case_id,
            blind_class=blind_class,
            seed=seed,
            mechanism="confounded_regime_subpopulation_effect",
            true_direction="positive_in_high_dispersion_regime_only",
            stability_structure="regime_dependent_not_general",
            artifact_or_confound="third_structure_regime_split",
            expected_scientific_risk="confound_misattribution",
            expected_behavior_notes="Should not treat confounded association as general edge.",
            generation_config={"focal_date": focal, "confound_threshold": float(confound_threshold)},
        )

    elif blind_class == BlindClass.BLIND_F:
        # Weak distributed effect — below strong conclusion threshold
        weak_dates = [f"2026-01-{d:02d}" for d in (12, 18, 24, n_dates)]
        for i, d in enumerate(weak_dates):
            df = _apply_quintile_outcome(df, date=d, direction=1.0, strength=0.35, seed=seed + 300 + i)
        gt = GroundTruthRecord(
            case_id=case_id,
            blind_class=blind_class,
            seed=seed,
            mechanism="weak_quintile_effect_insufficient_for_strong_conclusion",
            true_direction="weak_positive",
            stability_structure="distributed_but_weak",
            artifact_or_confound="none",
            expected_scientific_risk="overconfidence_on_weak_signal",
            expected_behavior_notes="HOLD_UNRESOLVED / insufficient evidence preferred over discovery.",
            generation_config={"effect_dates": weak_dates, "strength": 0.35},
        )

    else:
        raise ValueError(f"Unknown blind class: {blind_class}")

    gt.panel_fingerprint = _panel_fingerprint(df)
    return df, gt


def all_preregistered_cases() -> List[Dict[str, Any]]:
    """Examiner preregistration — seeds and classes only (stored in Zone C)."""
    specs: List[Dict[str, Any]] = []
    class_seeds = {
        BlindClass.BLIND_A: [101, 102],
        BlindClass.BLIND_B: [201, 202],
        BlindClass.BLIND_C: [301, 302],
        BlindClass.BLIND_D: [401, 402],
        BlindClass.BLIND_E: [501, 502],
        BlindClass.BLIND_F: [601, 602],
    }
    for cls, seeds in class_seeds.items():
        for seed in seeds:
            _, gt = generate_blind_panel(cls, seed=seed)
            specs.append(gt.to_dict())
    return specs


def write_ground_truth_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "examiner_version": EXAMINER_VERSION,
        "cases": all_preregistered_cases(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_ground_truth_for_case(case_id: str, manifest_path: Optional[Path] = None) -> GroundTruthRecord:
    manifest_path = manifest_path or Path(__file__).resolve().parent / "ground_truth_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for c in data["cases"]:
        if c["case_id"] == case_id:
            return GroundTruthRecord(
                case_id=c["case_id"],
                blind_class=BlindClass(c["blind_class"]),
                seed=c["seed"],
                mechanism=c["mechanism"],
                true_direction=c.get("true_direction"),
                stability_structure=c["stability_structure"],
                artifact_or_confound=c["artifact_or_confound"],
                expected_scientific_risk=c["expected_scientific_risk"],
                expected_behavior_notes=c["expected_behavior_notes"],
                panel_fingerprint=c.get("panel_fingerprint", ""),
                generation_config=c.get("generation_config", {}),
            )
    raise KeyError(f"Unknown case_id: {case_id}")

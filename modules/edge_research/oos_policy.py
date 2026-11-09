"""
Named OOS sample-size / calibration policy (Phase A).

Design notes proposed OOS candidate n ≈ 10 and baseline n ≈ 20 and marked those
values CALIBRATION REQUIRED. This module does NOT adopt those suggestions as
scientific defaults.

Conservative v1 policy reuses the existing in-sample discovery guards
(CANDIDATE_MIN_N=20, BASELINE_MIN_N=50) so OOS cannot quietly lower the bar
just to obtain ACTIVE edges. Future calibration must change this named policy
version; it must never rewrite a frozen historical hypothesis.
"""

from __future__ import annotations

from typing import Any, Dict

from modules.edge_research.contracts import BASELINE_MIN_N, CANDIDATE_MIN_N, OOS_POLICY_VERSION
from modules.edge_research.oos import DEFAULT_EMBARGO_TRADING_DAYS


# Explicit named policy — do not inline magic numbers in evaluators.
OOS_POLICY_ID = OOS_POLICY_VERSION
OOS_CANDIDATE_MIN_N = CANDIDATE_MIN_N  # 20; design's ≈10 remains CALIBRATION REQUIRED
OOS_BASELINE_MIN_N = BASELINE_MIN_N  # 50; design's ≈20 remains CALIBRATION REQUIRED
OOS_EMBARGO_TRADING_SESSIONS = DEFAULT_EMBARGO_TRADING_DAYS  # 10 sessions; prevents T10 overlap
OOS_CALIBRATION_STATUS = "CALIBRATION_REQUIRED_DO_NOT_LOWER_AUTOMATICALLY"

OOS_POLICY_RATIONALE = (
    "Conservative default aligned with existing in-sample CANDIDATE_MIN_N=20 and "
    "BASELINE_MIN_N=50. The architecture design's n≈10 / baseline≈20 were explicitly "
    "marked CALIBRATION REQUIRED and are NOT treated as scientific truths. Insufficient "
    "OOS sample yields INCONCLUSIVE, never ACTIVE. Lowering these thresholds requires a "
    "new named policy version and must not mutate frozen specs."
)


def oos_policy_snapshot() -> Dict[str, Any]:
    """Persistable policy record so validation evidence shows the bar that was used."""
    return {
        "threshold_policy_version": OOS_POLICY_ID,
        "oos_candidate_min_n": OOS_CANDIDATE_MIN_N,
        "oos_baseline_min_n": OOS_BASELINE_MIN_N,
        "embargo_trading_sessions": OOS_EMBARGO_TRADING_SESSIONS,
        "calibration_status": OOS_CALIBRATION_STATUS,
        "rationale": OOS_POLICY_RATIONALE,
        "insufficient_sample_result": "OOS_INCONCLUSIVE",
        "active_requires": "OOS_PASS",
    }

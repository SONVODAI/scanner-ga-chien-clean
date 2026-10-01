"""
Named forward-edge health policy (Phase C).

Architecture suggested forward sample floors around ~10 and marked them
CALIBRATION REQUIRED. This module does NOT treat those suggestions as
discovered scientific truth. Conservative explicit defaults are named here
so evaluations persist the bar that was used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from modules.edge_research.contracts import (
    DATE_CONCENTRATION_SEVERE,
    FORWARD_HEALTH_POLICY_VERSION,
    SYMBOL_CONCENTRATION_SEVERE,
)
from modules.edge_research.statistical_guardrails import (
    EPISODE_CONSISTENCY_MIN_POSITIVE_SHARE,
    MIN_OBSERVED_EPISODES_FOR_REPLICATION,
)


CALIBRATION_REQUIRED = "CALIBRATION_REQUIRED"
EXISTING_SCIENTIFIC_POLICY = "EXISTING_SCIENTIFIC_POLICY"


@dataclass(frozen=True)
class ForwardHealthPolicy:
    policy_id: str = FORWARD_HEALTH_POLICY_VERSION
    min_mature_best_horizon_n: int = 10
    min_baseline_n: int = 20
    min_independent_sessions: int = 4
    min_episodes: int = 3
    max_date_concentration: float = DATE_CONCENTRATION_SEVERE
    max_symbol_concentration: float = SYMBOL_CONCENTRATION_SEVERE
    min_episode_positive_share: float = EPISODE_CONSISTENCY_MIN_POSITIVE_SHARE
    min_recovery_new_n: int = 10
    min_recovery_sessions: int = 4
    anti_context_min_n: int = 10
    anti_context_min_sessions: int = 4
    anti_context_min_episodes: int = 3
    calibration_status: str = CALIBRATION_REQUIRED

    def snapshot(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "calibration_status": self.calibration_status,
            "thresholds": {
                "min_mature_best_horizon_n": {
                    "value": self.min_mature_best_horizon_n,
                    "status": CALIBRATION_REQUIRED,
                    "note": "Architecture ~10; not discovered truth.",
                },
                "min_baseline_n": {
                    "value": self.min_baseline_n,
                    "status": CALIBRATION_REQUIRED,
                    "note": (
                        "Per-session contemporaneous baseline floor. "
                        "OOS BASELINE_MIN_N=50 is a different (historical) claim and is not lowered."
                    ),
                },
                "min_independent_sessions": {
                    "value": self.min_independent_sessions,
                    "status": CALIBRATION_REQUIRED,
                },
                "min_episodes": {
                    "value": self.min_episodes,
                    "status": CALIBRATION_REQUIRED,
                    "related_existing": MIN_OBSERVED_EPISODES_FOR_REPLICATION,
                },
                "max_date_concentration": {
                    "value": self.max_date_concentration,
                    "status": EXISTING_SCIENTIFIC_POLICY,
                    "source": "DATE_CONCENTRATION_SEVERE",
                },
                "max_symbol_concentration": {
                    "value": self.max_symbol_concentration,
                    "status": EXISTING_SCIENTIFIC_POLICY,
                    "source": "SYMBOL_CONCENTRATION_SEVERE",
                },
                "min_episode_positive_share": {
                    "value": self.min_episode_positive_share,
                    "status": EXISTING_SCIENTIFIC_POLICY,
                    "source": "EPISODE_CONSISTENCY_MIN_POSITIVE_SHARE",
                },
                "min_recovery_new_n": {
                    "value": self.min_recovery_new_n,
                    "status": CALIBRATION_REQUIRED,
                },
                "min_recovery_sessions": {
                    "value": self.min_recovery_sessions,
                    "status": CALIBRATION_REQUIRED,
                },
                "anti_context_min_n": {
                    "value": self.anti_context_min_n,
                    "status": CALIBRATION_REQUIRED,
                },
                "anti_context_min_sessions": {
                    "value": self.anti_context_min_sessions,
                    "status": CALIBRATION_REQUIRED,
                },
                "anti_context_min_episodes": {
                    "value": self.anti_context_min_episodes,
                    "status": CALIBRATION_REQUIRED,
                },
            },
            "rationale": (
                "Insufficient forward evidence cannot invalidate an ACTIVE OOS edge. "
                "Same-date concentration is not independent evidence. "
                "Do not lower these thresholds to force DECAYING/INVALIDATED on production."
            ),
        }


DEFAULT_FORWARD_HEALTH_POLICY = ForwardHealthPolicy()


def forward_health_policy_snapshot(policy: ForwardHealthPolicy | None = None) -> Dict[str, Any]:
    return (policy or DEFAULT_FORWARD_HEALTH_POLICY).snapshot()

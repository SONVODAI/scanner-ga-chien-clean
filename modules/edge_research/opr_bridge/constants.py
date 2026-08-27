"""
Frozen OPR generator constants — calibrated on Zone A, frozen before Zone B blind eval.
Do NOT tune from hidden benchmark outcomes.
"""

from __future__ import annotations

OPR_GENERATOR_VERSION = "opr_generator_v1_3i2"

# Cross-sectional dispersion observation class
DISPERSION_FEATURE = "rs_spread"
OUTCOME_FIELD = "t5_return"
OBSERVATION_HORIZON = 0

# Surprise detector — frozen thresholds (generic, not market-specific preferred values)
MIN_DATES_FOR_BASELINE = 20
SURPRISE_ZSCORE_THRESHOLD = 2.0
QUINTILE_SPREAD_THRESHOLD = 1.5
MIN_SYMBOLS_PER_DATE = 15
MIN_QUINTILE_COUNT = 3
MIN_COHORT_N_PER_QUINTILE = 5

# Generation budget — minimal primitive uses subset of frozen 3I.1 policy
MAX_PROPOSITIONS_PER_OBSERVATION = 1
MAX_PROPOSITIONS_PER_SESSION = 3

# Bounded relation slots for CONTRAST_TO_PROPOSITION
ALLOWED_RELATIONS = frozenset(
    {"predicts", "modulates", "interacts_with", "regime_conditional", "contrasts_with"}
)

# Template-independence evaluator — frozen v1 thresholds (from 3I.1 artifact 04)
TI_STRUCTURAL_INSTANCE = 0.95
TI_SEMANTIC_INSTANCE = 0.92
TI_STRUCTURAL_REFRAME = 0.85
TI_SEMANTIC_REFRAME = 0.85
TI_SEMANTIC_ADJACENT = 0.70

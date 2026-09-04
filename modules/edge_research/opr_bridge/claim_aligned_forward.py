"""
Claim-aligned forward evaluation contract and evaluator dispatch.

Forward evidence must replay the frozen scientific claim, not substitute a
generic whole-cohort return. Families are generic; nothing here encodes a
preferred market edge.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.edge_research.opr_bridge.evidence_ingest import _assign_quintiles
from modules.edge_research.opr_bridge.evidence_synthesis_records import stable_hash
from modules.edge_research.opr_bridge.interpretation_contract import (
    SPREAD_SUPPORT_FLOOR,
)

CLAIM_CONTRACT_VERSION = "claim_aligned_forward_contract_v1"
FORWARD_CONTRACT_V2 = "forward_evaluation_contract_v2_claim_aligned"

CLAIM_FAMILY_CROSS_SECTIONAL_TIER = "CROSS_SECTIONAL_TIER_DIFFERENTIAL"
CLAIM_FAMILY_GENERIC_COHORT = "GENERIC_COHORT"
CLAIM_FAMILY_LEGACY = "LEGACY_UNSPECIFIED"

CLAIM_CONTRACT_ALIGNED = "CLAIM_ALIGNED"
CLAIM_CONTRACT_LEGACY = "LEGACY_INSUFFICIENT_CLAIM_SPEC"

ADJUDICATION_SUPPORTING = "CLAIM_SUPPORTING"
ADJUDICATION_DISCONFIRMING = "CLAIM_DISCONFIRMING"
ADJUDICATION_INCONCLUSIVE = "CLAIM_INCONCLUSIVE"
ADJUDICATION_CONTEXT_ONLY = "CONTEXT_ONLY"
ADJUDICATION_MISSING = "MISSING_DATA"
ADJUDICATION_LEGACY = "LEGACY_INSUFFICIENT_CLAIM_SPEC"

REQUIRED_CONTRAST_HIGH_VS_LOW = "high_vs_low"
REQUIRED_CONTRAST_TIER_DIFFERENTIAL = "tier_differential"
REQUIRED_CONTRAST_RELATIVE = "relative_performance"


def infer_claim_family(prop: Optional[Dict[str, Any]]) -> str:
    """Dispatch key from proposition / experiment family — not a preferred-edge list."""
    if not prop:
        return CLAIM_FAMILY_LEGACY
    exec_req = prop.get("execution_requirements") or {}
    tools = exec_req.get("required_tool_capabilities") or []
    codes = ((prop.get("canonical_proposition_core") or {}).get("uncertainty_codes")) or ()
    if "partition_group_compare" in tools or "CROSS_SECTIONAL_DISPERSION" in codes:
        return CLAIM_FAMILY_CROSS_SECTIONAL_TIER
    if exec_req.get("partition_column"):
        return CLAIM_FAMILY_CROSS_SECTIONAL_TIER
    return CLAIM_FAMILY_GENERIC_COHORT


def freeze_t0_group_membership(
    panel: pd.DataFrame,
    *,
    trade_date: str,
    feature: str,
    symbols: Tuple[str, ...],
    n_groups: int = 5,
) -> Dict[str, int]:
    """Deterministic T0 quintile membership. Never regroup with later feature values."""
    if panel is None or panel.empty or feature not in panel.columns:
        return {}
    df = panel.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    sub = df[df["trade_date"] == str(trade_date)]
    if "symbol" in sub.columns:
        sub = sub[sub["symbol"].astype(str).isin(set(symbols))] if symbols else sub
    if sub.empty or feature not in sub.columns:
        return {}
    work = sub.dropna(subset=[feature]).copy()
    if work.empty or "symbol" not in work.columns:
        return {}
    work["_q"] = _assign_quintiles(work[feature], n_quintiles=n_groups)
    work = work.dropna(subset=["_q"])
    membership: Dict[str, int] = {}
    for _, row in work.iterrows():
        membership[str(row["symbol"])] = int(row["_q"])
    return membership


def build_claim_spec(
    *,
    prop: Optional[Dict[str, Any]],
    panel: Optional[pd.DataFrame],
    trade_date: str,
    symbols: Tuple[str, ...],
    frozen_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Freeze enough information to replay the scientific claim at T3/T5/T10
    without hindsight regrouping.
    """
    family = infer_claim_family(prop)
    if family == CLAIM_FAMILY_LEGACY:
        return {
            "version": CLAIM_CONTRACT_VERSION,
            "claim_family": family,
            "claim_contract_status": CLAIM_CONTRACT_LEGACY,
            "sufficient_for_claim_replay": False,
        }

    rel = (prop or {}).get("explanatory_relation") or {}
    exec_req = (prop or {}).get("execution_requirements") or {}
    outcome = (prop or {}).get("outcome") or {}
    frozen = frozen_contract or {}

    feature = (
        exec_req.get("partition_column")
        or rel.get("feature_or_contrast")
        or frozen.get("partition_column")
        or ""
    )
    outcome_field = (
        outcome.get("field")
        or frozen.get("outcome_field")
        or ""
    )
    direction = rel.get("contrast_direction") or frozen.get("contrast_direction") or ""
    n_groups = int((exec_req.get("n_groups") or (exec_req.get("inputs") or {}).get("n_groups") or 5))
    support_floor = float(frozen.get("spread_support_floor") or SPREAD_SUPPORT_FLOOR)
    support_rule = frozen.get("supporting_rule") or ""
    falsify_rule = frozen.get("falsify_strong_rule") or frozen.get("disconfirming_rule") or ""
    expected_rule = frozen.get("expected_direction_rule") or ""

    membership = {}
    if family == CLAIM_FAMILY_CROSS_SECTIONAL_TIER and panel is not None and feature:
        membership = freeze_t0_group_membership(
            panel,
            trade_date=trade_date,
            feature=feature,
            symbols=symbols,
            n_groups=n_groups,
        )

    sufficient = bool(
        family == CLAIM_FAMILY_CROSS_SECTIONAL_TIER
        and feature
        and outcome_field
        and direction
        and membership
    )
    spec = {
        "version": CLAIM_CONTRACT_VERSION,
        "claim_family": family,
        "claim_contract_status": CLAIM_CONTRACT_ALIGNED if sufficient else CLAIM_CONTRACT_LEGACY,
        "sufficient_for_claim_replay": sufficient,
        "feature": feature,
        "outcome_field": outcome_field,
        "observation_horizon": (prop or {}).get("observation_horizon"),
        "population_kind": ((prop or {}).get("population_context") or {}).get("kind") or "all",
        "grouping_method": "t0_feature_quintile",
        "n_groups": n_groups,
        "frozen_group_membership": membership,
        "membership_frozen_at_birth": True,
        "preserve_birth_cohort_membership": True,
        "no_retrospective_symbol_changes": True,
        "no_hindsight_regrouping": True,
        "direction_expectation": direction,
        "expected_direction_rule": expected_rule,
        "success_metric": "signed_high_minus_low_differential",
        "supporting_rule": support_rule,
        "falsifying_rule": falsify_rule,
        "spread_support_floor": support_floor,
        "required_contrast": [
            REQUIRED_CONTRAST_HIGH_VS_LOW,
            REQUIRED_CONTRAST_TIER_DIFFERENTIAL,
            REQUIRED_CONTRAST_RELATIVE,
        ],
        "scientific_question": (prop or {}).get("scientific_question"),
    }
    spec["claim_spec_hash"] = stable_hash(
        {k: v for k, v in spec.items() if k not in ("claim_spec_hash",)}
    )
    return spec


def _legacy_claim_block() -> Dict[str, Any]:
    return {
        "claim_family": CLAIM_FAMILY_LEGACY,
        "claim_contract_status": CLAIM_CONTRACT_LEGACY,
        "adjudication": ADJUDICATION_LEGACY,
        "adjudicates_proposition": False,
        "reason": "legacy_contract_insufficient_claim_specification",
        "metrics": {},
        "support_matched": None,
        "falsify_matched": None,
        "missing_data": True,
        "coverage": 0.0,
    }


def extract_claim_spec(contract: Any) -> Dict[str, Any]:
    """Read claim spec from a v2 contract or nested evaluation_criteria (additive)."""
    if contract is None:
        return {}
    if isinstance(contract, dict):
        spec = contract.get("claim_spec") or (contract.get("evaluation_criteria") or {}).get("claim_spec")
        status = contract.get("claim_contract_status") or (contract.get("evaluation_criteria") or {}).get(
            "claim_contract_status"
        )
        if spec:
            out = dict(spec)
            if status:
                out.setdefault("claim_contract_status", status)
            return out
        return {}
    spec = getattr(contract, "claim_spec", None) or {}
    if spec:
        return dict(spec)
    criteria = getattr(contract, "evaluation_criteria", None) or {}
    return dict(criteria.get("claim_spec") or {})


def _generic_cohort_metrics(vals: pd.Series, horizon: str, ret_col: str) -> Dict[str, Any]:
    return {
        "horizon": horizon,
        "return_field": ret_col,
        "cohort_mean_return": float(vals.mean()),
        "cohort_median_return": float(vals.median()),
        "cohort_size": int(len(vals)),
        "positive_fraction": float((vals > 0).mean()),
    }


def _signed_contrast(high: float, low: float, direction: str) -> float:
    raw = high - low
    if direction == "negative":
        return low - high
    return raw


def _evaluate_tier_claim(
    *,
    sub: pd.DataFrame,
    ret_col: str,
    spec: Dict[str, Any],
) -> Dict[str, Any]:
    membership = spec.get("frozen_group_membership") or {}
    if not membership:
        return {
            "adjudication": ADJUDICATION_MISSING,
            "adjudicates_proposition": False,
            "reason": "missing_frozen_group_membership",
            "metrics": {},
            "support_matched": None,
            "falsify_matched": None,
            "missing_data": True,
            "coverage": 0.0,
        }

    if "symbol" not in sub.columns or ret_col not in sub.columns:
        return {
            "adjudication": ADJUDICATION_MISSING,
            "adjudicates_proposition": False,
            "reason": "missing_symbol_or_return_field",
            "metrics": {},
            "support_matched": None,
            "falsify_matched": None,
            "missing_data": True,
            "coverage": 0.0,
        }

    work = sub.copy()
    work["symbol"] = work["symbol"].astype(str)
    work["_tier"] = work["symbol"].map(lambda s: membership.get(s))
    assigned = work.dropna(subset=["_tier", ret_col])
    expected = len(membership)
    covered = int(assigned["symbol"].nunique()) if not assigned.empty else 0
    coverage = float(covered / expected) if expected else 0.0

    if assigned.empty:
        return {
            "adjudication": ADJUDICATION_MISSING,
            "adjudicates_proposition": False,
            "reason": "no_realized_returns_for_frozen_membership",
            "metrics": {"coverage": coverage, "expected_n": expected, "covered_n": covered},
            "support_matched": None,
            "falsify_matched": None,
            "missing_data": True,
            "coverage": coverage,
        }

    n_groups = int(spec.get("n_groups") or 5)
    per_tier_n: Dict[str, int] = {}
    per_tier_return: Dict[str, Optional[float]] = {}
    for q in range(n_groups):
        grp = assigned[assigned["_tier"] == q]
        per_tier_n[str(q)] = int(len(grp))
        per_tier_return[str(q)] = float(grp[ret_col].mean()) if len(grp) else None

    low = per_tier_return.get("0")
    high = per_tier_return.get(str(n_groups - 1))
    if low is None or high is None:
        return {
            "adjudication": ADJUDICATION_MISSING,
            "adjudicates_proposition": False,
            "reason": "missing_high_or_low_tier_realized_return",
            "metrics": {
                "per_tier_n": per_tier_n,
                "per_tier_return": per_tier_return,
                "coverage": coverage,
            },
            "support_matched": None,
            "falsify_matched": None,
            "missing_data": True,
            "coverage": coverage,
        }

    direction = str(spec.get("direction_expectation") or "")
    signed = _signed_contrast(high, low, direction)
    raw_delta = high - low
    abs_spread = abs(raw_delta)
    floor = float(spec.get("spread_support_floor") or SPREAD_SUPPORT_FLOOR)
    direction_matches = signed > 0
    support_matched = bool(direction_matches and abs_spread >= floor)
    falsify_matched = bool((not direction_matches) and abs_spread >= floor)

    if support_matched:
        adjudication = ADJUDICATION_SUPPORTING
        reason = "frozen_support_rule_matched"
    elif falsify_matched:
        adjudication = ADJUDICATION_DISCONFIRMING
        reason = "frozen_falsify_rule_matched"
    else:
        adjudication = ADJUDICATION_INCONCLUSIVE
        reason = "spread_below_floor_or_direction_ambiguous"

    return {
        "adjudication": adjudication,
        "adjudicates_proposition": adjudication in (ADJUDICATION_SUPPORTING, ADJUDICATION_DISCONFIRMING),
        "reason": reason,
        "metrics": {
            "per_tier_n": per_tier_n,
            "per_tier_return": per_tier_return,
            "low_tier_realized_return": low,
            "high_tier_realized_return": high,
            "high_minus_low": raw_delta,
            "signed_contrast": signed,
            "proposition_success_metric": signed,
            "quintile_mean_spread": abs_spread,
            "coverage": coverage,
            "expected_n": expected,
            "covered_n": covered,
        },
        "support_matched": support_matched,
        "falsify_matched": falsify_matched,
        "missing_data": False,
        "coverage": coverage,
    }


def evaluate_claim_aligned_metrics(
    *,
    panel: pd.DataFrame,
    birth_trade_date: str,
    symbols: Tuple[str, ...],
    horizon: str,
    return_field: str,
    contract: Any,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], str]:
    """
    Returns (generic_outcomes, claim_aligned_block, evaluation_status).

    Generic cohort metrics are always descriptive/contextual.
    Claim-aligned metrics are produced only when the frozen contract is sufficient.
    """
    spec = extract_claim_spec(contract)
    status_ok = "EVALUATED"
    status_missing = "MISSING_DATA"

    if panel is None or panel.empty or return_field not in panel.columns:
        claim = _legacy_claim_block() if not spec or spec.get("claim_contract_status") == CLAIM_CONTRACT_LEGACY else {
            "claim_family": spec.get("claim_family"),
            "claim_contract_status": spec.get("claim_contract_status"),
            "adjudication": ADJUDICATION_MISSING,
            "adjudicates_proposition": False,
            "reason": "missing_panel_or_return_field",
            "metrics": {},
            "support_matched": None,
            "falsify_matched": None,
            "missing_data": True,
            "coverage": 0.0,
        }
        return None, claim, status_missing

    df = panel.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    sub = df[df["trade_date"] == str(birth_trade_date)]
    if "symbol" in sub.columns and symbols:
        matched = sub[sub["symbol"].astype(str).isin(set(symbols))]
        if not matched.empty:
            sub = matched
    if sub.empty or return_field not in sub.columns:
        claim = {
            "claim_family": (spec or {}).get("claim_family") or CLAIM_FAMILY_LEGACY,
            "claim_contract_status": (spec or {}).get("claim_contract_status") or CLAIM_CONTRACT_LEGACY,
            "adjudication": ADJUDICATION_MISSING,
            "adjudicates_proposition": False,
            "reason": "no_birth_date_rows_or_return_field",
            "metrics": {},
            "support_matched": None,
            "falsify_matched": None,
            "missing_data": True,
            "coverage": 0.0,
        }
        return None, claim, status_missing

    vals = sub[return_field].dropna()
    if vals.empty:
        claim = {
            "claim_family": (spec or {}).get("claim_family") or CLAIM_FAMILY_LEGACY,
            "claim_contract_status": (spec or {}).get("claim_contract_status") or CLAIM_CONTRACT_LEGACY,
            "adjudication": ADJUDICATION_MISSING,
            "adjudicates_proposition": False,
            "reason": "all_returns_missing",
            "metrics": {},
            "support_matched": None,
            "falsify_matched": None,
            "missing_data": True,
            "coverage": 0.0,
        }
        return None, claim, status_missing

    generic = _generic_cohort_metrics(vals, horizon, return_field)
    if "symbol" in sub.columns:
        generic["symbols_evaluated"] = sorted(sub.loc[vals.index, "symbol"].astype(str).unique().tolist())[:50]

    if not spec or spec.get("claim_contract_status") != CLAIM_CONTRACT_ALIGNED:
        claim = _legacy_claim_block()
        claim["reason"] = "legacy_or_insufficient_claim_specification"
        return generic, claim, status_ok

    family = spec.get("claim_family")
    if family == CLAIM_FAMILY_CROSS_SECTIONAL_TIER:
        claim = _evaluate_tier_claim(sub=sub, ret_col=return_field, spec=spec)
        claim["claim_family"] = family
        claim["claim_contract_status"] = CLAIM_CONTRACT_ALIGNED
        return generic, claim, status_ok

    claim = {
        "claim_family": family or CLAIM_FAMILY_GENERIC_COHORT,
        "claim_contract_status": CLAIM_CONTRACT_ALIGNED,
        "adjudication": ADJUDICATION_CONTEXT_ONLY,
        "adjudicates_proposition": False,
        "reason": "family_has_no_relative_claim_evaluator",
        "metrics": {},
        "support_matched": None,
        "falsify_matched": None,
        "missing_data": False,
        "coverage": 1.0,
    }
    return generic, claim, status_ok


def interpret_claim_aligned_evidence(
    *,
    claim_aligned: Dict[str, Any],
    generic: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Separate claim adjudication from contextual cohort description.

    A generic cohort return must not masquerade as validation of a
    cross-sectional differential claim.
    """
    adjudication = claim_aligned.get("adjudication") or ADJUDICATION_CONTEXT_ONLY
    family = claim_aligned.get("claim_family")
    supports = None
    contradicts = None
    if adjudication == ADJUDICATION_SUPPORTING:
        supports = True
        contradicts = False
    elif adjudication == ADJUDICATION_DISCONFIRMING:
        supports = False
        contradicts = True

    rationale = [
        f"claim_family:{family}",
        f"adjudication:{adjudication}",
        f"reason:{claim_aligned.get('reason')}",
    ]
    if family == CLAIM_FAMILY_CROSS_SECTIONAL_TIER and adjudication in (
        ADJUDICATION_CONTEXT_ONLY,
        ADJUDICATION_LEGACY,
    ):
        rationale.append("generic_cohort_return_is_context_only")
        rationale.append("whole_cohort_mean_cannot_adjudicate_relative_claim")

    return {
        "claim_adjudication": adjudication,
        "adjudicates_proposition": bool(claim_aligned.get("adjudicates_proposition")),
        "supports_birth_expectation": supports,
        "contradicts_birth_expectation": contradicts,
        "automatic_belief_change": False,
        "generic_cohort_role": "CONTEXT_ONLY",
        "generic_cohort_mean_return": (generic or {}).get("cohort_mean_return"),
        "claim_metrics": claim_aligned.get("metrics") or {},
        "rationale_keys": rationale,
        "suggested_lifecycle_signal": {
            ADJUDICATION_SUPPORTING: "FORWARD_CLAIM_SUPPORTING",
            ADJUDICATION_DISCONFIRMING: "FORWARD_CLAIM_DISCONFIRMING",
            ADJUDICATION_INCONCLUSIVE: "FORWARD_CLAIM_INCONCLUSIVE",
            ADJUDICATION_CONTEXT_ONLY: "FORWARD_EVIDENCE_CONTEXT_ONLY",
            ADJUDICATION_MISSING: "FORWARD_CLAIM_MISSING_DATA",
            ADJUDICATION_LEGACY: "FORWARD_CLAIM_LEGACY_UNSPECIFIED",
        }.get(adjudication, "FORWARD_EVIDENCE_AMBIGUOUS"),
    }

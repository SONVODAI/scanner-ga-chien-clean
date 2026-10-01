"""
Canonical Edge Research EOD cycle: Phase A → Phase C → Phase B.

Headless-safe. No Streamlit dependency. App.py and CLI share this function.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import pandas as pd

from modules.edge_research.anti_context import (
    learn_anti_context,
    mature_shadow_observations,
    run_shadow_counterfactual_scan,
)
from modules.edge_research.contracts import ASSESSMENT_UNABLE_TO_ASSESS
from modules.edge_research.forward_evidence import apply_health_transitions, attach_baselines_to_matured_births
from modules.edge_research.forward_health_policy import DEFAULT_FORWARD_HEALTH_POLICY, ForwardHealthPolicy
from modules.edge_research.forward_maturity import mature_edge_forward_ledger
from modules.edge_research.storage import resolve_data_dir


def run_continuous_learning(
    session_date: str,
    *,
    data_dir: Optional[Path] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    session_calendar: Optional[Sequence[str]] = None,
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
    outcomes_df: Optional[pd.DataFrame] = None,
    policy: ForwardHealthPolicy = DEFAULT_FORWARD_HEALTH_POLICY,
    market_context: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Mature prior births, update contemporaneous baselines, evaluate health,
    learn anti-context. Failures are isolated per step.
    """
    errors: list[str] = []
    maturity: Dict[str, Any] = {}
    baselines: Dict[str, Any] = {}
    shadow_maturity: Dict[str, Any] = {}
    health: Dict[str, Any] = {}
    anti: Dict[str, Any] = {}
    if ohlcv_by_symbol is None and outcomes_df is None:
        try:
            from modules.edge_research.adapters import load_canonical_maturity_inputs

            prod_outcomes, prod_dates = load_canonical_maturity_inputs()
            if prod_outcomes is not None and not prod_outcomes.empty:
                outcomes_df = prod_outcomes
            if session_calendar is None and prod_dates:
                session_calendar = prod_dates
        except Exception:
            pass
    try:
        maturity = mature_edge_forward_ledger(
            session_date,
            data_dir=data_dir,
            session_calendar=session_calendar,
            freeze_df=freeze_df,
            ohlcv_by_symbol=ohlcv_by_symbol,
            outcomes_df=outcomes_df,
        )
    except Exception as exc:
        errors.append(f"maturity: {exc}")
        maturity = {"ok": False, "reason": "MATCHER_EXCEPTION", "detail": str(exc)}
    try:
        baselines = attach_baselines_to_matured_births(
            data_dir=data_dir,
            freeze_df=freeze_df,
            session_calendar=session_calendar,
            ohlcv_by_symbol=ohlcv_by_symbol,
            outcomes_df=outcomes_df,
            policy=policy,
        )
    except Exception as exc:
        errors.append(f"baseline: {exc}")
    try:
        shadow_maturity = mature_shadow_observations(
            session_date,
            data_dir=data_dir,
            session_calendar=session_calendar,
            freeze_df=freeze_df,
            ohlcv_by_symbol=ohlcv_by_symbol,
            outcomes_df=outcomes_df,
            policy=policy,
        )
    except Exception as exc:
        errors.append(f"shadow_maturity: {exc}")
    try:
        health = apply_health_transitions(
            data_dir=data_dir,
            freeze_df=freeze_df,
            session_date=session_date,
            policy=policy,
        )
    except Exception as exc:
        errors.append(f"health: {exc}")
        health = {"ok": False, "error": str(exc)}
    try:
        anti = learn_anti_context(data_dir=data_dir, policy=policy, session_date=session_date)
    except Exception as exc:
        errors.append(f"anti_context: {exc}")
    return {
        "ok": not errors,
        "errors": errors,
        "maturity": maturity,
        "baselines": baselines,
        "shadow_maturity": shadow_maturity,
        "health": health,
        "anti_context": anti,
    }


def run_edge_research_eod_cycle(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    freeze_path: Optional[Path] = None,
    session_calendar: Optional[Sequence[str]] = None,
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
    outcomes_df: Optional[pd.DataFrame] = None,
    market_context: Optional[Dict[str, str]] = None,
    policy: ForwardHealthPolicy = DEFAULT_FORWARD_HEALTH_POLICY,
    panel: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Production order:
      Phase A qualification
      → Phase C mature/health/anti-context
      → Phase B future recognition (uses updated edge state)
      → today's research-only shadow scan
    """
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.t0_universe import latest_freeze_trade_date, load_t0_freeze

    engine = EdgeResearchEngine(data_dir=data_dir)
    session = trade_date or ""
    if not session:
        try:
            session = latest_freeze_trade_date(freeze_df if freeze_df is not None else load_t0_freeze(freeze_path)) or ""
        except Exception:
            session = ""

    errors: list[str] = []
    qualification: Dict[str, Any] = {}
    continuous: Dict[str, Any] = {}
    recognition: Dict[str, Any] = {}
    shadow: Dict[str, Any] = {}

    try:
        qualification = engine.run_qualification_cycle(panel=panel)
    except Exception as exc:
        errors.append(f"qualification: {exc}")
        qualification = {"errors": [str(exc)]}

    try:
        continuous = run_continuous_learning(
            session,
            data_dir=engine.data_dir,
            freeze_df=freeze_df,
            session_calendar=session_calendar,
            ohlcv_by_symbol=ohlcv_by_symbol,
            outcomes_df=outcomes_df,
            policy=policy,
            market_context=market_context,
        )
        if continuous.get("errors"):
            errors.extend(list(continuous.get("errors") or []))
    except Exception as exc:
        errors.append(f"continuous_learning: {exc}")
        continuous = {"ok": False, "error": str(exc)}

    try:
        recognition = engine.run_future_recognition(
            trade_date=session or None,
            freeze_df=freeze_df,
            freeze_path=freeze_path,
            market_context=market_context,
        )
    except Exception as exc:
        errors.append(f"recognition: {exc}")
        recognition = {
            "assessment_state": ASSESSMENT_UNABLE_TO_ASSESS,
            "reason": "MATCHER_EXCEPTION",
            "failure_detail": str(exc),
        }

    try:
        shadow = run_shadow_counterfactual_scan(
            session,
            data_dir=engine.data_dir,
            freeze_df=freeze_df,
            market_context=market_context,
            session_calendar=session_calendar,
        )
    except Exception as exc:
        errors.append(f"shadow: {exc}")
        shadow = {"ok": False, "error": str(exc)}

    return {
        "trade_date": session,
        "qualification": qualification,
        "continuous_learning": continuous,
        "recognition": recognition,
        "shadow": shadow,
        "errors": errors,
        "order": ["qualification", "continuous_learning", "recognition", "shadow"],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Headless Mr.BOT Edge Research EOD cycle (A → C → B). No Streamlit."
    )
    parser.add_argument("--trade-date", default="", help="YYYY-MM-DD; default latest T0 freeze date")
    parser.add_argument("--data-dir", default="", help="Override EDGE_RESEARCH_DATA_DIR")
    args = parser.parse_args(list(argv) if argv is not None else None)
    data_dir = Path(args.data_dir) if args.data_dir else None
    result = run_edge_research_eod_cycle(trade_date=args.trade_date or None, data_dir=data_dir)
    print(json.dumps(result, indent=2, default=str))
    rec = result.get("recognition") or {}
    if rec.get("assessment_state") == ASSESSMENT_UNABLE_TO_ASSESS:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Canonical Edge Research EOD cycle: Phase A → Phase C → Phase B.

Headless-safe. No Streamlit dependency. App.py and CLI share this function.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
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
from modules.edge_research.storage import ensure_storage, resolve_data_dir

EOD_STATUS_FILENAME = "latest_eod_run.json"
SYSTEM_SUCCESS = "SUCCESS"
SYSTEM_FAILED = "FAILED"
SYSTEM_SKIPPED = "SKIPPED"
SKIP_NON_TRADING_DAY = "SKIPPED_NON_TRADING_DAY"
SKIP_T0_NOT_READY = "SKIPPED_T0_NOT_READY"
RUNNER_HEADLESS = "headless"
RUNNER_STREAMLIT_FALLBACK = "streamlit_fallback"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vn_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=7)))


def vn_today() -> str:
    return vn_now().strftime("%Y-%m-%d")


def _norm_date(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(pd.Timestamp(ts).normalize().date())


def freeze_contains_session(trade_date: str, freeze_df: Optional[pd.DataFrame] = None) -> bool:
    if not trade_date:
        return False
    frame = freeze_df
    if frame is None:
        try:
            from modules.edge_research.t0_universe import load_t0_freeze

            frame = load_t0_freeze()
        except Exception:
            return False
    if frame is None or frame.empty or "trade_date" not in frame.columns:
        return False
    dates = {_norm_date(v) for v in frame["trade_date"].tolist()}
    return _norm_date(trade_date) in dates


def eod_status_path(data_dir: Optional[Path] = None) -> Path:
    return ensure_storage(data_dir) / EOD_STATUS_FILENAME


def read_latest_eod_status(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = resolve_data_dir(data_dir) / EOD_STATUS_FILENAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_latest_eod_status(payload: Mapping[str, Any], data_dir: Optional[Path] = None) -> Path:
    path = eod_status_path(data_dir)
    path.write_text(json.dumps(dict(payload), indent=2, default=str), encoding="utf-8")
    return path


def production_preflight(
    trade_date: Optional[str],
    *,
    freeze_df: Optional[pd.DataFrame] = None,
    explicit_trade_date: bool = False,
) -> Dict[str, Any]:
    """
    Decide whether a headless production run should execute or skip.

    Uses canonical freeze presence as the trading-session source of truth.
    Weekend/holiday with no freeze row → skip, never fake assessment.
    """
    intended = _norm_date(trade_date) if trade_date else vn_today()
    weekday = pd.Timestamp(intended).weekday() if intended else vn_now().weekday()
    if weekday >= 5 and not freeze_contains_session(intended, freeze_df):
        return {
            "skip": True,
            "system_status": SYSTEM_SKIPPED,
            "skip_reason": SKIP_NON_TRADING_DAY,
            "trade_date": intended,
        }
    if not freeze_contains_session(intended, freeze_df):
        # Explicit replay of a known date without freeze is still a skip, not a fake NO_MATCH.
        return {
            "skip": True,
            "system_status": SYSTEM_SKIPPED,
            "skip_reason": SKIP_T0_NOT_READY,
            "trade_date": intended,
            "explicit_trade_date": explicit_trade_date,
        }
    return {"skip": False, "trade_date": intended, "system_status": SYSTEM_SUCCESS}


def _skipped_result(
    *,
    trade_date: str,
    reason: str,
    runner: str,
    started_at: str,
) -> Dict[str, Any]:
    finished = _iso_now()
    result = {
        "trade_date": trade_date,
        "system_status": SYSTEM_SKIPPED,
        "skip_reason": reason,
        "runner": runner,
        "started_at": started_at,
        "finished_at": finished,
        "qualification": {},
        "continuous_learning": {},
        "recognition": {},
        "shadow": {},
        "errors": [],
        "order": ["qualification", "continuous_learning", "recognition", "shadow"],
        "step_timestamps": {},
        "ran_science": False,
        "assessment_state": "",
        "assessment_reason": "",
    }
    return result


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
    runner: str = RUNNER_HEADLESS,
    persist_status: bool = True,
    enforce_canonical_t0: bool = False,
) -> Dict[str, Any]:
    """
    Production order:
      Phase A qualification
      → Phase C mature/health/anti-context
      → Phase B future recognition (uses updated edge state)
      → today's research-only shadow scan

    enforce_canonical_t0: production CLI/systemd skip if freeze lacks the session.
    Tests inject freeze_df and leave this False so fixtures still run.
    """
    from modules.edge_research.engine import EdgeResearchEngine
    from modules.edge_research.t0_universe import latest_freeze_trade_date, load_t0_freeze

    started_at = _iso_now()
    engine = EdgeResearchEngine(data_dir=data_dir)
    explicit = bool(trade_date)
    session = trade_date or ""
    loaded_freeze = freeze_df
    if loaded_freeze is None:
        try:
            loaded_freeze = load_t0_freeze(freeze_path)
        except Exception:
            loaded_freeze = None
    if not session:
        try:
            session = latest_freeze_trade_date(loaded_freeze) if loaded_freeze is not None else ""
        except Exception:
            session = ""

    if enforce_canonical_t0:
        intended = _norm_date(trade_date) if explicit else vn_today()
        pre = production_preflight(intended, freeze_df=loaded_freeze, explicit_trade_date=explicit)
        if pre.get("skip"):
            result = _skipped_result(
                trade_date=str(pre.get("trade_date") or intended),
                reason=str(pre.get("skip_reason") or SKIP_T0_NOT_READY),
                runner=runner,
                started_at=started_at,
            )
            if persist_status:
                write_latest_eod_status(result, data_dir=engine.data_dir)
            return result
        session = str(pre.get("trade_date") or intended)

    errors: list[str] = []
    qualification: Dict[str, Any] = {}
    continuous: Dict[str, Any] = {}
    recognition: Dict[str, Any] = {}
    shadow: Dict[str, Any] = {}
    step_timestamps: Dict[str, str] = {}

    step_timestamps["qualification_started_at"] = _iso_now()
    try:
        qualification = engine.run_qualification_cycle(panel=panel)
    except Exception as exc:
        errors.append(f"qualification: {exc}")
        qualification = {"errors": [str(exc)]}
    step_timestamps["qualification_finished_at"] = _iso_now()

    step_timestamps["continuous_learning_started_at"] = _iso_now()
    try:
        continuous = run_continuous_learning(
            session,
            data_dir=engine.data_dir,
            freeze_df=freeze_df if freeze_df is not None else loaded_freeze,
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
    step_timestamps["continuous_learning_finished_at"] = _iso_now()

    step_timestamps["recognition_started_at"] = _iso_now()
    try:
        recognition = engine.run_future_recognition(
            trade_date=session or None,
            freeze_df=freeze_df if freeze_df is not None else loaded_freeze,
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
    step_timestamps["recognition_finished_at"] = _iso_now()

    step_timestamps["shadow_started_at"] = _iso_now()
    try:
        shadow = run_shadow_counterfactual_scan(
            session,
            data_dir=engine.data_dir,
            freeze_df=freeze_df if freeze_df is not None else loaded_freeze,
            market_context=market_context,
            session_calendar=session_calendar,
        )
    except Exception as exc:
        errors.append(f"shadow: {exc}")
        shadow = {"ok": False, "error": str(exc)}
    step_timestamps["shadow_finished_at"] = _iso_now()

    rec_state = str((recognition or {}).get("assessment_state") or "")
    rec_reason = str((recognition or {}).get("reason") or "")
    # A completed scientific assessment — including UNABLE_TO_ASSESS — is SYSTEM SUCCESS.
    # systemd must not treat NO_MATCH / UNABLE as a unit failure.
    system_status = SYSTEM_SUCCESS
    finished_at = _iso_now()
    result = {
        "trade_date": session,
        "qualification": qualification,
        "continuous_learning": continuous,
        "recognition": recognition,
        "shadow": shadow,
        "errors": errors,
        "order": ["qualification", "continuous_learning", "recognition", "shadow"],
        "step_timestamps": step_timestamps,
        "runner": runner,
        "started_at": started_at,
        "finished_at": finished_at,
        "system_status": system_status,
        "ran_science": True,
        "assessment_state": rec_state,
        "assessment_reason": rec_reason,
    }
    if persist_status:
        write_latest_eod_status(
            {
                "trade_date": session,
                "system_status": system_status,
                "skip_reason": "",
                "assessment_state": rec_state,
                "assessment_reason": rec_reason,
                "runner": runner,
                "started_at": started_at,
                "finished_at": finished_at,
                "order": result["order"],
                "step_timestamps": step_timestamps,
                "errors": errors,
                "qualified_match_count": (recognition or {}).get("qualified_match_count"),
            },
            data_dir=engine.data_dir,
        )
    return result


def run_edge_research_eod_from_ui(
    *,
    trade_date: Optional[str] = None,
    data_dir: Optional[Path] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Streamlit fallback. Headless/systemd is authoritative.

    If a successful or skipped headless run already exists for this trade_date,
    do not run a second scientific cycle. UI only reads persisted results.
    """
    intended = _norm_date(trade_date) if trade_date else ""
    prior = read_latest_eod_status(data_dir)
    prior_date = _norm_date(prior.get("trade_date"))
    prior_runner = str(prior.get("runner") or "")
    prior_system = str(prior.get("system_status") or "")
    if (
        intended
        and prior_date == intended
        and prior_runner in {RUNNER_HEADLESS, "systemd", "cli"}
        and prior_system in {SYSTEM_SUCCESS, SYSTEM_SKIPPED}
    ):
        return {
            "skipped_duplicate": True,
            "reason": "HEADLESS_AUTHORITATIVE_ALREADY_RAN",
            "prior": prior,
            "trade_date": intended,
            "system_status": prior_system,
            "assessment_state": prior.get("assessment_state"),
            "assessment_reason": prior.get("assessment_reason"),
            "ran_science": False,
            "runner": RUNNER_STREAMLIT_FALLBACK,
        }
    return run_edge_research_eod_cycle(
        trade_date=trade_date,
        data_dir=data_dir,
        runner=RUNNER_STREAMLIT_FALLBACK,
        enforce_canonical_t0=False,
        **kwargs,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Headless Mr.BOT Edge Research EOD cycle (A → C → B). No Streamlit."
    )
    parser.add_argument("--trade-date", default="", help="YYYY-MM-DD; default today VN, gated on canonical T0 freeze")
    parser.add_argument("--data-dir", default="", help="Override EDGE_RESEARCH_DATA_DIR")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if canonical T0 freeze does not yet contain the session (tests/debug only).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    data_dir = Path(args.data_dir) if args.data_dir else None
    result = run_edge_research_eod_cycle(
        trade_date=args.trade_date or None,
        data_dir=data_dir,
        runner=RUNNER_HEADLESS,
        enforce_canonical_t0=not args.force,
    )
    print(json.dumps(result, indent=2, default=str))
    if result.get("system_status") == SYSTEM_FAILED:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

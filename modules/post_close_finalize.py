"""Stage 2: finalize session D from a validated handoff, then the close scan.

Buy Elite, earning-learning, and forward-shadow consume the handoff only.
A missing, stale, or invalid handoff is ``NO_VALID_HANDOFF``. It is never
replaced with an evening scan.

Canonical Market T0 and SweetSpot keep the >=18:00 same-calendar-day
contract. They are the only writers allowed to see ``close_scan``. After
midnight, those two report ``SAME_DAY_WINDOW_CLOSED`` for session D and do
not freeze D+1.

Market T0 and SweetSpot use the headless close scan
(``modules.close_session_scan``), which executes the production scan
definitions. That scan is not the intraday handoff. A supplied ``close_scan``
callback replaces the loader. An empty or failed scan does not call either
writer.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Callable, Optional

import pandas as pd

from modules.intraday_execution_boundary import VN_TZ, as_vn
from modules.session_handoff import (
    frames_as_dataframes,
    load_valid_handoff,
    parse_captured_at,
    validate_handoff,
)

NO_VALID_HANDOFF = "NO_VALID_HANDOFF"
SAME_DAY_WINDOW_CLOSED = "SAME_DAY_WINDOW_CLOSED"
CLOSE_SCAN_UNAVAILABLE = "CLOSE_SCAN_UNAVAILABLE"
BEFORE_CANONICAL_WINDOW = "BEFORE_CANONICAL_WINDOW"

HANDOFF_STEPS = ("forward_shadow", "buy_elite", "earning_learning")
CloseScan = Callable[[], Any]


def _status(status: str, **extra: Any) -> dict[str, Any]:
    out = {"status": status}
    out.update(extra)
    return out


def _market_number(market: dict, key: str) -> Optional[float]:
    value = market.get(key)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _finalize_forward(handoff: dict, *, ledger_path=None) -> dict[str, Any]:
    from modules.regime_alpha_forward_eval import finalize_forward_shadow_snapshot

    frames = frames_as_dataframes(handoff)
    market = handoff.get("market") or {}
    result = finalize_forward_shadow_snapshot(
        session_date=str(handoff.get("trade_date")),
        trading_today=bool(handoff.get("trading_today")),
        market_real=_market_number(market, "market_real"),
        market_forecast=_market_number(market, "market_forecast"),
        breadth=_market_number(market, "breadth"),
        recommendations=frames["recommendations"],
        brain_df=frames["leader_brain"],
        patterns_df=frames["pattern_library"],
        history_df=frames["leader_session_snapshot"],
        ledger_path=ledger_path,
    )
    result["status"] = "FROZEN" if result.get("ok") else result.get("reason", "SKIPPED")
    result["source"] = "session_handoff_v1"
    return result


def _finalize_buy_elite(handoff: dict) -> dict[str, Any]:
    from modules.buy_elite_learning import run_buy_elite_learning_cycle

    frames = frames_as_dataframes(handoff)
    market = handoff.get("market") or {}
    observed = parse_captured_at(handoff.get("captured_at"))
    history, _profile, hist_status, profile_status = run_buy_elite_learning_cycle(
        buy_elite_df=frames["buy_elite"],
        scan_df=frames["learning_board"],
        market_real=_market_number(market, "market_real") or 0.0,
        market_forecast=_market_number(market, "market_forecast") or 0.0,
        trading_today=bool(handoff.get("trading_today")),
        session_date=str(handoff.get("trade_date")),
        observed_at=observed,
    )
    dates = []
    if history is not None and not history.empty and "date" in history.columns:
        trade_date = str(handoff.get("trade_date"))
        dates = history.loc[history["date"].astype(str).str.slice(0, 10) == trade_date, "date"].astype(str).unique().tolist()
    return {
        "status": "APPENDED",
        "source": "session_handoff_v1",
        "session_date": str(handoff.get("trade_date")),
        "captured_at": handoff.get("captured_at"),
        "history_status": hist_status,
        "profile_status": profile_status,
        "session_dates_written": dates,
    }


def _finalize_learning(handoff: dict, *, data_dir=None) -> dict[str, Any]:
    from modules.earning_learning import update_learning

    frames = frames_as_dataframes(handoff)
    market = handoff.get("market") or {}
    context = {
        "market_real": _market_number(market, "market_real"),
        "market_score": _market_number(market, "market_real"),
        "market_live": _market_number(market, "market_live"),
        "market_forecast": _market_number(market, "market_forecast"),
        "market_regime": market.get("market_forecast_text") or "",
    }
    breadth = _market_number(market, "breadth")
    if breadth is not None:
        context["breadth"] = breadth
    result = update_learning(
        earning_board_df=frames["learning_board"],
        market_context=context,
        trading_today=bool(handoff.get("trading_today")),
        data_dir=data_dir,
    )
    if isinstance(result, dict):
        result = dict(result)
        result["status"] = result.get("skipped_reason") or "UPDATED"
        result["source"] = "session_handoff_v1"
        return result
    return {"status": "UPDATED", "source": "session_handoff_v1"}


def _close_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, pd.DataFrame):
        return {"scan_df": payload}
    if isinstance(payload, dict):
        return payload
    raise TypeError("close_scan must return a DataFrame or a mapping")


def _run_close_writers(payload: dict[str, Any], *, trade_date: str, now: datetime, data_dir=None) -> tuple[dict, dict]:
    from modules.evolution_health import get_earning_money_board
    from modules.market_aware_sweetspot_observer import freeze_daily_observer_if_eligible
    from modules.market_t0_capture import capture_market_t0_snapshot

    scan_df = payload.get("scan_df")
    if not isinstance(scan_df, pd.DataFrame):
        raise TypeError("close_scan payload is missing scan_df")
    market_t0 = capture_market_t0_snapshot(
        scan_df=scan_df,
        trade_date=trade_date,
        market_real=payload.get("market_real"),
        market_live=payload.get("market_live"),
        market_forecast=payload.get("market_forecast"),
        market_forecast_text=str(payload.get("market_forecast_text") or ""),
        market_confidence=payload.get("market_confidence"),
        market_status=str(payload.get("market_status") or ""),
        market_action=str(payload.get("market_action") or ""),
        market_regime=str(payload.get("market_regime") or ""),
        market_regime_note=str(payload.get("market_regime_note") or ""),
        rsi_breadth_report=payload.get("rsi_breadth_report"),
        trading_today=bool(payload.get("trading_today", True)),
        trading_reason=str(payload.get("trading_reason") or ""),
        data_dir=data_dir,
        now=now,
    )
    market_t0 = dict(market_t0)
    market_t0["status"] = "CAPTURED" if market_t0.get("ok") else "CAPTURE_FAILED"
    market_t0["source"] = "close_scan"
    board = get_earning_money_board(scan_df)
    sweetspot = freeze_daily_observer_if_eligible(
        t0_date=trade_date,
        earning_board_df=board,
        market_real=payload.get("market_real"),
        market_forecast=payload.get("market_forecast"),
        breadth=payload.get("breadth"),
        market_regime=str(payload.get("market_regime") or ""),
        scan_df=scan_df,
        data_dir=data_dir,
        now=now,
    )
    sweetspot = dict(sweetspot)
    sweetspot["status"] = "FROZEN" if sweetspot.get("added", 0) else sweetspot.get("skipped_reason", "SKIPPED")
    sweetspot["source"] = "close_scan"
    return market_t0, sweetspot


def _mature(session_date: str) -> dict[str, Any]:
    notes = {}
    try:
        from modules.regime_alpha_forward_eval import mature_forward_outcomes

        mature_forward_outcomes(immature_session_dates=[session_date])
        notes["forward_outcomes"] = "RAN"
    except Exception as exc:
        notes["forward_outcomes"] = f"{type(exc).__name__}: {exc}"
    try:
        from modules.market_aware_sweetspot_observer import mature_observer_outcomes

        mature_observer_outcomes(immature_session_dates=[session_date])
        notes["observer_outcomes"] = "RAN"
    except Exception as exc:
        notes["observer_outcomes"] = f"{type(exc).__name__}: {exc}"
    notes["status"] = "RAN"
    return notes


def run_post_close_finalize(
    *,
    now: Optional[datetime] = None,
    session_date: Optional[str] = None,
    close_scan: Optional[CloseScan] = None,
    handoff: Optional[dict] = None,
    data_dir=None,
    ledger_path=None,
    mature: bool = True,
) -> dict[str, Any]:
    """Finalize session D. ``close_scan`` is used only for Market T0 and SweetSpot."""
    local_now = as_vn(now or datetime.now(VN_TZ))
    vn_today = local_now.strftime("%Y-%m-%d")
    session_date = str(session_date or vn_today)
    report: dict[str, Any] = {
        "session_date": session_date,
        "vn_today": vn_today,
        "now": local_now.isoformat(),
        "close_scan_calls": 0,
        "steps": {},
    }

    if handoff is not None:
        ok, _reason = validate_handoff(handoff, path_trade_date=session_date)
        resolved = handoff if ok else None
    else:
        resolved = load_valid_handoff(session_date)
    if resolved is None:
        for name in HANDOFF_STEPS:
            report["steps"][name] = _status(NO_VALID_HANDOFF, source=None)
    else:
        report["steps"]["forward_shadow"] = _finalize_forward(resolved, ledger_path=ledger_path)
        report["steps"]["buy_elite"] = _finalize_buy_elite(resolved)
        report["steps"]["earning_learning"] = _finalize_learning(resolved, data_dir=data_dir)

    canonical_minute = 18 * 60
    clock = local_now.hour * 60 + local_now.minute
    if session_date != vn_today:
        report["steps"]["market_t0"] = _status(SAME_DAY_WINDOW_CLOSED, source=None)
        report["steps"]["sweetspot"] = _status(SAME_DAY_WINDOW_CLOSED, source=None)
    elif clock < canonical_minute:
        report["steps"]["market_t0"] = _status(BEFORE_CANONICAL_WINDOW, source=None)
        report["steps"]["sweetspot"] = _status(BEFORE_CANONICAL_WINDOW, source=None)
    else:
        report["close_scan_calls"] = 1
        if close_scan is None:
            from modules.close_session_scan import build_close_scan_inputs

            payload = build_close_scan_inputs(now=local_now)
            if not payload.get("ok"):
                status = str(payload.get("status") or "CLOSE_SCAN_FAILED")
                detail: dict[str, Any] = {
                    "source": "close_scan",
                    "trade_date": payload.get("trade_date", session_date),
                }
                if payload.get("error"):
                    detail["error"] = payload["error"]
                report["steps"]["market_t0"] = _status(status, **detail)
                report["steps"]["sweetspot"] = _status(status, **detail)
                payload = None
        else:
            payload = _close_payload(close_scan())
        if payload is not None:
            market_t0, sweetspot = _run_close_writers(
                payload,
                trade_date=session_date,
                now=local_now,
                data_dir=data_dir,
            )
            report["steps"]["market_t0"] = market_t0
            report["steps"]["sweetspot"] = sweetspot

    if mature:
        report["steps"]["maturation"] = _mature(session_date)
    return report


def main() -> None:
    if os.environ.get("POST_CLOSE_RESEARCH_ENABLED") != "true":
        print(json.dumps({
            "status": "SCHEDULE_DISABLED",
            "reason": "POST_CLOSE_RESEARCH_ENABLED is not true",
        }))
        return
    from modules.forward_ledger_store import (
        FORWARD_LEDGER_NAMES,
        _storage_for,
        authority_ready,
        brain_dir,
    )

    store = _storage_for(brain_dir() / FORWARD_LEDGER_NAMES[0])
    if not authority_ready(storage=store):
        print(json.dumps({
            "status": "AUTHORITY_NOT_READY",
            "reason": "forward ledger migration report is not ready",
        }))
        return
    report = run_post_close_finalize()
    print(json.dumps(report, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()

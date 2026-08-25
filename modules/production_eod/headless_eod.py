"""
Headless production EOD — Streamlit-free canonical daily accumulation.

Owns EMS / MDT0 / EL learning / Forecast Memory prerequisites for the
mrbot-daily-research timer. Does not change REAL/LIVE/FC formulas.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_UNIVERSE = 142
HEADLESS_EOD_VERSION = "headless_eod_v1"


@dataclass
class HeadlessEodResult:
    ok: bool
    trade_date: str
    version: str = HEADLESS_EOD_VERSION
    stage_disposition: str = "FAILED"
    reason: str = ""
    started_at: str = ""
    completed_at: str = ""
    source_rows: int = 0
    universe_ok: bool = False
    after_close_eligible: bool = False
    trading_today: bool = False
    artifacts: Dict[str, Any] = field(default_factory=dict)
    market_real: Optional[float] = None
    market_live: Optional[float] = None
    market_forecast: Optional[float] = None
    forecast_memory: Dict[str, Any] = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def _iso(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now(VN_TZ).astimezone(datetime.now().astimezone().tzinfo)
    # store UTC Z
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def is_after_close_eligible(now: Optional[datetime] = None) -> bool:
    from modules.market_t0_capture import is_canonical_eligible

    return bool(is_canonical_eligible(now or vn_now()))


def resolve_trading_today(trade_date: str) -> tuple[bool, str]:
    """Mirror app.py is_vnindex_trading_today without Streamlit."""
    today = str(trade_date)[:10]
    try:
        from vnstock import stock_historical_data

        for typ in ("index", "stock"):
            try:
                df = stock_historical_data(
                    symbol="VNINDEX",
                    start_date=(vn_now() - timedelta(days=10)).strftime("%Y-%m-%d"),
                    end_date=today,
                    resolution="1D",
                    type=typ,
                    beautify=True,
                )
            except Exception:
                continue
            if df is None or df.empty:
                continue
            date_col = None
            for c in df.columns:
                if "date" in str(c).lower() or "time" in str(c).lower():
                    date_col = c
                    break
            if date_col is None:
                continue
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=[date_col]).sort_values(date_col)
            if df.empty:
                continue
            last_date = df[date_col].iloc[-1].strftime("%Y-%m-%d")
            if last_date == today:
                return True, f"VNINDEX có giao dịch hôm nay: {today}"
            return False, f"VNINDEX phiên mới nhất {last_date} (không phải {today})"
    except Exception as exc:
        logger.warning("trading_today probe failed: %s", exc)
    # Fail closed for LIVE production unless tests inject trading_today
    return False, "VNINDEX trading-day probe unavailable"


def _simple_regime(market_real: float, market_forecast: float) -> tuple[str, str]:
    """Same thresholds as app elite_regime labels (text only for MDT0 context)."""
    mr = float(market_real or 0)
    mf = float(market_forecast or 0)
    if mr >= 8 and mf >= 5:
        return "🟢 MÙA XUÂN", "Market khỏe: cho phép ưu tiên mã có động lượng + đồng thuận cao."
    if mr >= 6:
        return "🟡 TRUNG TÍNH", "Market trung tính: ưu tiên Pull/Early, mua nhỏ, stop gần."
    return "🔴 MÙA ĐÔNG", "Market yếu: chỉ lập watchlist, chưa giải ngân thật."


def should_attempt_headless_eod(
    trade_date: str,
    *,
    now: Optional[datetime] = None,
    allow_before_close_for_tests: bool = False,
) -> tuple[bool, str]:
    now = now or vn_now()
    td = str(trade_date)[:10]
    vn_today = now.strftime("%Y-%m-%d")
    if td != vn_today and not allow_before_close_for_tests:
        return False, f"trade_date_mismatch:{td}!={vn_today}"
    if not allow_before_close_for_tests and not is_after_close_eligible(now):
        return False, "BEFORE_EOD_PLUS_3H"
    return True, "ok"


def build_eod_scan_df(
    *,
    symbols: Optional[list] = None,
    scan_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build or accept the canonical board. Injected scan_df used by tests (no network)."""
    if scan_df is not None:
        out = scan_df.copy()
    else:
        from modules.scanner_core import WATCHLIST, run_scan

        out = run_scan(list(symbols) if symbols is not None else list(WATCHLIST))
    if out is None or out.empty:
        return pd.DataFrame()
    try:
        from modules.evolution_health import add_evolution_health

        out = add_evolution_health(out)
    except Exception as exc:
        logger.warning("add_evolution_health failed safely: %s", exc)
    return out


def run_headless_eod(
    trade_date: str,
    *,
    repo_root: Optional[Path] = None,
    scan_df: Optional[pd.DataFrame] = None,
    now: Optional[datetime] = None,
    trading_today: Optional[bool] = None,
    trading_reason: str = "",
    allow_before_close_for_tests: bool = False,
    skip_forecast_memory: bool = False,
    expected_universe: int = EXPECTED_UNIVERSE,
    include_vnindex_ohlcv: bool = True,
) -> Dict[str, Any]:
    """
    Produce canonical EOD artifacts without Streamlit.

    Order: board → EMS → MDT0 (+FM hook) → update_learning → explicit FM stage.
    Idempotent for the same trade_date (first-write-wins downstream).
    """
    root = Path(repo_root) if repo_root else REPO_ROOT
    td = str(trade_date)[:10]
    now = now or vn_now()
    started = _iso()
    result = HeadlessEodResult(ok=False, trade_date=td, started_at=started)
    ems_path = root / "data" / "earning_money_snapshots.csv"
    el_dir = root / "data" / "earning_learning"
    fm_dir = root / "data" / "forecast_research"
    md_path = el_dir / "market_daily_t0.csv"

    ok_attempt, attempt_reason = should_attempt_headless_eod(
        td, now=now, allow_before_close_for_tests=allow_before_close_for_tests
    )
    result.after_close_eligible = is_after_close_eligible(now) or allow_before_close_for_tests
    if not ok_attempt:
        result.stage_disposition = "WAITING_FOR_DATA"
        result.reason = attempt_reason
        result.completed_at = _iso()
        _write_status(root, result)
        return result.to_dict()

    if trading_today is None:
        trading_today, trading_reason = resolve_trading_today(td)
    result.trading_today = bool(trading_today)

    if not trading_today and not allow_before_close_for_tests:
        result.stage_disposition = "SKIPPED_NON_TRADING_DAY"
        result.reason = trading_reason or "not_trading_today"
        result.ok = True
        result.completed_at = _iso()
        _write_status(root, result)
        return result.to_dict()

    try:
        board = build_eod_scan_df(scan_df=scan_df)
        # Stamp trade_date so EL adaptation does not fall back to calendar today.
        if not board.empty and "trade_date" not in board.columns:
            board = board.copy()
            board["trade_date"] = td
        result.source_rows = int(len(board))
        result.universe_ok = result.source_rows >= expected_universe
        if board.empty:
            result.stage_disposition = "WAITING_FOR_DATA"
            result.reason = "empty_scan_board"
            result.completed_at = _iso()
            _write_status(root, result)
            return result.to_dict()
        if not result.universe_ok:
            result.stage_disposition = "WAITING_FOR_DATA"
            result.reason = f"incomplete_universe:{result.source_rows}/{expected_universe}"
            result.errors.append(result.reason)
            # Fail closed: do not write partial EMS/MDT0 as canonical EOD.
            result.completed_at = _iso()
            _write_status(root, result)
            return result.to_dict()

        from modules.scanner_core import (
            calc_market_forecast,
            calc_market_live,
            calc_market_real,
        )

        market_real = float(calc_market_real(board))
        market_live = float(calc_market_live(board))
        fc = calc_market_forecast(board)
        market_forecast = float(fc.score)
        market_confidence = (
            float(fc.confidence) if getattr(fc, "confidence", None) is not None else None
        )
        market_forecast_text = str(getattr(fc, "text", "") or "")
        result.market_real = market_real
        result.market_live = market_live
        result.market_forecast = market_forecast

        # --- EMS (durable via snapshot_storage GitHub path when configured) ---
        from modules.daily_summary import run_daily_summary

        ems_path.parent.mkdir(parents=True, exist_ok=True)
        ems = run_daily_summary(
            board,
            snapshot_date=td,
            snapshot_file=ems_path,
            save=True,
        )
        result.artifacts["ems"] = {
            "ok": True,
            "path": str(ems_path),
            "current_date": getattr(ems, "current_date", td),
            "rows": int(len(getattr(ems, "current", board))),
            "status": getattr(ems, "status", ""),
        }

        # --- MDT0 (+ nested FM hook with repo-local paths) ---
        from modules.market_t0_capture import capture_market_t0_snapshot

        regime_name, regime_note = _simple_regime(market_real, market_forecast)
        el_dir.mkdir(parents=True, exist_ok=True)

        mdt0 = capture_market_t0_snapshot(
            scan_df=board,
            trade_date=td,
            market_real=market_real,
            market_live=market_live,
            market_forecast=market_forecast,
            market_forecast_text=market_forecast_text,
            market_confidence=market_confidence,
            market_status="",
            market_action="",
            rsi_breadth_report=None,
            trading_today=True,
            trading_reason=trading_reason or f"headless_eod:{td}",
            market_regime=regime_name,
            market_regime_note=regime_note,
            data_dir=str(el_dir),
            include_vnindex_ohlcv=include_vnindex_ohlcv,
            now=now,
        )
        result.artifacts["mdt0"] = {
            "ok": True,
            "path": str(md_path),
            "canonical_added": mdt0.get("canonical_added"),
            "daily_snapshot_id": mdt0.get("daily_snapshot_id"),
            "forecast_t0_hook": mdt0.get("forecast_t0_hook"),
            "canonical_skipped_reason": mdt0.get("canonical_skipped_reason"),
        }

        # --- EL observations / freeze / outcomes / lifecycle ---
        from modules.earning_learning import update_learning
        from modules.learning_t0_capture import build_learning_input_df

        learning_input = build_learning_input_df(board)
        learning_raw = update_learning(
            earning_board_df=learning_input,
            market_context={
                "trade_date": td,
                "market_real": market_real,
                "market_score": market_real,
                "market_live": market_live,
                "market_forecast": market_forecast,
                "market_regime": market_forecast_text,
            },
            trading_today=True,
            data_dir=str(el_dir),
        )
        learning = (
            learning_raw.to_dict()
            if hasattr(learning_raw, "to_dict")
            else (learning_raw if isinstance(learning_raw, dict) else {})
        )
        result.artifacts["earning_learning"] = {
            "ok": bool(learning.get("ok", True)),
            "trade_date": learning.get("trade_date", td),
            "observations_added": learning.get("observations_added"),
            "outcomes_added": learning.get("outcomes_added"),
            "lifecycle_rows": learning.get("lifecycle_rows"),
            "github_sync": learning.get("github_sync"),
            "t0_freeze_added": learning.get("t0_freeze_added"),
        }

        # --- Explicit Forecast Memory stage (durable sync via persistence layer) ---
        if not skip_forecast_memory:
            from modules.forecast_research.production_daily_integration import (
                run_forecast_memory_daily_stage,
            )

            fm = run_forecast_memory_daily_stage(
                td,
                data_dir=fm_dir,
                ems_path=ems_path,
                md_path=md_path,
                require_mdt0=True,
                mature=True,
            )
            result.forecast_memory = fm
            result.artifacts["forecast_memory"] = {
                "stage_disposition": fm.get("stage_disposition"),
                "forecast_t0": fm.get("forecast_t0"),
                "maturity": fm.get("maturity"),
                "mdrr": fm.get("mdrr"),
                "p0_market_memory": fm.get("p0_market_memory"),
            }

        result.ok = True
        result.stage_disposition = "SUCCESS"
        result.reason = "headless_eod_complete"
    except Exception as exc:
        logger.exception("headless EOD failed")
        result.ok = False
        result.stage_disposition = "FAILED"
        result.reason = f"headless_eod_error:{type(exc).__name__}:{exc}"
        result.errors.append(result.reason)

    result.completed_at = _iso()
    _write_status(root, result)
    return result.to_dict()


def _write_status(repo_root: Path, result: HeadlessEodResult) -> None:
    path = repo_root / "data" / "forecast_research" / "headless_eod_status.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("headless EOD status write failed: %s", exc)

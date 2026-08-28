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

from modules.production_stage_telemetry import emit_stage_end, emit_stage_start

logger = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_UNIVERSE = 142
HEADLESS_EOD_VERSION = "headless_eod_v1"

# Run provenance classes — autonomous FAIL evidence must stay distinct from recovery.
RUN_CLASS_AUTONOMOUS = "AUTONOMOUS"
RUN_CLASS_RECOVERY = "RECOVERY_MANUAL_REMEDIATION"

PROBE_OK = "OK"
PROBE_FAILED = "PROBE_FAILED"
PROBE_NOT_TRADING = "NOT_TRADING"

STATUS_AUTONOMOUS = "headless_eod_status.json"
STATUS_RECOVERY = "headless_eod_recovery_status.json"
STATUS_HISTORY = "headless_eod_run_history.jsonl"


@dataclass
class TradingDayProbeResult:
    """Strict separation: probe failure ≠ non-trading day."""

    trading_today: Optional[bool]
    reason: str
    probe_status: str  # OK | PROBE_FAILED | NOT_TRADING

    @property
    def probe_failed(self) -> bool:
        return self.probe_status == PROBE_FAILED


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
    trading_day_probe_status: str = ""
    run_class: str = RUN_CLASS_AUTONOMOUS
    run_identity: str = ""
    autonomy_evidence: str = "AUTONOMOUS_PRODUCTION"
    artifacts: Dict[str, Any] = field(default_factory=dict)
    market_real: Optional[float] = None
    market_live: Optional[float] = None
    market_forecast: Optional[float] = None
    forecast_memory: Dict[str, Any] = field(default_factory=dict)
    health_summary: Dict[str, Any] = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def _iso(dt: Optional[datetime] = None) -> str:
    # store UTC Z
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def is_after_close_eligible(now: Optional[datetime] = None) -> bool:
    from modules.market_t0_capture import is_canonical_eligible

    return bool(is_canonical_eligible(now or vn_now()))


def resolve_trading_today(trade_date: str) -> TradingDayProbeResult:
    """
    Mirror app.py is_vnindex_trading_today without Streamlit.

    Probe/dependency failures return probe_status=PROBE_FAILED — never
    silently classified as a non-trading day.
    """
    today = str(trade_date)[:10]
    try:
        from vnstock import stock_historical_data
    except Exception as exc:
        logger.warning("trading_today probe failed (import): %s", exc)
        return TradingDayProbeResult(
            trading_today=None,
            reason=f"TRADING_DAY_PROBE_FAILED:import:{type(exc).__name__}:{exc}",
            probe_status=PROBE_FAILED,
        )

    last_error: Optional[str] = None
    try:
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
            except Exception as exc:
                last_error = f"{type(exc).__name__}:{exc}"
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
                return TradingDayProbeResult(
                    trading_today=True,
                    reason=f"VNINDEX có giao dịch hôm nay: {today}",
                    probe_status=PROBE_OK,
                )
            return TradingDayProbeResult(
                trading_today=False,
                reason=f"VNINDEX phiên mới nhất {last_date} (không phải {today})",
                probe_status=PROBE_NOT_TRADING,
            )
    except Exception as exc:
        logger.warning("trading_today probe failed: %s", exc)
        return TradingDayProbeResult(
            trading_today=None,
            reason=f"TRADING_DAY_PROBE_FAILED:{type(exc).__name__}:{exc}",
            probe_status=PROBE_FAILED,
        )

    detail = last_error or "no_vnindex_bars"
    return TradingDayProbeResult(
        trading_today=None,
        reason=f"TRADING_DAY_PROBE_FAILED:unavailable:{detail}",
        probe_status=PROBE_FAILED,
    )


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

        # Headless EOD: Vietnam D1 via vnstock only — Yahoo is never primary.
        out = run_scan(
            list(symbols) if symbols is not None else list(WATCHLIST),
            eod_mode=True,
        )
    if out is None or out.empty:
        return pd.DataFrame()
    try:
        from modules.evolution_health import add_evolution_health

        out = add_evolution_health(out)
    except Exception as exc:
        logger.warning("add_evolution_health failed safely: %s", exc)
    return out


def build_eod_health_summary(
    *,
    trade_date: str,
    source_rows: int,
    expected_universe: int,
    artifacts: Dict[str, Any],
    forecast_memory: Dict[str, Any],
    stage_disposition: str,
    run_class: str,
) -> Dict[str, Any]:
    """Explicit operator-facing health line for logs/status."""
    ems_ok = bool((artifacts.get("ems") or {}).get("ok"))
    mdt0_ok = bool((artifacts.get("mdt0") or {}).get("ok")) and (
        (artifacts.get("mdt0") or {}).get("canonical_added") in (0, 1, None)
        or (artifacts.get("mdt0") or {}).get("daily_snapshot_id")
    )
    # Prefer explicit FM freeze result when present.
    ft0 = (forecast_memory or {}).get("forecast_t0") or (artifacts.get("forecast_memory") or {}).get(
        "forecast_t0"
    ) or {}
    fc_ok = bool(ft0.get("ok")) or str(ft0.get("reason") or "") == "ALREADY_FROZEN"
    el = artifacts.get("earning_learning") or {}
    el_ok = bool(el.get("ok", False)) and int(el.get("observations_added") or 0) >= 0
    sync = el.get("github_sync") or (forecast_memory or {}).get("reason") or ""
    auto = "N/A"
    if run_class == RUN_CLASS_AUTONOMOUS:
        auto = "PASS" if stage_disposition == "SUCCESS" and source_rows >= expected_universe else "FAIL"
    elif run_class == RUN_CLASS_RECOVERY:
        auto = "RECOVERY_NOT_AUTO"
    line = (
        f"EOD {source_rows}/{expected_universe} | "
        f"MDT0 {'OK' if mdt0_ok else 'NO'} | "
        f"FC {'OK' if fc_ok else 'NO'} | "
        f"EL {'OK' if el_ok else 'NO'} | "
        f"SYNC {sync or 'UNKNOWN'} | "
        f"AUTO {auto}"
    )
    return {
        "trade_date": trade_date,
        "eod_rows": source_rows,
        "expected_universe": expected_universe,
        "ems_ok": ems_ok,
        "mdt0_ok": bool(mdt0_ok),
        "forecast_t0_ok": fc_ok,
        "earning_learning_ok": el_ok,
        "sync": sync,
        "auto_verdict": auto,
        "line": line,
    }


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
    run_class: str = RUN_CLASS_AUTONOMOUS,
    preserve_autonomy_status: bool = False,
) -> Dict[str, Any]:
    """
    Produce canonical EOD artifacts without Streamlit.

    Order: board → EMS → MDT0 (+FM hook) → update_learning → explicit FM stage.
    Idempotent for the same trade_date (first-write-wins downstream).

    run_class=RECOVERY_MANUAL_REMEDIATION writes a separate status file and never
    overwrites autonomous FAIL evidence in headless_eod_status.json.
    """
    root = Path(repo_root) if repo_root else REPO_ROOT
    td = str(trade_date)[:10]
    now = now or vn_now()
    started = _iso()
    is_recovery = run_class == RUN_CLASS_RECOVERY or preserve_autonomy_status
    effective_class = RUN_CLASS_RECOVERY if is_recovery else RUN_CLASS_AUTONOMOUS
    run_identity = (
        f"{effective_class}:{td}:{started}"
    )
    result = HeadlessEodResult(
        ok=False,
        trade_date=td,
        started_at=started,
        run_class=effective_class,
        run_identity=run_identity,
        autonomy_evidence=(
            "RECOVERY_NOT_AUTONOMOUS_EVIDENCE"
            if is_recovery
            else "AUTONOMOUS_PRODUCTION"
        ),
    )
    ems_path = root / "data" / "earning_money_snapshots.csv"
    el_dir = root / "data" / "earning_learning"
    fm_dir = root / "data" / "forecast_research"
    md_path = el_dir / "market_daily_t0.csv"

    # Recovery: write STARTED checkpoint immediately so SSH drops still leave provenance.
    if is_recovery:
        result.stage_disposition = "RECOVERY_STARTED"
        result.reason = "recovery_checkpoint_started"
        result.completed_at = ""
        _persist_status(root, result, is_recovery=True)

    ok_attempt, attempt_reason = should_attempt_headless_eod(
        td, now=now, allow_before_close_for_tests=allow_before_close_for_tests
    )
    result.after_close_eligible = is_after_close_eligible(now) or allow_before_close_for_tests
    if not ok_attempt:
        result.stage_disposition = "WAITING_FOR_DATA"
        result.reason = attempt_reason
        result.completed_at = _iso()
        _persist_status(root, result, is_recovery=is_recovery)
        return result.to_dict()

    probe: Optional[TradingDayProbeResult] = None
    if trading_today is None:
        probe = resolve_trading_today(td)
        trading_today = bool(probe.trading_today) if probe.trading_today is not None else False
        trading_reason = probe.reason
        result.trading_day_probe_status = probe.probe_status
    else:
        result.trading_day_probe_status = PROBE_OK if trading_today else PROBE_NOT_TRADING
        trading_reason = trading_reason or (
            "injected_trading_today" if trading_today else "injected_non_trading"
        )

    result.trading_today = bool(trading_today)

    if probe is not None and probe.probe_failed and not allow_before_close_for_tests:
        # Loud failure — never pretend this is a non-trading day.
        result.stage_disposition = "TRADING_DAY_PROBE_FAILED"
        result.reason = probe.reason
        result.ok = False
        result.errors.append(probe.reason)
        result.completed_at = _iso()
        _persist_status(root, result, is_recovery=is_recovery)
        return result.to_dict()

    if not trading_today and not allow_before_close_for_tests:
        result.stage_disposition = "SKIPPED_NON_TRADING_DAY"
        result.reason = trading_reason or "not_trading_today"
        result.ok = True
        result.completed_at = _iso()
        _persist_status(root, result, is_recovery=is_recovery)
        return result.to_dict()

    try:
        t_scan = emit_stage_start("headless_scan", trade_date=td)
        board = build_eod_scan_df(scan_df=scan_df)
        # Stamp trade_date so EL adaptation does not fall back to calendar today.
        if not board.empty and "trade_date" not in board.columns:
            board = board.copy()
            board["trade_date"] = td
        result.source_rows = int(len(board))
        result.universe_ok = result.source_rows >= expected_universe
        if board.empty:
            emit_stage_end(
                "headless_scan",
                started_monotonic=t_scan,
                disposition="EMPTY",
                source_rows=0,
            )
            result.stage_disposition = "WAITING_FOR_DATA"
            result.reason = "empty_scan_board"
            result.completed_at = _iso()
            _persist_status(root, result, is_recovery=is_recovery)
            return result.to_dict()
        if not result.universe_ok:
            emit_stage_end(
                "headless_scan",
                started_monotonic=t_scan,
                disposition="INCOMPLETE",
                source_rows=result.source_rows,
            )
            result.stage_disposition = "WAITING_FOR_DATA"
            result.reason = f"incomplete_universe:{result.source_rows}/{expected_universe}"
            result.errors.append(result.reason)
            # Fail closed: do not write partial EMS/MDT0 as canonical EOD.
            result.completed_at = _iso()
            _persist_status(root, result, is_recovery=is_recovery)
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
        emit_stage_end(
            "headless_scan",
            started_monotonic=t_scan,
            disposition="OK" if result.universe_ok else "INCOMPLETE",
            source_rows=result.source_rows,
        )

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
        if is_recovery:
            result.stage_disposition = "RECOVERY_EMS_WRITTEN"
            result.reason = "recovery_checkpoint_ems"
            _persist_status(root, result, is_recovery=True)

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
            trading_reason=trading_reason or f"headless_eod:{td}:{effective_class}",
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
        if is_recovery:
            result.stage_disposition = "RECOVERY_MDT0_WRITTEN"
            result.reason = "recovery_checkpoint_mdt0"
            _persist_status(root, result, is_recovery=True)

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

            t_fm = emit_stage_start("forecast_memory", trade_date=td)
            fm = run_forecast_memory_daily_stage(
                td,
                data_dir=fm_dir,
                ems_path=ems_path,
                md_path=md_path,
                require_mdt0=True,
                mature=True,
            )
            emit_stage_end(
                "forecast_memory",
                started_monotonic=t_fm,
                disposition=str(fm.get("stage_disposition") or "UNKNOWN"),
                reason=fm.get("reason"),
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
        result.reason = (
            "headless_eod_recovery_complete"
            if is_recovery
            else "headless_eod_complete"
        )
        result.health_summary = build_eod_health_summary(
            trade_date=td,
            source_rows=result.source_rows,
            expected_universe=expected_universe,
            artifacts=result.artifacts,
            forecast_memory=result.forecast_memory,
            stage_disposition=result.stage_disposition,
            run_class=effective_class,
        )
        logger.info("headless_eod_health %s", result.health_summary.get("line"))
        print(f"[headless_eod] {result.health_summary.get('line')}", flush=True)
    except Exception as exc:
        logger.exception("headless EOD failed")
        result.ok = False
        result.stage_disposition = "FAILED"
        result.reason = f"headless_eod_error:{type(exc).__name__}:{exc}"
        result.errors.append(result.reason)

    result.completed_at = _iso()
    _persist_status(root, result, is_recovery=is_recovery)
    return result.to_dict()


def _persist_status(
    repo_root: Path,
    result: HeadlessEodResult,
    *,
    is_recovery: bool,
) -> None:
    """
    Always append immutable history.

    Autonomous runs update headless_eod_status.json.
    Recovery runs update headless_eod_recovery_status.json + dated recovery
    snapshot — never overwrite autonomous FAIL evidence.
    """
    fm = repo_root / "data" / "forecast_research"
    try:
        fm.mkdir(parents=True, exist_ok=True)
        payload = result.to_dict()
        history = fm / STATUS_HISTORY
        with history.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

        if is_recovery:
            (fm / STATUS_RECOVERY).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            recovery_dir = fm / "recovery_runs"
            recovery_dir.mkdir(parents=True, exist_ok=True)
            stamp = (result.started_at or _iso()).replace(":", "").replace("+", "")
            snap = recovery_dir / f"RECOVERY_{result.trade_date}_{stamp}.json"
            snap.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        else:
            (fm / STATUS_AUTONOMOUS).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("headless EOD status write failed: %s", exc)

"""Headless close scan for canonical Market T0 and SweetSpot.

This does not import ``app.py`` (that script executes the Streamlit page).
It loads the existing production function definitions out of ``app.py`` and
runs those same objects. There is no second scoring formula.

Provenance, same as the cash-session page:

- Watchlist: the ``WATCHLIST`` constant in ``app.py``.
- Daily bars: ``vnstock.stock_historical_data`` inside ``download_symbol_data``.
  That call has no API-key argument (vnstock 0.2.9.2).
- Live bar: ``yfinance`` 15-minute download inside ``fetch_live_price``.
  After 15:00, ``inject_live_into_daily`` keeps the daily close when live is
  within the existing tolerance (``D1_FINAL``).
- Symbol row: ``analyze_symbol`` / ``run_scan``.
- Health columns: ``modules.evolution_health.add_evolution_health``.
- Market scalars: ``calc_market_real``, ``calc_market_live``,
  ``calc_market_forecast``, ``market_status_text``,
  ``build_rsi_breadth_report``, ``elite_regime``.
- Session date: the Vietnam calendar date of the job clock. The intraday
  handoff is not an input.

``capture_market_t0_snapshot`` still fetches optional VNINDEX OHLCV itself.
"""

from __future__ import annotations

import ast
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from modules.evolution_health import add_evolution_health
from modules.intraday_execution_boundary import VN_TZ, as_vn

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

_SEEDS = (
    "WATCHLIST",
    "YAHOO_SUFFIX",
    "GROUP_ORDER",
    "GROUP_RANK",
    "VN_TZ",
    "TEXT_GUARD_COLS",
    "NUMERIC_GUARD_COLS",
    "to_float",
    "is_valid_price",
    "safe_max_number",
    "safe_min_number",
    "safe_round",
    "ema",
    "sma",
    "calc_rsi",
    "calc_obv",
    "slope_state_text",
    "vn_now",
    "today_str",
    "vn_time_str",
    "ensure_object_columns",
    "ensure_numeric_columns",
    "guard_dataframe_dtypes",
    "log_runtime_error",
    "download_symbol_data",
    "fetch_live_price",
    "inject_live_into_daily",
    "build_indicators",
    "calc_price_score",
    "calc_rsi_score",
    "calc_obv_score",
    "calc_slope_score",
    "calc_rs_score",
    "calc_volume_score",
    "classify_pull_label",
    "build_warning",
    "build_status",
    "classify_group",
    "analyze_symbol",
    "run_scan",
    "calc_market_real",
    "calc_market_live",
    "calc_market_forecast",
    "market_status_text",
    "build_rsi_breadth_report",
    "_FORECAST_ENGINE",
    "is_vnindex_trading_today",
    "elite_regime",
)


class _ProgressBar:
    def progress(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def empty(self) -> None:
        return None


class _StreamlitStub:
    """Enough of Streamlit for cache decorators and the scan progress bar."""

    def cache_data(self, *_args: Any, **_kwargs: Any) -> Callable:
        def decorator(fn: Callable) -> Callable:
            return fn

        return decorator

    def progress(self, *_args: Any, **_kwargs: Any) -> _ProgressBar:
        return _ProgressBar()


def _assigned_name(stmt: ast.AST) -> Optional[str]:
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if isinstance(target, ast.Name):
        return target.id
    return None


def _collect(tree: ast.AST) -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for stmt in tree.body:  # type: ignore[attr-defined]
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[stmt.name] = stmt
        else:
            name = _assigned_name(stmt)
            if name:
                found[name] = stmt
    return found


def _referenced_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


_PURE_CALLS = {"ZoneInfo", "ForecastEngine", "sorted", "list", "set", "tuple", "dict", "frozenset"}


def _is_pure(node: Optional[ast.AST]) -> bool:
    """True for module constants. Page-level calls such as scan_df = ... are not."""
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_pure(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (key is None or _is_pure(key)) and _is_pure(value)
            for key, value in zip(node.keys, node.values)
        )
    if isinstance(node, (ast.BinOp, ast.BoolOp)):
        values = node.values if isinstance(node, ast.BoolOp) else (node.left, node.right)
        return all(_is_pure(value) for value in values)
    if isinstance(node, ast.UnaryOp):
        return _is_pure(node.operand)
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _PURE_CALLS:
        return all(_is_pure(arg) for arg in node.args) and not node.keywords
    return False


def _includable(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return True
    if isinstance(node, ast.Assign):
        return _is_pure(node.value)
    return False


def load_production_scan_api() -> dict[str, Any]:
    """Execute the production scan definitions without running the Streamlit page."""
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = _collect(tree)
    needed = set(_SEEDS)
    changed = True
    while changed:
        changed = False
        for name in list(needed):
            node = found.get(name)
            if node is None:
                continue
            if not _includable(node):
                continue
            for ref in _referenced_names(node):
                if ref in found and ref not in needed and _includable(found[ref]):
                    needed.add(ref)
                    changed = True

    ordered = sorted(
        (found[name] for name in needed if name in found and _includable(found[name])),
        key=lambda node: node.lineno,
    )
    module = ast.Module(body=ordered, type_ignores=[])
    ast.fix_missing_locations(module)
    try:
        import yfinance as yf
    except Exception:
        yf = None
    from forecast_engine import ForecastEngine

    namespace: dict[str, Any] = {
        "np": np,
        "pd": pd,
        "os": os,
        "time": time,
        "datetime": datetime,
        "timedelta": timedelta,
        "ZoneInfo": ZoneInfo,
        "st": _StreamlitStub(),
        "yf": yf,
        "ForecastEngine": ForecastEngine,
        "__name__": "close_session_scan_api",
    }
    exec(compile(module, str(APP_PATH), "exec"), namespace)  # noqa: S102 — production defs, not a second copy
    namespace["__source_path__"] = str(APP_PATH)
    return namespace


def _learning_breadth(report: Any) -> Optional[float]:
    if not isinstance(report, dict):
        return None
    score = report.get("score")
    try:
        if score is not None and pd.notna(score):
            return float(score)
    except (TypeError, ValueError):
        return None
    return None


def build_close_scan_inputs(
    *,
    now: Optional[datetime] = None,
    symbols: Optional[list[str]] = None,
    api: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build the close-scan payload. Does not read a session handoff."""
    local_now = as_vn(now or datetime.now(VN_TZ))
    trade_date = local_now.strftime("%Y-%m-%d")
    try:
        production = api or load_production_scan_api()
        universe = list(symbols) if symbols is not None else list(production["WATCHLIST"])
        scan_df = production["run_scan"](universe)
        if not isinstance(scan_df, pd.DataFrame) or scan_df.empty:
            return {
                "ok": False,
                "status": "CLOSE_SCAN_EMPTY",
                "trade_date": trade_date,
                "scan_df": scan_df if isinstance(scan_df, pd.DataFrame) else pd.DataFrame(),
            }
        scan_df = add_evolution_health(scan_df)
        market_real = production["calc_market_real"](scan_df)
        market_live = production["calc_market_live"](scan_df)
        forecast = production["calc_market_forecast"](scan_df)
        market_status, market_action = production["market_status_text"](market_real)
        trading_today, trading_reason = production["is_vnindex_trading_today"]()
        regime_name, _weights, regime_note = production["elite_regime"](
            market_real,
            forecast.score,
        )
        breadth_report = production["build_rsi_breadth_report"](scan_df)
    except Exception as exc:
        return {
            "ok": False,
            "status": "CLOSE_SCAN_FAILED",
            "trade_date": trade_date,
            "error": f"{type(exc).__name__}: {exc}",
            "scan_df": pd.DataFrame(),
        }
    return {
        "ok": True,
        "status": "READY",
        "trade_date": trade_date,
        "scan_df": scan_df,
        "market_real": market_real,
        "market_live": market_live,
        "market_forecast": forecast.score,
        "market_forecast_text": forecast.text,
        "market_confidence": forecast.confidence,
        "market_status": market_status,
        "market_action": market_action,
        "market_regime": regime_name,
        "market_regime_note": regime_note,
        "rsi_breadth_report": breadth_report,
        "breadth": _learning_breadth(breadth_report),
        "trading_today": bool(trading_today),
        "trading_reason": str(trading_reason or ""),
        "source": "close_scan",
    }

"""Session-D handoff captured during the research lock.

Stage 1 serializes frames the cash-session run already computed. It does not
scan, score, learn, mature, or freeze forward ledgers. The stored
``captured_at`` is the actual Vietnam clock of that run.

A handoff is valid only when the schema matches, the path date equals
``trade_date``, and ``captured_at`` falls on that date inside the weekday
research lock (09:15 inclusive through 15:10 exclusive). Anything else is
not a handoff — callers report ``NO_VALID_HANDOFF`` and do not rebuild it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd

from modules.earning_learning import GitHubLocalStorage, _load_github_config
from modules.intraday_execution_boundary import VN_TZ, as_vn, research_below_boundary_locked

SCHEMA_VERSION = "session_handoff_v1"
HANDOFF_DIR = Path("data") / "session_handoff"
REMOTE_DIR = "data/session_handoff"

FRAME_KEYS = (
    "buy_elite",
    "learning_board",
    "recommendations",
    "leader_brain",
    "pattern_library",
    "leader_session_snapshot",
)

MARKET_KEYS = (
    "market_real",
    "market_live",
    "market_forecast",
    "market_forecast_text",
    "market_confidence",
    "breadth",
    "market_status",
    "market_action",
    "market_regime",
    "market_regime_note",
)


def _storage(local_dir: Optional[Path] = None) -> GitHubLocalStorage:
    directory = Path(local_dir) if local_dir is not None else HANDOFF_DIR
    return GitHubLocalStorage(directory, _load_github_config(REMOTE_DIR))


def _json_number(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return number


def _frame_csv(frame: Optional[pd.DataFrame]) -> str:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return ""
    return frame.to_csv(index=False)


def _read_frame(text: Any) -> pd.DataFrame:
    if not isinstance(text, str) or not text.strip():
        return pd.DataFrame()
    from io import StringIO

    return pd.read_csv(StringIO(text))


def _storm_score_view(storm_score_frame: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Use the retained Storm frame. Never recompute scores."""
    if (
        storm_score_frame is None
        or not isinstance(storm_score_frame, pd.DataFrame)
        or storm_score_frame.empty
        or "symbol" not in storm_score_frame.columns
        or "storm_score" not in storm_score_frame.columns
    ):
        return pd.DataFrame(columns=["symbol", "storm_score"])
    scores = storm_score_frame[["symbol", "storm_score"]].copy()
    scores["symbol"] = scores["symbol"].astype(str).str.upper()
    return scores.drop_duplicates(subset=["symbol"], keep="last").reset_index(drop=True)


def _session_history(history: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if history is None or history.empty or "session_date" not in history.columns:
        return pd.DataFrame() if history is None else history.iloc[0:0].copy()
    dates = history["session_date"].astype(str).str.slice(0, 10)
    return history.loc[dates == trade_date].reset_index(drop=True)


def _captured_at_text(now: datetime) -> str:
    local = as_vn(now).replace(microsecond=0)
    return local.isoformat()


def parse_captured_at(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return as_vn(parsed)


def validate_handoff(payload: Any, *, path_trade_date: str) -> tuple[bool, str]:
    """Return whether this object is the session-D handoff for ``path_trade_date``."""
    if not isinstance(payload, dict):
        return False, "bad_schema"
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "bad_schema"
    trade_date = str(payload.get("trade_date") or "").strip()
    path_trade_date = str(path_trade_date or "").strip()
    if not trade_date or trade_date != path_trade_date:
        return False, "trade_date_mismatch"
    captured = parse_captured_at(payload.get("captured_at"))
    if captured is None:
        return False, "bad_captured_at"
    if captured.strftime("%Y-%m-%d") != trade_date:
        return False, "captured_at_date_mismatch"
    if not research_below_boundary_locked(captured):
        return False, "captured_at_outside_lock"
    frames = payload.get("frames")
    if not isinstance(frames, dict):
        return False, "bad_schema"
    if any(key not in frames for key in FRAME_KEYS):
        return False, "bad_schema"
    market = payload.get("market")
    if not isinstance(market, dict):
        return False, "bad_schema"
    return True, "ok"


def _decode(text: Optional[str]) -> Optional[dict]:
    if text is None or not str(text).strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def load_handoff_payload(
    trade_date: str,
    *,
    storage: Optional[GitHubLocalStorage] = None,
) -> Optional[dict]:
    store = storage or _storage()
    result = store.read_text(f"{trade_date}.json")
    return _decode(result.text)


def load_valid_handoff(
    trade_date: str,
    *,
    storage: Optional[GitHubLocalStorage] = None,
) -> Optional[dict]:
    payload = load_handoff_payload(trade_date, storage=storage)
    ok, _reason = validate_handoff(payload, path_trade_date=trade_date)
    if not ok:
        return None
    return payload


def frames_as_dataframes(payload: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    frames = payload.get("frames") if isinstance(payload, Mapping) else {}
    if not isinstance(frames, dict):
        frames = {}
    return {key: _read_frame(frames.get(key)) for key in FRAME_KEYS}


def capture_session_handoff(
    *,
    trade_date: str,
    trading_today: bool,
    trading_reason: str,
    market: Mapping[str, Any],
    buy_elite_df: Optional[pd.DataFrame],
    learning_board: Optional[pd.DataFrame],
    recommendations: Optional[pd.DataFrame],
    leader_brain: Optional[pd.DataFrame],
    pattern_library: Optional[pd.DataFrame],
    leader_history: Optional[pd.DataFrame],
    now: datetime,
    storage: Optional[GitHubLocalStorage] = None,
) -> dict[str, Any]:
    """Persist one keep-last handoff. A later ``captured_at`` wins.

    A failed GitHub PUT leaves the previous object in place. This function
    does not scan or call research engines.
    """
    local_now = as_vn(now)
    trade_date = str(trade_date or "").strip()
    captured_at = _captured_at_text(local_now)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "trade_date": trade_date,
        "captured_at": captured_at,
        "trading_today": bool(trading_today),
        "trading_reason": str(trading_reason or ""),
        "market": {key: _json_number(market.get(key)) if key in {
            "market_real",
            "market_live",
            "market_forecast",
            "market_confidence",
            "breadth",
        } else market.get(key, "") for key in MARKET_KEYS},
        "frames": {
            "buy_elite": _frame_csv(buy_elite_df),
            "learning_board": _frame_csv(learning_board),
            "recommendations": _frame_csv(recommendations),
            "leader_brain": _frame_csv(leader_brain),
            "pattern_library": _frame_csv(pattern_library),
            "leader_session_snapshot": _frame_csv(
                _session_history(leader_history if leader_history is not None else pd.DataFrame(), trade_date)
            ),
        },
    }
    for key in ("market_forecast_text", "market_status", "market_action", "market_regime", "market_regime_note"):
        value = manifest["market"].get(key)
        manifest["market"][key] = "" if value is None else str(value)

    ok, reason = validate_handoff(manifest, path_trade_date=trade_date)
    if not ok:
        return {"ok": False, "status": "NOT_WRITTEN", "reason": reason, "captured_at": captured_at}

    store = storage or _storage()
    filename = f"{trade_date}.json"
    existing = _decode(store.read_text(filename).text)
    existing_ok, _ = validate_handoff(existing, path_trade_date=trade_date)
    if existing_ok:
        previous = parse_captured_at(existing.get("captured_at"))
        current = parse_captured_at(captured_at)
        if previous is not None and current is not None and previous >= current:
            return {
                "ok": True,
                "status": "KEPT_NEWER",
                "captured_at": existing.get("captured_at"),
                "reason": "older_capture_ignored",
            }

    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    written = store.write_text(
        filename,
        text,
        commit_message=f"Session handoff {trade_date} captured_at {captured_at}",
    )
    status = "WRITTEN" if written.github_ok or written.local_ok else "WRITE_FAILED"
    if written.github_status not in {"GITHUB_OK", "GITHUB_DISABLED"} and written.local_ok:
        status = "LOCAL_ONLY_GITHUB_UNCHANGED"
    return {
        "ok": written.local_ok or written.github_ok,
        "status": status,
        "captured_at": captured_at,
        "github_status": written.github_status,
        "reason": written.error,
    }


def capture_locked_session_handoff(
    *,
    trade_date: str,
    trading_today: bool,
    trading_reason: str,
    market_real: Any,
    market_live: Any,
    market_forecast: Any,
    market_forecast_text: str,
    market_confidence: Any,
    breadth: Any,
    market_status: str,
    market_action: str,
    market_regime: str,
    market_regime_note: str,
    buy_elite_df: Optional[pd.DataFrame],
    scan_df: Optional[pd.DataFrame],
    storm_score_frame: Optional[pd.DataFrame],
    evo_table: Optional[pd.DataFrame],
    leader_brain: Optional[pd.DataFrame],
    now: Optional[datetime] = None,
    storage: Optional[GitHubLocalStorage] = None,
) -> dict[str, Any]:
    """Serialize the in-memory session. Called only from the locked branch.

    Storm scores come from ``storm_score_frame`` (already computed). This
    does not call ``_compute_storm_score_frame`` or ``compute_storm_scores``.
    """
    local_now = as_vn(now or datetime.now(VN_TZ))
    if not research_below_boundary_locked(local_now):
        return {
            "ok": False,
            "status": "NOT_WRITTEN",
            "reason": "not_locked",
            "captured_at": _captured_at_text(local_now),
        }
    try:
        from leader_memory import get_runtime_recommendations, load_history, load_pattern_library
        from modules.learning_t0_capture import build_learning_input_df

        learning_board = build_learning_input_df(
            scan_df if isinstance(scan_df, pd.DataFrame) else pd.DataFrame(),
            storm_scores=_storm_score_view(storm_score_frame),
            evo_table=evo_table,
            leader_brain=leader_brain if isinstance(leader_brain, pd.DataFrame) else pd.DataFrame(),
        )
        return capture_session_handoff(
            trade_date=str(trade_date),
            trading_today=bool(trading_today),
            trading_reason=str(trading_reason or ""),
            market={
                "market_real": market_real,
                "market_live": market_live,
                "market_forecast": market_forecast,
                "market_forecast_text": market_forecast_text,
                "market_confidence": market_confidence,
                "breadth": breadth,
                "market_status": market_status,
                "market_action": market_action,
                "market_regime": market_regime,
                "market_regime_note": market_regime_note,
            },
            buy_elite_df=buy_elite_df,
            learning_board=learning_board,
            recommendations=get_runtime_recommendations(),
            leader_brain=leader_brain if isinstance(leader_brain, pd.DataFrame) else pd.DataFrame(),
            pattern_library=load_pattern_library(),
            leader_history=load_history(),
            now=local_now,
            storage=storage,
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "NOT_WRITTEN",
            "reason": f"{type(exc).__name__}: {exc}",
            "captured_at": _captured_at_text(local_now),
        }

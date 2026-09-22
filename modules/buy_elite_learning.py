"""BUY ELITE learning persistence, import-safe outside Streamlit.

Selection, ``head(30)``, immutable ``first_seen``, and scoring are unchanged.
When ``session_date`` and ``observed_at`` are omitted, stamps use
``today_str()`` / ``vn_now()`` so an in-app call behaves as before.

GitHub token: Streamlit secrets, then ``GITHUB_TOKEN`` env. This module does
not change ``app.get_github_token``.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
GITHUB_REPO_OWNER = os.getenv("GITHUB_REPO_OWNER", "SONVODAI")
GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME", "scanner-ga-chien-clean")
HISTORY_FILE = "buy_elite_learning_history.csv"
PROFILE_FILE = "buy_elite_learning_profile.json"

TEXT_GUARD_COLS = {
    "date", "time", "created_at", "updated_at", "last_outcome_update",
    "symbol", "group", "regime", "learning_mode", "conclusion", "nav",
    "dna", "obv", "status", "personality", "message", "mode", "note",
    "current_thought", "source", "stage", "error", "name", "version",
}
NUMERIC_GUARD_COLS = {
    "rank", "score", "price", "entry_price", "market_real", "market_forecast",
    "winprob", "elite_score", "storm", "persistence", "evolution",
    "recent_change", "rsi", "slope", "dist_ema9", "market_score",
    "action_score", "storm_score", "evo_score", "zone_score", "penalty",
    "t1_return", "t3_return", "t5_return", "t1_win", "t3_win", "t5_win",
    "obv_value", "volume", "vol_ma20", "completed_t5", "baseline_winrate",
    "confidence", "age_days", "signals_today", "avg_winprob", "avg_elite_score",
    "high_consensus_count",
}


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def today_str() -> str:
    return vn_now().strftime("%Y-%m-%d")


def vn_time_str(fmt: str = "%d/%m/%Y %H:%M:%S") -> str:
    return vn_now().strftime(fmt)


def _as_vn(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _date_text(value) -> str:
    if isinstance(value, datetime):
        return _as_vn(value).strftime("%Y-%m-%d")
    text = str(value or "").strip()
    return text[:10]


def to_float(value, default=np.nan):
    try:
        if value is None:
            return default
        if isinstance(value, pd.DataFrame):
            if value.empty:
                return default
            value = value.iloc[-1, -1]
        if isinstance(value, pd.Series):
            if len(value) == 0:
                return default
            value = value.iloc[-1]
        if isinstance(value, np.ndarray):
            if value.size == 0:
                return default
            value = value.flatten()[-1]
        if isinstance(value, str):
            value = value.strip()
            if value in ["", "--", "nan", "NaN", "None", "N/A", "null"]:
                return default
            value = value.replace(",", "")
        out = float(value)
        if pd.isna(out) or np.isinf(out):
            return default
        return out
    except Exception:
        return default


def is_valid_price(value) -> bool:
    number = to_float(value)
    return pd.notna(number) and number > 0


def ensure_object_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].astype("object")
        out[col] = out[col].where(pd.notna(out[col]), "")
    return out


def ensure_numeric_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def guard_dataframe_dtypes(df: pd.DataFrame, text_cols=None, numeric_cols=None) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    text_cols = list(TEXT_GUARD_COLS if text_cols is None else text_cols)
    numeric_cols = list(NUMERIC_GUARD_COLS if numeric_cols is None else numeric_cols)
    existing_text = [c for c in text_cols if c in out.columns]
    existing_numeric = [c for c in numeric_cols if c in out.columns and c not in existing_text]
    if existing_text:
        out = ensure_object_columns(out, existing_text)
    if existing_numeric:
        out = ensure_numeric_columns(out, existing_numeric)
    return out


def _github_token() -> str | None:
    token = None
    try:
        import streamlit as st

        token = st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        token = None
    if token not in (None, ""):
        return str(token)
    env = os.getenv("GITHUB_TOKEN")
    if env not in (None, ""):
        return str(env).strip()
    return None


def _github_read_text(path: str) -> str | None:
    token = _github_token()
    if not token:
        return None
    try:
        import requests

        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {token}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            content = response.json().get("content", "")
            return base64.b64decode(content).decode("utf-8")
    except Exception:
        pass
    return None


def _github_write_text(path: str, text: str, message: str) -> str:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except Exception:
        pass

    token = _github_token()
    if not token:
        return "LOCAL_ONLY"

    try:
        import requests

        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {token}"}
        encoded_content = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        sha = None
        get_response = requests.get(url, headers=headers, timeout=10)
        if get_response.status_code == 200:
            sha = get_response.json().get("sha")
        payload = {"message": message, "content": encoded_content}
        if sha:
            payload["sha"] = sha
        put_response = requests.put(url, headers=headers, json=payload, timeout=15)
        if put_response.status_code in [200, 201]:
            return "GITHUB_OK"
        return f"GITHUB_FAIL_{put_response.status_code}"
    except Exception:
        return "GITHUB_ERROR"


def default_buy_elite_learning_profile() -> dict:
    return {
        "version": "BUY_ELITE_LEARNING_V3",
        "mode": "WARMUP",
        "created_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "updated_at": vn_time_str("%Y-%m-%d %H:%M:%S"),
        "completed_t5": 0,
        "baseline_winrate": None,
        "min_completed_to_learn": 80,
        "min_feature_samples": 20,
        "note": "WARMUP: chưa đủ dữ liệu, multiplier giữ gần 1.0 để không làm méo hệ thống.",
        "multipliers": {
            "market": 1.0,
            "action": 1.0,
            "storm": 1.0,
            "evo": 1.0,
            "zone": 1.0,
            "obv": 1.0,
            "rsi_penalty": 1.0,
            "dist_penalty": 1.0,
        },
        "regime_multipliers": {
            "WINTER": {},
            "NEUTRAL": {},
            "SPRING": {},
        },
        "insights": [],
    }


def read_buy_elite_learning_profile() -> dict:
    text = _github_read_text(PROFILE_FILE)
    if text is None:
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as handle:
                text = handle.read()
        except Exception:
            return default_buy_elite_learning_profile()
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            return default_buy_elite_learning_profile()
        base = default_buy_elite_learning_profile()
        base.update(obj)
        base.setdefault("multipliers", {}).update(obj.get("multipliers", {}))
        base.setdefault("regime_multipliers", {}).update(obj.get("regime_multipliers", {}))
        return base
    except Exception:
        return default_buy_elite_learning_profile()


def write_buy_elite_learning_profile(profile: dict) -> str:
    try:
        text = json.dumps(profile, ensure_ascii=False, indent=2)
    except Exception:
        text = json.dumps(default_buy_elite_learning_profile(), ensure_ascii=False, indent=2)
    return _github_write_text(
        PROFILE_FILE,
        text,
        f"Update BUY ELITE learning profile {vn_time_str('%Y-%m-%d %H:%M:%S')}",
    )


def read_buy_elite_history() -> pd.DataFrame:
    text = _github_read_text(HISTORY_FILE)
    if text is not None:
        try:
            return pd.read_csv(StringIO(text))
        except Exception:
            pass
    try:
        return guard_dataframe_dtypes(pd.read_csv(HISTORY_FILE))
    except Exception:
        return pd.DataFrame()


def write_buy_elite_history(history_df: pd.DataFrame) -> str:
    if history_df is None:
        history_df = pd.DataFrame()
    history_df = guard_dataframe_dtypes(history_df)
    try:
        text = history_df.to_csv(index=False)
    except Exception:
        text = ""
    return _github_write_text(
        HISTORY_FILE,
        text,
        f"Update BUY ELITE learning history {vn_time_str('%Y-%m-%d %H:%M:%S')}",
    )


def update_buy_elite_outcomes(
    history_df: pd.DataFrame,
    scan_df: pd.DataFrame,
    as_of=None,
    observed_at: datetime | None = None,
) -> pd.DataFrame:
    """Update T+1/T+3/T+5. Omitted ``as_of`` still means ``today_str()``."""
    if history_df is None or history_df.empty or scan_df is None or scan_df.empty:
        return history_df if history_df is not None else pd.DataFrame()

    hist = history_df.copy()
    if "date" not in hist.columns or "symbol" not in hist.columns or "entry_price" not in hist.columns:
        return hist

    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.dropna(subset=["date", "symbol"])
    if hist.empty:
        return hist

    today = _date_text(as_of) if as_of is not None else today_str()
    stamp = (
        _as_vn(observed_at).strftime("%Y-%m-%d %H:%M:%S")
        if observed_at is not None
        else vn_time_str("%Y-%m-%d %H:%M:%S")
    )
    price_col = "price" if "price" in scan_df.columns else None
    symbol_col = "symbol" if "symbol" in scan_df.columns else None
    current_prices = (
        scan_df.set_index(symbol_col)[price_col].to_dict()
        if price_col and symbol_col
        else {}
    )

    date_strs = sorted(set(hist["date"].dt.strftime("%Y-%m-%d").tolist() + [today]))
    date_pos = {d: i for i, d in enumerate(date_strs)}

    outcome_num_cols = ["t1_return", "t3_return", "t5_return", "t1_win", "t3_win", "t5_win"]
    for col in outcome_num_cols:
        if col not in hist.columns:
            hist[col] = np.nan
        hist[col] = pd.to_numeric(hist[col], errors="coerce")

    if "last_outcome_update" not in hist.columns:
        hist["last_outcome_update"] = ""
    hist["last_outcome_update"] = hist["last_outcome_update"].astype("object")
    hist["last_outcome_update"] = hist["last_outcome_update"].where(pd.notna(hist["last_outcome_update"]), "")

    for idx, row in hist.iterrows():
        symbol = str(row.get("symbol", ""))
        entry = to_float(row.get("entry_price", np.nan))
        if symbol not in current_prices or not is_valid_price(entry):
            continue
        current_price = to_float(current_prices.get(symbol, np.nan))
        if not is_valid_price(current_price):
            continue

        signal_date = row["date"].strftime("%Y-%m-%d")
        gap = date_pos.get(today, 0) - date_pos.get(signal_date, 0)
        if gap <= 0:
            continue

        ret = round((current_price / entry - 1) * 100, 2)
        for horizon in [1, 3, 5]:
            ret_col = f"t{horizon}_return"
            win_col = f"t{horizon}_win"
            if gap >= horizon and pd.isna(row.get(ret_col, np.nan)):
                hist.at[idx, ret_col] = ret
                hist.at[idx, win_col] = 1 if ret > 0 else 0
                hist.at[idx, "last_outcome_update"] = stamp

    hist["date"] = hist["date"].dt.strftime("%Y-%m-%d")
    return guard_dataframe_dtypes(hist)


def _publish_research_watchlist_snapshot(
    history_df: pd.DataFrame | None,
    observed_at: datetime | None = None,
) -> None:
    try:
        from modules.live_shadow_transport.watchlist_bus import persist_and_publish_research_watchlist

        persist_and_publish_research_watchlist(
            history_df if history_df is not None else pd.DataFrame(),
            observed_at=observed_at or vn_now(),
            publisher=_github_write_text,
        )
    except Exception:
        pass


def append_today_buy_elite_signals(
    history_df: pd.DataFrame,
    buy_elite_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    allow_save: bool = True,
    session_date: str | None = None,
    observed_at: datetime | None = None,
) -> pd.DataFrame:
    """Append today's BUY ELITE rows. Omitted session date still means ``today_str()``."""
    moment = _as_vn(observed_at) if observed_at is not None else vn_now()
    if not allow_save or buy_elite_df is None or buy_elite_df.empty:
        _publish_research_watchlist_snapshot(history_df, observed_at=moment)
        return history_df if history_df is not None else pd.DataFrame()

    today = _date_text(session_date) if session_date else today_str()
    now_time = moment.strftime("%H:%M:%S")
    rows = []

    for _, row in buy_elite_df.head(30).iterrows():
        rows.append({
            "date": today,
            "time": now_time,
            "symbol": row.get("MÃ", ""),
            "entry_price": row.get("GIÁ", np.nan),
            "market_real": market_real,
            "market_forecast": market_forecast,
            "regime": row.get("REGIME", ""),
            "learning_mode": row.get("LearningMode", ""),
            "conclusion": row.get("KẾT LUẬN", ""),
            "winprob": row.get("WinProb", np.nan),
            "elite_score": row.get("EliteScore", np.nan),
            "consensus": row.get("ĐỒNG THUẬN", ""),
            "nav": row.get("NAV ELITE", ""),
            "group": row.get("NHÓM", ""),
            "storm": row.get("Storm", np.nan),
            "persistence": row.get("Persistence", np.nan),
            "dna": row.get("DNA", ""),
            "evolution": row.get("evolution", np.nan),
            "recent_change": row.get("recent_change", np.nan),
            "rsi": row.get("RSI", np.nan),
            "slope": row.get("SLOPE", np.nan),
            "dist_ema9": row.get("DIST EMA9%", np.nan),
            "obv": row.get("OBV", ""),
            "market_score": row.get("MarketScore", np.nan),
            "action_score": row.get("ActionScore", np.nan),
            "storm_score": row.get("StormScore", np.nan),
            "evo_score": row.get("EvoScore", np.nan),
            "zone_score": row.get("ZoneScore", np.nan),
            "penalty": row.get("Penalty", np.nan),
            "t1_return": np.nan,
            "t3_return": np.nan,
            "t5_return": np.nan,
            "t1_win": np.nan,
            "t3_win": np.nan,
            "t5_win": np.nan,
            "last_outcome_update": "",
        })

    new_df = guard_dataframe_dtypes(pd.DataFrame(rows))
    if new_df.empty:
        _publish_research_watchlist_snapshot(history_df, observed_at=moment)
        return history_df if history_df is not None else pd.DataFrame()

    history_df = guard_dataframe_dtypes(history_df) if history_df is not None else pd.DataFrame()
    try:
        from modules.live_candidate.persist import apply_immutable_first_seen
        from modules.live_shadow_transport.watchlist_bus import persist_and_publish_research_watchlist

        hist = apply_immutable_first_seen(history_df, new_df, observed_at=moment)
        persist_and_publish_research_watchlist(
            hist,
            observed_at=moment,
            publisher=_github_write_text,
        )
    except Exception:
        if history_df.empty:
            hist = new_df
        else:
            hist = pd.concat([history_df, new_df], ignore_index=True)
        hist = hist.drop_duplicates(subset=["date", "symbol"], keep="last")

    hist = guard_dataframe_dtypes(hist)
    return hist


def _feature_multiplier(completed: pd.DataFrame, mask: pd.Series, baseline: float, min_n: int, kind: str = "good") -> tuple[float, str | None]:
    sub = completed[mask.fillna(False)].copy()
    n = len(sub)
    if n < min_n or baseline is None or pd.isna(baseline):
        return 1.0, None

    wr = to_float(sub["t5_win"].mean(), np.nan)
    if pd.isna(wr):
        return 1.0, None

    if kind == "good":
        adj = np.clip((wr - baseline) * 0.45, -0.12, 0.12)
        mult = 1.0 + adj
    else:
        adj = np.clip((baseline - wr) * 0.65, -0.18, 0.25)
        mult = 1.0 + adj

    insight = f"{kind}: n={n}, winrate={round(wr*100,1)}%, baseline={round(baseline*100,1)}%, mult={round(mult,3)}"
    return round(float(np.clip(mult, 0.80, 1.25)), 3), insight


def build_buy_elite_learning_profile(history_df: pd.DataFrame, old_profile: dict | None = None) -> dict:
    old_profile = old_profile if isinstance(old_profile, dict) else default_buy_elite_learning_profile()
    profile = default_buy_elite_learning_profile()
    profile["created_at"] = old_profile.get("created_at", profile["created_at"])
    profile["updated_at"] = vn_time_str("%Y-%m-%d %H:%M:%S")

    if history_df is None or history_df.empty or "t5_win" not in history_df.columns:
        profile["note"] = "Chưa có lịch sử BUY ELITE. V3 đang WARMUP, chưa tự chỉnh trọng số."
        return profile

    hist = history_df.copy()
    hist["t5_win"] = pd.to_numeric(hist["t5_win"], errors="coerce")
    hist["t5_return"] = pd.to_numeric(hist.get("t5_return", np.nan), errors="coerce")
    completed = hist.dropna(subset=["t5_win", "t5_return"]).copy()
    completed_count = len(completed)
    profile["completed_t5"] = int(completed_count)

    min_completed = int(profile.get("min_completed_to_learn", 80))
    min_feature_samples = int(profile.get("min_feature_samples", 20))

    if completed_count == 0:
        profile["note"] = "Đã ghi tín hiệu nhưng chưa có mã nào đủ T+5 để học."
        return profile

    baseline = to_float(completed["t5_win"].mean(), np.nan)
    avg_ret = to_float(completed["t5_return"].mean(), np.nan)
    profile["baseline_winrate"] = round(float(baseline), 4) if pd.notna(baseline) else None
    profile["avg_t5_return"] = round(float(avg_ret), 3) if pd.notna(avg_ret) else None

    if completed_count < min_completed:
        profile["mode"] = "WARMUP"
        profile["note"] = f"Đã có {completed_count}/{min_completed} mẫu T+5. Chưa tự chỉnh trọng số, chỉ ghi nhớ và thống kê."
        profile["insights"] = [
            f"Completed T+5: {completed_count}/{min_completed}",
            f"Baseline WinRate: {round(baseline*100,1)}%" if pd.notna(baseline) else "Baseline WinRate: chưa đủ",
            f"Average T+5: {round(avg_ret,2)}%" if pd.notna(avg_ret) else "Average T+5: chưa đủ",
        ]
        return profile

    profile["mode"] = "ACTIVE_LEARNING"
    profile["note"] = "Đủ dữ liệu tối thiểu. Learning Engine đã bắt đầu tự chỉnh trọng số rất chậm."

    completed["storm_num"] = pd.to_numeric(completed.get("storm", np.nan), errors="coerce")
    completed["persistence_num"] = pd.to_numeric(completed.get("persistence", np.nan), errors="coerce")
    completed["evolution_num"] = pd.to_numeric(completed.get("evolution", np.nan), errors="coerce")
    completed["recent_change_num"] = pd.to_numeric(completed.get("recent_change", np.nan), errors="coerce")
    completed["rsi_num"] = pd.to_numeric(completed.get("rsi", np.nan), errors="coerce")
    completed["dist_num"] = pd.to_numeric(completed.get("dist_ema9", np.nan), errors="coerce")
    completed["market_real_num"] = pd.to_numeric(completed.get("market_real", np.nan), errors="coerce")
    completed["action_score_num"] = pd.to_numeric(completed.get("action_score", np.nan), errors="coerce")
    completed["zone_score_num"] = pd.to_numeric(completed.get("zone_score", np.nan), errors="coerce")

    obv_series = completed["obv"].astype(str) if "obv" in completed.columns else pd.Series("", index=completed.index)
    features = {
        "market": (completed["market_real_num"] >= 6, "good"),
        "action": (completed["action_score_num"] > 0, "good"),
        "storm": (completed["storm_num"].notna(), "good"),
        "evo": ((completed["persistence_num"] >= 3.5) | (completed["evolution_num"] > 0) | (completed["recent_change_num"] > 0), "good"),
        "zone": (completed["zone_score_num"] > 0, "good"),
        "obv": (obv_series.str.contains("🟢", na=False), "good"),
        "rsi_penalty": (completed["rsi_num"] > 72, "risk"),
        "dist_penalty": (completed["dist_num"] > 3.5, "risk"),
    }

    insights = [
        f"Completed T+5: {completed_count}",
        f"Baseline WinRate: {round(baseline*100,1)}%",
        f"Average T+5: {round(avg_ret,2)}%" if pd.notna(avg_ret) else "Average T+5: chưa đủ",
    ]

    new_mult = {}
    for name, (mask, kind) in features.items():
        mult, insight = _feature_multiplier(completed, mask, baseline, min_feature_samples, kind=kind)
        old_mult = to_float(old_profile.get("multipliers", {}).get(name, 1.0), 1.0)
        blended = round(float(np.clip(old_mult * 0.80 + mult * 0.20, 0.85, 1.15)), 3)
        new_mult[name] = blended
        if insight:
            insights.append(f"{name}: {insight}, blended={blended}")

    profile["multipliers"].update(new_mult)

    regime_mults = {"WINTER": {}, "NEUTRAL": {}, "SPRING": {}}
    for regime_key in regime_mults.keys():
        if "regime" not in completed.columns:
            continue
        if regime_key == "WINTER":
            sub = completed[completed["regime"].astype(str).str.contains("ĐÔNG|WINTER", regex=True, na=False)]
        elif regime_key == "NEUTRAL":
            sub = completed[completed["regime"].astype(str).str.contains("TRUNG|NEUTRAL", regex=True, na=False)]
        else:
            sub = completed[completed["regime"].astype(str).str.contains("XUÂN|SPRING", regex=True, na=False)]
        if len(sub) < max(40, min_feature_samples):
            continue
        sub_baseline = to_float(sub["t5_win"].mean(), np.nan)
        if pd.notna(sub_baseline) and pd.notna(baseline):
            seasonal = round(float(np.clip(1.0 + (sub_baseline - baseline) * 0.25, 0.90, 1.10)), 3)
            regime_mults[regime_key] = {"action": seasonal, "storm": seasonal, "zone": round(float(np.clip(2 - seasonal, 0.90, 1.10)), 3)}
            insights.append(f"Regime {regime_key}: n={len(sub)}, winrate={round(sub_baseline*100,1)}%, seasonal={seasonal}")

    profile["regime_multipliers"] = regime_mults
    profile["insights"] = insights[-20:]
    return profile


def run_buy_elite_learning_cycle(
    buy_elite_df: pd.DataFrame,
    scan_df: pd.DataFrame,
    market_real: float,
    market_forecast: float,
    trading_today: bool,
    session_date: str | None = None,
    observed_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict, str, str]:
    """Read history, update outcomes, learn the profile, append this session's signals."""
    history = read_buy_elite_history()
    old_profile = read_buy_elite_learning_profile()

    history = update_buy_elite_outcomes(
        history,
        scan_df,
        as_of=session_date,
        observed_at=observed_at,
    )
    profile = build_buy_elite_learning_profile(history, old_profile=old_profile)
    profile_status = write_buy_elite_learning_profile(profile)

    history = append_today_buy_elite_signals(
        history,
        buy_elite_df,
        market_real,
        market_forecast,
        allow_save=trading_today,
        session_date=session_date,
        observed_at=observed_at,
    )
    if history is not None and not history.empty and "date" in history.columns:
        tmp = history.copy()
        tmp["date_dt"] = pd.to_datetime(tmp["date"], errors="coerce")
        keep_dates = sorted(tmp["date_dt"].dropna().dt.strftime("%Y-%m-%d").unique())[-260:]
        tmp["date_str"] = tmp["date_dt"].dt.strftime("%Y-%m-%d")
        history = tmp[tmp["date_str"].isin(keep_dates)].drop(columns=["date_dt", "date_str"], errors="ignore")
    hist_status = write_buy_elite_history(history)
    return history, profile, hist_status, profile_status

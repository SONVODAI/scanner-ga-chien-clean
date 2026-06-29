# =========================================================
# MR.BOT V21 - BRAIN CONTROLLER MASTER PIPELINE
# File: brain_controller.py
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def bc_now():
    return datetime.now(VN_TZ)


def bc_today():
    return bc_now().strftime("%Y-%m-%d")


def bc_time():
    return bc_now().strftime("%H:%M:%S")


def bc_now_str():
    return bc_now().strftime("%Y-%m-%d %H:%M:%S")


def safe_num(x, default=0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


try:
    from brain_manager import get_brain
except Exception as e:
    get_brain = None
    BRAIN_IMPORT_ERROR = str(e)
else:
    BRAIN_IMPORT_ERROR = ""


try:
    from learning_engine import save_experience_learning, get_learning_summary
except Exception:
    save_experience_learning = None
    get_learning_summary = None


try:
    from thinking_engine import save_thinking_journal, get_thinking_summary
except Exception:
    save_thinking_journal = None
    get_thinking_summary = None


try:
    from decision_engine import make_market_decision, get_decision_summary
except Exception:
    make_market_decision = None
    get_decision_summary = None


try:
    from brain_optimizer import run_brain_optimizer, get_optimizer_summary
except Exception:
    run_brain_optimizer = None
    get_optimizer_summary = None


# =========================================================
# SNAPSHOT BUILDERS
# =========================================================

def build_market_snapshot_df(scan_df, market_real, market_live, market_forecast):
    df = scan_df.copy() if isinstance(scan_df, pd.DataFrame) else pd.DataFrame()

    def count_group(name):
        if df.empty or "group" not in df.columns:
            return 0
        return int((df["group"].astype(str) == name).sum())

    return pd.DataFrame([{
        "date": bc_today(),
        "time": bc_time(),
        "session_slot": "EOD" if bc_now().hour >= 15 else "INTRADAY",

        "market_real": market_real,
        "market_live": market_live,
        "market_forecast": market_forecast,

        "pull_dep": count_group("PULL ĐẸP"),
        "pull_vua": count_group("PULL VỪA"),
        "mua_early": count_group("MUA EARLY"),
        "cp_manh": count_group("CP MẠNH"),
        "ga_tang_toc": count_group("GÀ TĂNG TỐC"),

        "obv_green_pct": round((df["obv_status"] == "🟢").mean() * 100, 2) if "obv_status" in df.columns and not df.empty else np.nan,
        "slope_positive_pct": round((df["ema9_ma20_slope"] > 0).mean() * 100, 2) if "ema9_ma20_slope" in df.columns and not df.empty else np.nan,
        "rsi_above_50_pct": round((df["rsi14"] > 50).mean() * 100, 2) if "rsi14" in df.columns and not df.empty else np.nan,
        "scan_count": len(df),
    }])


def build_scan_snapshot_df(scan_df):
    if not isinstance(scan_df, pd.DataFrame) or scan_df.empty:
        return pd.DataFrame()

    keep_cols = [
        "symbol", "group", "price", "total_score",
        "rsi14", "ema9_ma20_slope", "obv_status",
        "dist_from_ema9_pct", "warning",
        "is_live_adjusted",
    ]

    cols = [c for c in keep_cols if c in scan_df.columns]
    out = scan_df[cols].copy()

    out["date"] = bc_today()
    out["time"] = bc_time()

    return out


# =========================================================
# CONTROLLER DECISION
# =========================================================

def build_brain_health(state):
    score = 0
    notes = []

    if state.get("market_status") == "OK":
        score += 20
    else:
        notes.append("Market snapshot chưa ổn.")

    if state.get("learning_status") in ["OK", "SAVED", "LOCAL_ONLY", "GITHUB_OK"]:
        score += 20
    else:
        notes.append("Learning chưa đủ dữ liệu hoặc đang warmup.")

    if state.get("thinking_status") in ["OK", "SAVED", "GITHUB_OK", "LOCAL_ONLY"]:
        score += 20
    else:
        notes.append("Thinking chưa hình thành đủ nhật ký.")

    if state.get("decision_status") == "OK":
        score += 25
    else:
        notes.append("Decision Engine chưa trả quyết định chuẩn.")

    if state.get("optimizer_status") == "OK":
        score += 15
    else:
        notes.append("Optimizer đang warmup hoặc chưa đủ dữ liệu.")

    return {
        "brain_health": int(min(score, 100)),
        "notes": notes,
    }


def build_final_message(state):
    decision = state.get("decision", {}) or {}
    action = decision.get("action", "CHỜ")
    confidence = decision.get("confidence", 0)
    risk = decision.get("risk_level", "")
    nav = decision.get("suggested_nav", 0)
    priority = decision.get("priority_groups", [])

    if isinstance(priority, list):
        priority_text = ", ".join([str(x) for x in priority])
    else:
        priority_text = str(priority)

    return (
        f"Brain Controller: {action}. "
        f"Confidence={confidence}/100, Risk={risk}, NAV gợi ý={nav}%. "
        f"Ưu tiên: {priority_text}."
    )


# =========================================================
# MASTER PIPELINE
# =========================================================

def run_brain_controller(
    scan_df,
    market_real,
    market_live,
    market_forecast,
    trading_today=True,
):
    state = {
        "created_at": bc_now_str(),
        "status": "RUNNING",
        "market_status": "INIT",
        "learning_status": "INIT",
        "thinking_status": "INIT",
        "decision_status": "INIT",
        "optimizer_status": "INIT",

        "brain": None,
        "market_snapshot": {},
        "learning": {},
        "thinking": {},
        "decision": {},
        "optimizer": {},
        "brain_health": 0,
        "notes": [],
        "final_message": "",
    }

    if get_brain is None:
        state["status"] = "IMPORT_ERROR"
        state["error"] = BRAIN_IMPORT_ERROR
        return state

    try:
        brain = get_brain()
        state["brain"] = brain

        # -----------------------------------------------------
        # 1. OBSERVE / SAVE MARKET SNAPSHOT
        # -----------------------------------------------------
        market_snapshot_df = build_market_snapshot_df(
            scan_df=scan_df,
            market_real=market_real,
            market_live=market_live,
            market_forecast=market_forecast,
        )

        brain.remember(
            table="market_snapshot",
            data=market_snapshot_df,
            key=["date", "session_slot"],
            keep_days=720,
            date_col="date",
            sort_by=["date", "time"],
            sync_github=False,
        )

        state["market_snapshot"] = market_snapshot_df.iloc[-1].to_dict()
        state["market_status"] = "OK"

        # -----------------------------------------------------
        # 2. SAVE SCAN SNAPSHOT
        # -----------------------------------------------------
        scan_snapshot_df = build_scan_snapshot_df(scan_df)

        if isinstance(scan_snapshot_df, pd.DataFrame) and not scan_snapshot_df.empty:
            brain.remember(
                table="scan_snapshot",
                data=scan_snapshot_df,
                key=["date", "symbol"],
                keep_days=180,
                date_col="date",
                sort_by=["date", "symbol"],
                sync_github=False,
            )

        # -----------------------------------------------------
        # 3. LEARNING ENGINE
        # -----------------------------------------------------
        if save_experience_learning is not None and trading_today:
            experience_df, experience_status, experience_summary = save_experience_learning(brain)
            state["learning_status"] = str(experience_status)
            state["learning"] = {
                "status": experience_status,
                "summary": experience_summary,
                "rows": len(experience_df) if isinstance(experience_df, pd.DataFrame) else 0,
            }
        else:
            state["learning_status"] = "SKIP"
            state["learning"] = {
                "status": "SKIP_NO_MODULE_OR_NO_TRADING",
                "summary": {},
            }

        if get_learning_summary is not None:
            state["learning"]["controller_summary"] = get_learning_summary(brain)

        # -----------------------------------------------------
        # 4. THINKING ENGINE
        # -----------------------------------------------------
        if save_thinking_journal is not None:
            try:
                thinking_df, thinking_status, thinking_row = save_thinking_journal(brain)
                state["thinking_status"] = str(thinking_status)
                state["thinking"] = {
                    "status": thinking_status,
                    "row": thinking_row,
                    "rows": len(thinking_df) if isinstance(thinking_df, pd.DataFrame) else 0,
                }
            except Exception as e:
                state["thinking_status"] = "ERROR"
                state["thinking"] = {"status": "ERROR", "error": str(e)}
        else:
            state["thinking_status"] = "SKIP"
            state["thinking"] = {"status": "NO_THINKING_MODULE"}

        if get_thinking_summary is not None:
            try:
                state["thinking"]["controller_summary"] = get_thinking_summary(brain)
            except Exception:
                pass

        # -----------------------------------------------------
        # 5. DECISION ENGINE
        # -----------------------------------------------------
        if make_market_decision is not None:
            try:
                decision = make_market_decision(
                    brain=brain,
                    latest_snapshot=None,
                    save=True,
                )
                state["decision_status"] = "OK"
                state["decision"] = decision if isinstance(decision, dict) else {}
            except Exception as e:
                state["decision_status"] = "ERROR"
                state["decision"] = {"error": str(e)}
        else:
            state["decision_status"] = "SKIP"
            state["decision"] = {}

        if get_decision_summary is not None:
            try:
                state["decision"]["controller_summary"] = get_decision_summary(brain)
            except Exception:
                pass

        # -----------------------------------------------------
        # 6. OPTIMIZER
        # -----------------------------------------------------
        if run_brain_optimizer is not None:
            try:
                report, recommendation, save_result = run_brain_optimizer(
                    brain=brain,
                    save=True,
                )
                state["optimizer_status"] = "OK"
                state["optimizer"] = {
                    "report": report,
                    "recommendation": recommendation,
                    "save_result": save_result,
                }
            except Exception as e:
                state["optimizer_status"] = "ERROR"
                state["optimizer"] = {"error": str(e)}
        else:
            state["optimizer_status"] = "SKIP"
            state["optimizer"] = {}

        if get_optimizer_summary is not None:
            try:
                state["optimizer"]["controller_summary"] = get_optimizer_summary(brain)
            except Exception:
                pass

        # -----------------------------------------------------
        # 7. FINAL CONTROLLER STATE
        # -----------------------------------------------------
        health = build_brain_health(state)
        state["brain_health"] = health["brain_health"]
        state["notes"] = health["notes"]
        state["final_message"] = build_final_message(state)

        state["status"] = "READY"
        return state

    except Exception as e:
        state["status"] = "ERROR"
        state["error"] = str(e)
        return state


# =========================================================
# VIEW HELPERS
# =========================================================

def build_controller_view(state):
    if not isinstance(state, dict):
        return pd.DataFrame()

    rows = [
        {
            "Module": "Market",
            "Status": state.get("market_status"),
        },
        {
            "Module": "Learning",
            "Status": state.get("learning_status"),
        },
        {
            "Module": "Thinking",
            "Status": state.get("thinking_status"),
        },
        {
            "Module": "Decision",
            "Status": state.get("decision_status"),
        },
        {
            "Module": "Optimizer",
            "Status": state.get("optimizer_status"),
        },
    ]

    return pd.DataFrame(rows)


def build_controller_summary_view(state):
    if not isinstance(state, dict):
        return pd.DataFrame()

    decision = state.get("decision", {}) or {}

    return pd.DataFrame([{
        "Created": state.get("created_at", ""),
        "Status": state.get("status", ""),
        "Brain Health": state.get("brain_health", 0),
        "Action": decision.get("action", ""),
        "Confidence": decision.get("confidence", 0),
        "Risk": decision.get("risk_level", ""),
        "NAV": decision.get("suggested_nav", 0),
        "Message": state.get("final_message", ""),
    }])

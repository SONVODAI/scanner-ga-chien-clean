# =========================================================
# MR.BOT V21 - BRAIN CONTROLLER
# Điều phối Brain theo kiến trúc hiện tại của app.py
# =========================================================

import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_str():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


try:
    from brain_manager import get_brain
    from learning_engine import save_experience_learning
    from decision_engine import make_market_decision
    from brain_optimizer import run_brain_optimizer
except Exception as e:
    get_brain = None
    save_experience_learning = None
    make_market_decision = None
    run_brain_optimizer = None
    IMPORT_ERROR = str(e)
else:
    IMPORT_ERROR = ""


def build_market_snapshot_df(scan_df, market_real, market_live, market_forecast):
    return pd.DataFrame([{
        "date": datetime.now(VN_TZ).strftime("%Y-%m-%d"),
        "time": datetime.now(VN_TZ).strftime("%H:%M:%S"),
        "session_slot": "EOD" if datetime.now(VN_TZ).hour >= 15 else "INTRADAY",

        "market_real": market_real,
        "market_live": market_live,
        "market_forecast": market_forecast,

        "pull_dep": int((scan_df["group"] == "PULL ĐẸP").sum()) if "group" in scan_df.columns else 0,
        "pull_vua": int((scan_df["group"] == "PULL VỪA").sum()) if "group" in scan_df.columns else 0,
        "mua_early": int((scan_df["group"] == "MUA EARLY").sum()) if "group" in scan_df.columns else 0,
        "cp_manh": int((scan_df["group"] == "CP MẠNH").sum()) if "group" in scan_df.columns else 0,
        "ga_tang_toc": int((scan_df["group"] == "GÀ TĂNG TỐC").sum()) if "group" in scan_df.columns else 0,

        "obv_green_pct": round((scan_df["obv_status"] == "🟢").mean() * 100, 2) if "obv_status" in scan_df.columns else np.nan,
        "slope_positive_pct": round((scan_df["ema9_ma20_slope"] > 0).mean() * 100, 2) if "ema9_ma20_slope" in scan_df.columns else np.nan,
        "rsi_above_50_pct": round((scan_df["rsi14"] > 50).mean() * 100, 2) if "rsi14" in scan_df.columns else np.nan,
    }])


def run_brain_controller(
    scan_df,
    market_real,
    market_live,
    market_forecast,
    trading_today=True,
):
    if get_brain is None:
        return {
            "status": "IMPORT_ERROR",
            "error": IMPORT_ERROR,
        }

    brain = get_brain()

    state = {
        "created_at": now_str(),
        "status": "RUNNING",
        "brain": brain,
        "learning": {},
        "decision": {},
        "optimizer": {},
    }

    try:
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

        if save_experience_learning is not None and trading_today:
            experience_df, experience_status, experience_summary = save_experience_learning(brain)
            state["learning"] = {
                "status": experience_status,
                "summary": experience_summary,
            }
        else:
            state["learning"] = {
                "status": "SKIP_NO_MODULE_OR_NO_TRADING",
                "summary": {},
            }

        if make_market_decision is not None:
            decision = make_market_decision(brain=brain, save=True)
            state["decision"] = decision
        else:
            state["decision"] = {}

        if run_brain_optimizer is not None:
            report, recommendation, save_result = run_brain_optimizer(
                brain=brain,
                save=True,
            )
            state["optimizer"] = {
                "report": report,
                "recommendation": recommendation,
                "save_result": save_result,
            }
        else:
            state["optimizer"] = {}

        state["status"] = "READY"
        return state

    except Exception as e:
        state["status"] = "ERROR"
        state["error"] = str(e)
        return state

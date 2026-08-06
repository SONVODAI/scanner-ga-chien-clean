# =========================================================
# MR.BOT GENESIS V24 - PATTERN MEMORY & ADAPTIVE LEARNING
# =========================================================
from __future__ import annotations

import os
import re
import base64
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SCHEMA_VERSION = "GENESIS_V24"

PATTERN_FILE = "pattern_history.csv"
GITHUB_REPO_OWNER = "SONVODAI"
GITHUB_REPO_NAME = "scanner-ga-chien-clean"
GITHUB_PATTERN_PATH = PATTERN_FILE

MIN_PATTERN_SAMPLE = 5
DEFAULT_TOP_PATTERNS = 30

LEARNING_GROUPS = ("MUA EARLY", "PULL VỪA", "PULL ĐẸP", "CP MẠNH")

REQUIRED_COLUMNS = [
    "sample_id","date","time","schema_version","symbol",
    "market_real","market_forecast","market_regime","market_phase","breadth_score",
    "is_ai","is_leader","is_earning","is_final_decision",
    "group","price","total_score","E","R","O","S","RS","V",
    "rsi14","ema9_ma20_slope","dist_from_ema9_pct","obv_status",
    "volume","vol_ma20","green_2_confirm","early_green2",
    "early_dry_green2","warning",
    "rsi_bucket","rs_bucket","obv_bucket","pattern_signature",
    "t1_return","t3_return","t5_return","t10_return",
    "t1_win","t3_win","t5_win","t10_win",
]

OUTCOME_COLUMNS = [
    "t1_return","t3_return","t5_return","t10_return",
    "t1_win","t3_win","t5_win","t10_win",
]

FEATURE_COLUMNS = [
    "group","E","R","O","S","RS","V",
    "rsi_bucket","rs_bucket","obv_bucket",
    "green_2_confirm","early_green2","early_dry_green2","warning",
    "market_regime","market_phase",
    "is_ai","is_leader","is_earning","is_final_decision",
]


# ---------------- BASIC HELPERS ----------------

def today_str():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


def now_time_str():
    return datetime.now(VN_TZ).strftime("%H:%M:%S")


def _safe_float(x):
    try:
        if x is None or pd.isna(x):
            return None
        if isinstance(x, str):
            s = x.strip().replace("%", "").replace(",", ".")
            m = re.search(r"-?\d+(?:\.\d+)?", s)
            return float(m.group()) if m else None
        return float(x)
    except Exception:
        return None


def _clean_symbol(x):
    return "" if x is None else str(x).strip().upper()


def _calc_return(buy_price, sell_price):
    buy, sell = _safe_float(buy_price), _safe_float(sell_price)
    if buy is None or sell is None or buy <= 0:
        return None
    return round((sell - buy) / buy * 100.0, 2)


def _calc_win(ret):
    v = _safe_float(ret)
    return None if v is None else int(v > 0)


def _numeric_mean(series):
    x = pd.to_numeric(series, errors="coerce").dropna()
    return None if x.empty else round(float(x.mean()), 2)


def _winrate(series):
    x = pd.to_numeric(series, errors="coerce").dropna()
    return None if x.empty else round(float(x.mean()) * 100.0, 1)


# ---------------- SCHEMA / NORMALIZATION ----------------

def normalize_schema(df):
    out = pd.DataFrame() if df is None else df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in out.columns:
            out[col] = None
    extras = [c for c in out.columns if c not in REQUIRED_COLUMNS]
    return out[REQUIRED_COLUMNS + extras]


def normalize_rsi(rsi):
    r = _safe_float(rsi)
    if r is None: return "UNKNOWN"
    if r < 40: return "<40"
    if r < 45: return "40-45"
    if r < 50: return "45-50"
    if r < 55: return "50-55"
    if r < 60: return "55-60"
    if r < 65: return "60-65"
    if r < 70: return "65-70"
    return ">=70"


def normalize_rs(rs):
    r = _safe_float(rs)
    if r is None: return "UNKNOWN"
    if r <= -4: return "<=-4"
    if r <= -2: return "-4~-2"
    if r <= 0: return "-2~0"
    if r <= 2: return "0~2"
    if r <= 4: return "2~4"
    return ">4"


def normalize_obv(value):
    if value is None:
        return "UNKNOWN"
    try:
        if pd.isna(value):
            return "UNKNOWN"
    except Exception:
        pass
    s = str(value).strip().upper()
    if "GREEN" in s or "XANH" in s: return "GREEN"
    if "RED" in s or "ĐỎ" in s: return "RED"
    if "UP" in s or "TĂNG" in s: return "UP"
    if "DOWN" in s or "GIẢM" in s: return "DOWN"
    return s or "UNKNOWN"


def build_pattern_signature(row):
    return "|".join([
        f"G={row.get('group','')}",
        f"RS={normalize_rs(row.get('RS'))}",
        f"RSI={normalize_rsi(row.get('rsi14'))}",
        f"OBV={normalize_obv(row.get('obv_status'))}",
        f"E={row.get('E','')}",
        f"R={row.get('R','')}",
        f"S={row.get('S','')}",
        f"G2={row.get('green_2_confirm','')}",
        f"EARLY={row.get('early_green2','')}",
        f"MKT={row.get('market_regime','')}",
    ])


def add_normalized_features(df):
    out = normalize_schema(df)
    out["rsi_bucket"] = out["rsi14"].apply(normalize_rsi)
    out["rs_bucket"] = out["RS"].apply(normalize_rs)
    out["obv_bucket"] = out["obv_status"].apply(normalize_obv)
    out["pattern_signature"] = out.apply(build_pattern_signature, axis=1)
    return out


def migrate_history(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    out = normalize_schema(df)
    out["symbol"] = out["symbol"].map(_clean_symbol)
    missing = out["sample_id"].isna() | out["sample_id"].astype(str).str.strip().eq("")
    if missing.any():
        out.loc[missing, "sample_id"] = (
            out.loc[missing, "date"].astype(str) + "_" +
            out.loc[missing, "time"].fillna("00:00:00").astype(str) + "_" +
            out.loc[missing, "symbol"].astype(str)
        )
    out["schema_version"] = out["schema_version"].fillna(SCHEMA_VERSION)
    return add_normalized_features(out)


# ---------------- STORAGE ----------------

def get_github_token():
    try:
        return st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return None


def read_pattern_history():
    token = get_github_token()
    if token:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_PATTERN_PATH}"
            r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=10)
            if r.status_code == 200:
                content = r.json().get("content", "")
                if content:
                    decoded = base64.b64decode(content).decode("utf-8")
                    if decoded.strip():
                        return migrate_history(pd.read_csv(StringIO(decoded)))
        except Exception as e:
            print("READ PATTERN GITHUB ERROR:", e)

    try:
        if os.path.exists(PATTERN_FILE) and os.path.getsize(PATTERN_FILE) > 1:
            return migrate_history(pd.read_csv(PATTERN_FILE))
    except Exception as e:
        print("READ PATTERN LOCAL ERROR:", e)

    return pd.DataFrame(columns=REQUIRED_COLUMNS)


def write_pattern_history(df):
    if df is None:
        return "NO_DF"
    out = normalize_schema(df)
    out.to_csv(PATTERN_FILE, index=False)

    token = get_github_token()
    if not token:
        return "LOCAL_ONLY"

    try:
        csv_content = out.to_csv(index=False)
        encoded = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
        url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_PATTERN_PATH}"
        headers = {"Authorization": f"token {token}"}
        sha = None
        get_r = requests.get(url, headers=headers, timeout=10)
        if get_r.status_code == 200:
            sha = get_r.json().get("sha")
        payload = {
            "message": f"Update pattern history {today_str()} {now_time_str()}",
            "content": encoded,
        }
        if sha:
            payload["sha"] = sha
        put_r = requests.put(url, headers=headers, json=payload, timeout=15)
        if put_r.status_code in (200, 201):
            return "GITHUB_OK"
        return f"GITHUB_FAIL_{put_r.status_code}: {put_r.text[:200]}"
    except Exception as e:
        return f"GITHUB_ERROR: {e}"


# ---------------- SAMPLE / HISTORY ENGINE ----------------

def filter_learning_samples(scan_df):
    if scan_df is None or scan_df.empty or "group" not in scan_df.columns:
        return pd.DataFrame()
    return scan_df[scan_df["group"].isin(LEARNING_GROUPS)].copy().reset_index(drop=True)


def _symbol_set(df):
    if df is None or df.empty:
        return set()
    for col in ("symbol", "MÃ", "Mã", "ma"):
        if col in df.columns:
            return set(df[col].map(_clean_symbol))
    return set()


def build_samples(
    scan_df, market_real, market_forecast,
    market_context=None, ai_df=None, leader_df=None,
    earning_df=None, final_df=None,
):
    out = filter_learning_samples(scan_df)
    if out.empty or "symbol" not in out.columns:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    out["symbol"] = out["symbol"].map(_clean_symbol)
    now = datetime.now(VN_TZ)
    out["date"] = now.strftime("%Y-%m-%d")
    out["time"] = now.strftime("%H:%M:%S")
    out["schema_version"] = SCHEMA_VERSION
    out["sample_id"] = out["date"] + "_" + out["time"] + "_" + out["symbol"]

    out["market_real"] = market_real
    out["market_forecast"] = market_forecast
    ctx = market_context or {}
    out["market_regime"] = ctx.get("market_regime")
    out["market_phase"] = ctx.get("market_phase")
    out["breadth_score"] = ctx.get("breadth_score")

    out["is_ai"] = out["symbol"].isin(_symbol_set(ai_df))
    out["is_leader"] = out["symbol"].isin(_symbol_set(leader_df))
    out["is_earning"] = out["symbol"].isin(_symbol_set(earning_df))
    out["is_final_decision"] = out["symbol"].isin(_symbol_set(final_df))

    for col in OUTCOME_COLUMNS:
        if col not in out.columns:
            out[col] = None
    return add_normalized_features(out)


def merge_history(old_df, new_df):
    if old_df is None or old_df.empty:
        return migrate_history(new_df)
    if new_df is None or new_df.empty:
        return migrate_history(old_df)

    out = pd.concat([migrate_history(old_df), migrate_history(new_df)], ignore_index=True, sort=False)
    return (
        out.drop_duplicates(subset=["sample_id"], keep="last")
        .sort_values(["date","time","symbol"], na_position="last")
        .reset_index(drop=True)
    )


def save_pattern_history(
    brain, scan_df, market_real, market_forecast,
    market_context=None, ai_df=None, leader_df=None,
    earning_df=None, final_df=None,
):
    # Tương thích lời gọi V22 4 tham số.
    if scan_df is None or scan_df.empty:
        return pd.DataFrame(), "EMPTY_SCAN"

    new_samples = build_samples(
        scan_df, market_real, market_forecast,
        market_context, ai_df, leader_df, earning_df, final_df,
    )
    if new_samples.empty:
        return pd.DataFrame(), "EMPTY_LEARN_GROUP"

    history = merge_history(read_pattern_history(), new_samples)
    status = write_pattern_history(history)
    print("V24 NEW SAMPLES =", len(new_samples))
    print("V24 TOTAL ROWS  =", len(history))
    print("V24 STATUS      =", status)
    return history, status


# ---------------- T+ ENGINE ----------------

def _detect_symbol_price_columns(df):
    symbol_col = next((c for c in ("symbol","MÃ","Mã","ma") if c in df.columns), None)
    price_col = next((c for c in ("close_price","price","GIÁ","Giá","close") if c in df.columns), None)
    return symbol_col, price_col


def update_tplus_result(history_df, today_price_df, hold_days, target_date=None):
    if history_df is None or history_df.empty or today_price_df is None or today_price_df.empty:
        return history_df

    return_col, win_col = f"t{hold_days}_return", f"t{hold_days}_win"
    if return_col not in OUTCOME_COLUMNS:
        raise ValueError(f"Unsupported T+ horizon: {hold_days}")

    symbol_col, price_col = _detect_symbol_price_columns(today_price_df)
    if symbol_col is None or price_col is None:
        raise ValueError("Price dataframe needs symbol and price/close columns")

    prices = today_price_df[[symbol_col, price_col]].copy()
    prices[symbol_col] = prices[symbol_col].map(_clean_symbol)
    prices[price_col] = pd.to_numeric(prices[price_col], errors="coerce")
    price_map = prices.dropna(subset=[price_col]).set_index(symbol_col)[price_col].to_dict()

    out = migrate_history(history_df)
    mask = out[return_col].isna()
    if target_date is not None:
        mask &= out["date"].astype(str).eq(str(target_date))

    for idx in out.index[mask]:
        sell = price_map.get(_clean_symbol(out.at[idx, "symbol"]))
        if sell is None:
            continue
        ret = _calc_return(out.at[idx, "price"], sell)
        if ret is not None:
            out.at[idx, return_col] = ret
            out.at[idx, win_col] = _calc_win(ret)
    return out


def update_all_tplus(history_df, t1_price_df=None, t3_price_df=None, t5_price_df=None, t10_price_df=None):
    out = migrate_history(history_df)
    for days, frame in ((1,t1_price_df),(3,t3_price_df),(5,t5_price_df),(10,t10_price_df)):
        if frame is not None and not frame.empty:
            out = update_tplus_result(out, frame, days)
    return out


# ---------------- LEARNING STATISTICS ----------------

def build_pattern_statistics(history_df):
    if history_df is None or history_df.empty:
        return pd.DataFrame()
    df = add_normalized_features(migrate_history(history_df))
    rows = []
    for feature in FEATURE_COLUMNS:
        if feature not in df.columns:
            continue
        for value, sub in df.dropna(subset=[feature]).groupby(feature, dropna=True):
            row = {"feature": feature, "value": value, "samples": len(sub)}
            for t in (1,3,5,10):
                row[f"avg_t{t}"] = _numeric_mean(sub[f"t{t}_return"])
                row[f"winrate_t{t}"] = _winrate(sub[f"t{t}_win"])
            rows.append(row)
    return pd.DataFrame(rows)


def build_best_pattern(stats_df):
    if stats_df is None or stats_df.empty:
        return pd.DataFrame()
    cols = [c for c in ("winrate_t5","avg_t5","samples") if c in stats_df.columns]
    return stats_df.sort_values(cols, ascending=False, na_position="last").reset_index(drop=True) if cols else stats_df


def build_learning_snapshot(history_df):
    best = build_best_pattern(build_pattern_statistics(history_df))
    return {"history_rows": 0 if history_df is None else len(history_df),
            "patterns": len(best), "best_pattern": best.head(30)}


def build_pattern_dna(history_df):
    return pd.DataFrame() if history_df is None or history_df.empty else add_normalized_features(migrate_history(history_df))


def build_dna_statistics(history_df):
    df = build_pattern_dna(history_df)
    if df.empty:
        return pd.DataFrame()
    rows = []
    for dna, sub in df.groupby("pattern_signature", dropna=True):
        row = {"pattern_signature": dna, "samples": len(sub)}
        for t in (1,3,5,10):
            row[f"avg_t{t}"] = _numeric_mean(sub[f"t{t}_return"])
            row[f"winrate_t{t}"] = _winrate(sub[f"t{t}_win"])
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["winrate_t5","avg_t5","samples"], ascending=False, na_position="last").reset_index(drop=True)


def export_learning_snapshot(history_df):
    feature_stats = build_pattern_statistics(history_df)
    dna_stats = build_dna_statistics(history_df)
    return {"feature_stats": feature_stats, "dna_stats": dna_stats, "best_dna": dna_stats.head(20)}


def filter_valid_patterns(stats_df, min_samples=MIN_PATTERN_SAMPLE):
    if stats_df is None or stats_df.empty or "samples" not in stats_df.columns:
        return pd.DataFrame()
    samples = pd.to_numeric(stats_df["samples"], errors="coerce").fillna(0)
    return stats_df[samples >= min_samples].copy().reset_index(drop=True)


def score_pattern(row):
    score = min(_safe_float(row.get("samples")) or 0, 30)
    for t, weight in ((3,.30),(5,.45),(10,.35)):
        wr, avg = _safe_float(row.get(f"winrate_t{t}")), _safe_float(row.get(f"avg_t{t}"))
        if wr is not None: score += wr * weight
        if avg is not None: score += max(avg, 0) * 3
    return round(score, 2)


def calculate_pattern_confidence(row):
    samples = int(_safe_float(row.get("samples")) or 0)
    wr = _safe_float(row.get("winrate_t5"))
    if wr is None: wr = _safe_float(row.get("winrate_t3")) or 0
    if samples < 5: return "LOW"
    if samples < 10: return "MEDIUM" if wr >= 80 else "LOW"
    if samples < 20:
        if wr >= 75: return "HIGH"
        if wr >= 60: return "MEDIUM"
        return "LOW"
    if wr >= 75: return "VERY_HIGH"
    if wr >= 60: return "HIGH"
    return "MEDIUM"


def rank_patterns(stats_df):
    out = filter_valid_patterns(stats_df)
    if out.empty:
        return out
    out["learning_score"] = out.apply(score_pattern, axis=1)
    out["confidence"] = out.apply(calculate_pattern_confidence, axis=1)
    return out.sort_values(["learning_score","samples"], ascending=False).reset_index(drop=True)


def export_learning_table(history_df):
    return rank_patterns(build_pattern_statistics(history_df))


def get_best_learning_patterns(history_df, top_n=DEFAULT_TOP_PATTERNS):
    out = rank_patterns(build_dna_statistics(history_df))
    if out.empty:
        return out
    return out[out["confidence"].isin(["VERY_HIGH","HIGH"])].head(top_n).reset_index(drop=True)


# ---------------- SIMILARITY / ADAPTIVE BONUS ----------------

SIMILARITY_FEATURE_WEIGHTS = {
    "group":1.40, "rs_bucket":1.25, "rsi_bucket":1.20, "obv_bucket":1.15,
    "E":.70, "R":.70, "S":.70, "green_2_confirm":.80,
    "early_green2":.80, "market_regime":1.30,
}


def _row_dna(row):
    return {
        "group":row.get("group"), "rs_bucket":normalize_rs(row.get("RS")),
        "rsi_bucket":normalize_rsi(row.get("rsi14")),
        "obv_bucket":normalize_obv(row.get("obv_status")),
        "E":row.get("E"), "R":row.get("R"), "S":row.get("S"),
        "green_2_confirm":row.get("green_2_confirm"),
        "early_green2":row.get("early_green2"),
        "market_regime":row.get("market_regime"),
    }


def _signature_to_dna(signature):
    mapping = {"G":"group","RS":"rs_bucket","RSI":"rsi_bucket","OBV":"obv_bucket",
               "E":"E","R":"R","S":"S","G2":"green_2_confirm",
               "EARLY":"early_green2","MKT":"market_regime"}
    out = {}
    for part in str(signature).split("|"):
        if "=" in part:
            k, v = part.split("=",1)
            if k in mapping: out[mapping[k]] = v
    return out


def pattern_similarity(stock_row, pattern_signature):
    stock, pattern = _row_dna(stock_row), _signature_to_dna(pattern_signature)
    matched = usable = 0.0
    for feature, weight in SIMILARITY_FEATURE_WEIGHTS.items():
        b = pattern.get(feature)
        if b is None or str(b).strip() in ("","None","nan","UNKNOWN"):
            continue
        usable += weight
        if str(stock.get(feature)).strip().upper() == str(b).strip().upper():
            matched += weight
    return 0.0 if usable <= 0 else round(matched / usable * 100.0, 2)


def build_learning_insight(history_df):
    table = get_best_learning_patterns(history_df, DEFAULT_TOP_PATTERNS)
    patterns = []
    for _, row in table.iterrows():
        patterns.append({
            "pattern":row.get("pattern_signature"),
            "confidence":row.get("confidence"),
            "samples":int(_safe_float(row.get("samples")) or 0),
            "winrate":_safe_float(row.get("winrate_t5")),
            "winrate_t3":_safe_float(row.get("winrate_t3")),
            "winrate_t10":_safe_float(row.get("winrate_t10")),
            "avg_return":_safe_float(row.get("avg_t5")),
            "learning_score":_safe_float(row.get("learning_score")),
        })
    return {"patterns":patterns,
            "summary":{"total_patterns":len(patterns),
                       "very_high":sum(p["confidence"]=="VERY_HIGH" for p in patterns),
                       "high":sum(p["confidence"]=="HIGH" for p in patterns)}}


def match_pattern(scan_row, learning_patterns, min_similarity=70.0):
    best = None
    for p in learning_patterns:
        signature = p.get("pattern") or p.get("pattern_signature")
        if not signature: continue
        similarity = pattern_similarity(scan_row, signature)
        if similarity < min_similarity: continue
        candidate = dict(p)
        candidate.update({"matched":True,"similarity":similarity,"pattern":signature})
        if best is None or (similarity, candidate.get("learning_score") or 0) > (
            best.get("similarity") or 0, best.get("learning_score") or 0):
            best = candidate
    return best or {"matched":False,"similarity":0.0}


def calculate_learning_bonus(match):
    if not match.get("matched"):
        return 0.0
    base = {"VERY_HIGH":20.0,"HIGH":14.0,"MEDIUM":7.0,"LOW":0.0}.get(str(match.get("confidence")),0.0)
    similarity = _safe_float(match.get("similarity")) or 0
    wr = _safe_float(match.get("winrate"))
    if wr is None: wr = _safe_float(match.get("winrate_t3")) or 0
    return round(min((base + wr/20.0) * similarity/100.0, 25.0), 2)


def learning_bonus_for_stock(scan_row, history_df, min_similarity=70.0):
    insight = build_learning_insight(history_df)
    return calculate_learning_bonus(match_pattern(scan_row, insight["patterns"], min_similarity))


def explain_learning_match(scan_row, history_df, min_similarity=70.0):
    insight = build_learning_insight(history_df)
    match = match_pattern(scan_row, insight["patterns"], min_similarity)
    match["bonus"] = calculate_learning_bonus(match)
    return match


# ---------------- EVOLUTION / CONTEXT / BRAIN INSIGHT ----------------

def build_evolution_history(history_df):
    if history_df is None or history_df.empty:
        return pd.DataFrame()
    df = migrate_history(history_df).copy()
    df["_dt"] = pd.to_datetime(df["date"].astype(str)+" "+df["time"].fillna("00:00:00").astype(str), errors="coerce")
    df = df.sort_values(["symbol","_dt"])
    rows = []
    for symbol, sub in df.groupby("symbol"):
        groups = []
        for g in sub["group"].dropna().astype(str):
            if not groups or groups[-1] != g: groups.append(g)
        if groups:
            rows.append({"symbol":symbol,"steps":len(groups),
                         "evolution_path":" -> ".join(groups),
                         "start_group":groups[0],"last_group":groups[-1]})
    return pd.DataFrame(rows)


def build_evolution_statistics(history_df):
    evo = build_evolution_history(history_df)
    if evo.empty: return evo
    return (evo.groupby("evolution_path").agg(samples=("symbol","count"))
            .reset_index().sort_values("samples",ascending=False).reset_index(drop=True))


def _market_bucket(x):
    v = _safe_float(x)
    if v is None: return "UNKNOWN"
    if v < 3: return "<3"
    if v < 5: return "3-5"
    if v < 7: return "5-7"
    if v < 9: return "7-9"
    return ">=9"


def build_context_statistics(history_df):
    if history_df is None or history_df.empty:
        return pd.DataFrame()
    df = migrate_history(history_df).copy()
    df["market_real_bucket"] = df["market_real"].apply(_market_bucket)
    df["market_forecast_bucket"] = df["market_forecast"].apply(_market_bucket)
    rows = []
    for feature in ("market_real_bucket","market_forecast_bucket","market_regime","market_phase","group"):
        for value, sub in df.dropna(subset=[feature]).groupby(feature):
            row = {"context":feature,"value":value,"samples":len(sub)}
            for t in (3,5,10):
                row[f"avg_t{t}"] = _numeric_mean(sub[f"t{t}_return"])
                row[f"winrate_t{t}"] = _winrate(sub[f"t{t}_win"])
            rows.append(row)
    return pd.DataFrame(rows)


def build_brain_insight(history_df):
    history = migrate_history(history_df)
    feature = export_learning_table(history)
    dna = get_best_learning_patterns(history, 20)
    context = build_context_statistics(history)
    evolution = build_evolution_statistics(history)
    return {
        "schema_version":SCHEMA_VERSION,
        "history_rows":len(history),
        "feature_patterns":feature,
        "winning_dna":dna,
        "context_patterns":context,
        "evolution_patterns":evolution,
        "summary":{"valid_feature_patterns":len(feature),"valid_dna_patterns":len(dna),
                   "context_rows":len(context),"evolution_paths":len(evolution)},
    }


def validate_history(history_df):
    if history_df is None:
        return {"ok":False,"errors":["history_df is None"],"warnings":[]}
    errors, warnings = [], []
    missing = [c for c in REQUIRED_COLUMNS if c not in history_df.columns]
    if missing: errors.append(f"Missing required columns: {missing}")
    if "sample_id" in history_df.columns:
        dup = history_df["sample_id"].dropna().duplicated().sum()
        if dup: warnings.append(f"{dup} duplicated sample_id rows")
    return {"ok":not errors,"errors":errors,"warnings":warnings,
            "rows":len(history_df),"schema_version":SCHEMA_VERSION}


__all__ = [
    "SCHEMA_VERSION","PATTERN_FILE","LEARNING_GROUPS","REQUIRED_COLUMNS",
    "read_pattern_history","write_pattern_history","save_pattern_history",
    "update_tplus_result","update_all_tplus","build_pattern_statistics",
    "build_dna_statistics","build_learning_snapshot","export_learning_snapshot",
    "export_learning_table","get_best_learning_patterns","build_learning_insight",
    "pattern_similarity","match_pattern","calculate_learning_bonus",
    "learning_bonus_for_stock","explain_learning_match",
    "build_evolution_history","build_evolution_statistics",
    "build_context_statistics","build_brain_insight","validate_history",
]

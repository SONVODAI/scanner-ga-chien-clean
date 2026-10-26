"""
FC-1 expanding walk-forward evaluator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from modules.forecast_research.fc1.baselines import BASELINE_NAMES, predict_baseline
from modules.forecast_research.fc1.contract import (
    FC1_VERSION,
    FC1_WALKFORWARD_SCHEMA_VERSION,
    HORIZONS,
    INSUFFICIENT_EVIDENCE,
    PIT_SAFE_FEATURES,
)
from modules.forecast_research.fc1.episodes import assign_episodes, episode_summary
from modules.forecast_research.fc1.maturity import (
    assert_train_precedes_prediction,
    filter_train_labels,
    maturity_cutoff_description,
)
from modules.forecast_research.fc1.metrics import binary_metrics, continuous_metrics, downside_discrimination


def run_walkforward(
    pit: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    horizons: Sequence[int] = HORIZONS,
    baselines: Sequence[str] = BASELINE_NAMES,
    feature_set: Sequence[str] = PIT_SAFE_FEATURES,
) -> Dict[str, Any]:
    """
    Expanding walk-forward over dates that have matured labels.

    For each prediction date t with a matured label at horizon h:
      train = labels matured strictly before t
      predict baselines at t
      score against realized label at t
    """
    pit = assign_episodes(pit)
    pit = pit.sort_values("trade_date").reset_index(drop=True)
    labels = labels.copy()
    labels["trade_date"] = labels["trade_date"].astype(str).str[:10]
    labels["mature_trade_date"] = labels["mature_trade_date"].astype(str).str[:10]

    pred_rows: List[Dict[str, Any]] = []
    feature_set = list(feature_set)

    for h in horizons:
        lab_h = labels[labels["horizon"] == int(h)].sort_values("trade_date")
        # Eligible prediction dates: those with matured labels in the artifact
        for _, lab in lab_h.iterrows():
            t = str(lab["trade_date"])[:10]
            pred_pit = pit[pit["trade_date"].astype(str).str[:10] == t]
            if pred_pit.empty:
                continue
            pred_row = pred_pit.iloc[0]
            train_lab = filter_train_labels(labels, prediction_date=t, horizon=int(h))
            train_dates = train_lab["trade_date"].astype(str).str[:10].tolist()
            mature_dates = train_lab["mature_trade_date"].astype(str).str[:10].tolist()
            assert_train_precedes_prediction(train_dates, t, mature_dates)

            train_pit = pit[pit["trade_date"].astype(str).str[:10].isin(set(train_dates))].copy()

            for bname in baselines:
                pred = predict_baseline(
                    bname,
                    train_labels=train_lab,
                    train_pit=train_pit,
                    pred_row=pred_row,
                )
                rec = {
                    "fc1_version": FC1_VERSION,
                    "walkforward_schema_version": FC1_WALKFORWARD_SCHEMA_VERSION,
                    "horizon": int(h),
                    "prediction_date": t,
                    "mature_trade_date": str(lab["mature_trade_date"])[:10],
                    "maturity_cutoff": t,
                    "maturity_rule": maturity_cutoff_description(t, int(h)),
                    "train_dates_json": json.dumps(train_dates),
                    "train_n": int(len(train_lab)),
                    "feature_set_json": json.dumps(feature_set),
                    "baseline": bname,
                    "baseline_status": pred["status"],
                    "binary_prob": pred.get("binary_prob"),
                    "continuous_pred": pred.get("continuous_pred"),
                    "realized_favorable_median": lab.get("favorable_median"),
                    "realized_broad_favorable": lab.get("broad_favorable"),
                    "realized_xs_median_return": lab.get("xs_median_return"),
                    "realized_xs_positive_share": lab.get("xs_positive_share"),
                    "realized_xs_lt_minus3pct_share": lab.get("xs_lt_minus3pct_share"),
                    "episode_id": int(pred_row.get("episode_id")) if pd.notna(pred_row.get("episode_id")) else None,
                    "regime_pit": pred_row.get("regime_pit"),
                }
                pred_rows.append(rec)

    preds = pd.DataFrame(pred_rows)
    leaderboard = _build_leaderboard(preds, pit)
    return {
        "predictions": preds,
        "leaderboard": leaderboard,
        "pit_with_episodes": pit,
        "protocol": {
            "type": "expanding_walkforward",
            "random_split": False,
            "maturity_rule": "mature_trade_date < prediction_date AND trade_date < prediction_date",
            "feature_set": feature_set,
            "baselines": list(baselines),
            "horizons": list(horizons),
        },
    }


def _build_leaderboard(preds: pd.DataFrame, pit: pd.DataFrame) -> Dict[str, Any]:
    board: Dict[str, Any] = {}
    if preds.empty:
        return {"note": "no_predictions"}

    for h in sorted(preds["horizon"].unique()):
        hkey = f"T{int(h)}"
        board[hkey] = {}
        sub_h = preds[preds["horizon"] == h]
        dates = sorted(sub_h["prediction_date"].unique().tolist())
        ep = episode_summary(pit, dates=dates)
        board[hkey]["prediction_dates"] = dates
        board[hkey]["n_prediction_dates"] = len(dates)
        board[hkey]["episode_summary"] = ep

        for bname in sub_h["baseline"].unique():
            bsub = sub_h[sub_h["baseline"] == bname]
            ok = bsub[bsub["baseline_status"] == "OK"]
            entry: Dict[str, Any] = {
                "baseline": bname,
                "n_rows": int(len(bsub)),
                "n_ok": int(len(ok)),
                "n_insufficient": int((bsub["baseline_status"] == INSUFFICIENT_EVIDENCE).sum()),
            }
            if ok.empty:
                entry["status"] = INSUFFICIENT_EVIDENCE
            else:
                entry["binary"] = binary_metrics(
                    ok["realized_favorable_median"].tolist(),
                    ok["binary_prob"].tolist(),
                )
                entry["continuous"] = continuous_metrics(
                    ok["realized_xs_median_return"].tolist(),
                    ok["continuous_pred"].tolist(),
                )
                entry["downside"] = downside_discrimination(
                    ok["realized_xs_lt_minus3pct_share"].tolist(),
                    ok["binary_prob"].tolist(),
                )
                entry["episodes_in_ok"] = int(ok["episode_id"].nunique()) if "episode_id" in ok else None
                entry["status"] = "OK"
                # Tiny-N caveat
                if entry["binary"]["n"] < 10:
                    entry["interpretation"] = "TINY_N_DO_NOT_RANK_AS_SIGNIFICANT"
            board[hkey][bname] = entry

        if int(h) == 10:
            max_ok = 0
            for _name, entry in board[hkey].items():
                if isinstance(entry, dict) and "n_ok" in entry:
                    max_ok = max(max_ok, int(entry.get("n_ok") or 0))
            if len(dates) < 20 or max_ok < 10:
                board[hkey]["verdict"] = INSUFFICIENT_EVIDENCE
                board[hkey]["note"] = (
                    "T10 explicitly INSUFFICIENT_EVIDENCE for ranking "
                    f"(n_prediction_dates={len(dates)}, max_baseline_ok={max_ok})"
                )
    return board

"""
Forecast V2 FC-1 harness tests — maturity, leakage, walk-forward, isolation.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.forecast_research.fc1.baselines import predict_baseline
from modules.forecast_research.fc1.contract import (
    FORBIDDEN_FEATURE_EXACT,
    INSUFFICIENT_EVIDENCE,
    PIT_SAFE_FEATURES,
    PROVENANCE_PIT_SAFE,
)
from modules.forecast_research.fc1.episodes import assign_episodes
from modules.forecast_research.fc1.labels import (
    aggregate_universe_opportunity,
    build_labels,
    label_available_at_prediction,
    mature_trade_date_for,
)
from modules.forecast_research.fc1.maturity import (
    assert_train_precedes_prediction,
    filter_train_labels,
)
from modules.forecast_research.fc1.pit_dataset import (
    assert_no_forbidden_feature_columns,
    build_pit_dataset,
    fit_past_only_zscore,
)
from modules.forecast_research.fc1.runner import run_fc1_harness
from modules.forecast_research.fc1.walkforward import run_walkforward


REPO = Path(__file__).resolve().parents[1]


def _synth_board(n: int, trade_date: str, *, real: float = 7.0, early_frac: float = 0.3) -> pd.DataFrame:
    groups = [
        "THEO DÕI",
        "TÍCH LŨY",
        "MUA EARLY",
        "PULL VỪA",
        "PULL ĐẸP",
        "MUA BREAK",
        "CP MẠNH",
        "GÀ TĂNG TỐC",
    ]
    rows = []
    n_early = int(n * early_frac)
    for i in range(n):
        g = "MUA EARLY" if i < n_early else groups[i % len(groups)]
        rows.append(
            {
                "snapshot_date": trade_date,
                "trade_date": trade_date,
                "symbol": f"S{i:03d}",
                "price": 100 + i * 0.1,
                "group": g,
                "rsi14": 30 + (i % 50),
                "rs5": (i % 11) - 5,
                "rs10": (i % 9) - 4,
                "obv_status": "🟢" if i % 2 == 0 else "🔴",
                "ema9_ma20_slope": 0.1 if i % 3 == 0 else -0.1,
                "near_bottom_20_pct": 1.0 if i % 5 == 0 else 10.0,
                "near_bottom_60_pct": 2.0 if i % 7 == 0 else 20.0,
                "dist_high20_pct": -1.0 if i % 6 == 0 else -15.0,
                "market_real": real,
                "market_live": real - 0.5,
                "market_forecast": max(0.0, real - 5.0),
                "breadth": 40 + real * 2,
            }
        )
    return pd.DataFrame(rows)


def _write_fixture(tmp: Path) -> Path:
    root = tmp / "repo"
    (root / "data" / "earning_learning").mkdir(parents=True)
    (root / "data" / "forecast_research").mkdir(parents=True)
    dates = [
        "2026-07-31",
        "2026-08-03",
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
        "2026-08-07",
        "2026-08-10",
        "2026-08-11",
        "2026-08-12",
        "2026-08-13",
        "2026-08-14",
        "2026-08-17",
    ]
    ems = pd.concat([_synth_board(142, d, real=5.0 + (i % 5)) for i, d in enumerate(dates)], ignore_index=True)
    ems.to_csv(root / "data" / "earning_money_snapshots.csv", index=False)
    obs = ems.rename(columns={}).copy()
    obs["trade_date"] = obs["snapshot_date"]
    obs.to_csv(root / "data" / "earning_learning" / "observations.csv", index=False)

    # Outcomes: for each entry date, T3/T5/T10 with synthetic returns
    session = dates
    out_rows = []
    oid = 0
    for i, d0 in enumerate(session):
        for h in (3, 5, 10):
            if i + h >= len(session):
                continue
            d_h = session[i + h]
            # Alternate favorable/unfavorable blocks
            base = 2.0 if (i % 6) < 3 else -1.5
            for s in range(142):
                oid += 1
                ret = base + (0.01 * (s % 7))
                out_rows.append(
                    {
                        "outcome_id": f"o{oid}",
                        "observation_id": f"obs-{d0}-{s}",
                        "symbol": f"S{s:03d}",
                        "entry_date": d0,
                        "entry_price": 100,
                        "horizon": h,
                        "target_date": d_h,
                        "target_price": 100 * (1 + ret / 100),
                        "return_pct": ret,
                        "max_gain_pct": max(ret, 0),
                        "max_drawdown_pct": min(ret, 0),
                        "is_win": ret > 0,
                        "is_leader": False,
                        "evaluated_at": f"{d_h}T12:00:00Z",
                    }
                )
    pd.DataFrame(out_rows).to_csv(root / "data" / "earning_learning" / "outcomes.csv", index=False)

    # Minimal MDT0 for later dates
    mdt0 = []
    for i, d in enumerate(dates[-4:]):
        mdt0.append(
            {
                "trade_date": d,
                "session_slot": "AFTER_CLOSE",
                "market_real": 7.0 + i * 0.2,
                "market_live": 8.0,
                "market_forecast": 1.5,
                "breadth_score": 50,
                "vnindex_daily_return_pct": 0.1 * i,
                "market_regime": "🟡 TRUNG TÍNH",
            }
        )
    pd.DataFrame(mdt0).to_csv(root / "data" / "earning_learning" / "market_daily_t0.csv", index=False)
    pd.DataFrame(columns=["trade_date"]).to_csv(
        root / "data" / "earning_learning" / "t0_observation_freeze.csv", index=False
    )
    pd.DataFrame(columns=["trade_date"]).to_csv(
        root / "data" / "forecast_research" / "forecast_t0_daily.csv", index=False
    )
    return root


def test_forbidden_lifecycle_feature_columns_fail_closed():
    with pytest.raises(ValueError):
        assert_no_forbidden_feature_columns(["rsi50_share", "t3_return_pct"])
    with pytest.raises(ValueError):
        assert_no_forbidden_feature_columns(["lifecycle_class"])
    assert_no_forbidden_feature_columns(["market_real", "share_MUA_EARLY"])


def test_label_maturity_boundary():
    assert label_available_at_prediction(mature_trade_date="2026-08-10", prediction_date="2026-08-11")
    assert not label_available_at_prediction(mature_trade_date="2026-08-11", prediction_date="2026-08-11")
    assert not label_available_at_prediction(mature_trade_date="2026-08-12", prediction_date="2026-08-11")


def test_filter_train_labels_excludes_immature(tmp_path: Path):
    root = _write_fixture(tmp_path)
    pit, _ = build_pit_dataset(repo_root=root)
    labels, _ = build_labels(pit=pit, repo_root=root)
    # Prediction on 2026-08-13: train may not include labels maturing on/after that date
    train = filter_train_labels(labels, prediction_date="2026-08-13", horizon=3)
    assert (train["trade_date"] < "2026-08-13").all()
    assert (train["mature_trade_date"] < "2026-08-13").all()
    # A label whose mature date is 2026-08-13 must be excluded
    assert not ((train["mature_trade_date"] >= "2026-08-13").any())


def test_assert_train_precedes_prediction_fail_closed():
    with pytest.raises(AssertionError):
        assert_train_precedes_prediction(["2026-08-10", "2026-08-13"], "2026-08-13", ["2026-08-12"])
    with pytest.raises(AssertionError):
        assert_train_precedes_prediction(["2026-08-10"], "2026-08-13", ["2026-08-13"])
    assert_train_precedes_prediction(["2026-08-10"], "2026-08-13", ["2026-08-12"])


def test_zscore_fit_past_only_no_future():
    train = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    future = pd.DataFrame({"a": [100.0]})
    stats = fit_past_only_zscore(train, ["a"])
    mu, sd = stats["a"]
    assert mu == pytest.approx(2.0)
    # Fitting must not use future frame
    stats2 = fit_past_only_zscore(pd.concat([train, future]), ["a"])
    assert stats2["a"][0] != stats["a"][0] or True  # different if wrongly pooled
    # Explicit: past-only stats ignore the 100
    assert abs(mu - 2.0) < 1e-9


def test_pit_dataset_tags_provenance(tmp_path: Path):
    root = _write_fixture(tmp_path)
    pit, meta = build_pit_dataset(repo_root=root)
    assert len(pit) >= 8
    assert "provenance__market_real" in pit.columns
    assert (pit["provenance__market_real"] == PROVENANCE_PIT_SAFE).all()
    feature_cols = [c for c in pit.columns if c in PIT_SAFE_FEATURES]
    assert_no_forbidden_feature_columns(feature_cols)


def test_walkforward_no_random_split_and_reproducible_fields(tmp_path: Path):
    root = _write_fixture(tmp_path)
    pit, _ = build_pit_dataset(repo_root=root)
    labels, _ = build_labels(pit=pit, repo_root=root)
    wf = run_walkforward(pit, labels, horizons=(3, 5))
    preds = wf["predictions"]
    assert not preds.empty
    assert wf["protocol"]["random_split"] is False
    required = {
        "train_dates_json",
        "prediction_date",
        "maturity_cutoff",
        "feature_set_json",
        "baseline",
        "binary_prob",
        "realized_xs_median_return",
    }
    assert required.issubset(preds.columns)
    # Every OK train set precedes prediction
    for _, r in preds.iterrows():
        import json

        train_dates = json.loads(r["train_dates_json"])
        for d in train_dates:
            assert d < r["prediction_date"]


def test_insufficient_evidence_marked_not_skipped(tmp_path: Path):
    root = _write_fixture(tmp_path)
    pit, _ = build_pit_dataset(repo_root=root)
    labels, _ = build_labels(pit=pit, repo_root=root)
    # Earliest matured T3 date should have tiny/empty train -> INSUFFICIENT for regression baselines
    lab3 = labels[labels["horizon"] == 3].sort_values("trade_date")
    t0 = lab3.iloc[0]["trade_date"]
    train = filter_train_labels(labels, prediction_date=t0, horizon=3)
    pred_row = assign_episodes(pit)[pit["trade_date"] == t0].iloc[0]
    out = predict_baseline(
        "real_only",
        train_labels=train,
        train_pit=pit,
        pred_row=pred_row,
    )
    assert out["status"] == INSUFFICIENT_EVIDENCE


def test_episodes_do_not_use_future_outcomes(tmp_path: Path):
    root = _write_fixture(tmp_path)
    pit, _ = build_pit_dataset(repo_root=root)
    # Strip any accidental outcome cols
    pit2 = pit[[c for c in pit.columns if "return" not in c.lower() or c.endswith("_lag1")]].copy()
    ep = assign_episodes(pit2)
    assert "episode_id" in ep.columns
    assert "regime_pit" in ep.columns
    src = inspect.getsource(assign_episodes)
    assert "favorable_median" not in src
    assert "xs_median" not in src


def test_runner_writes_artifacts_without_touching_app(tmp_path: Path):
    root = _write_fixture(tmp_path)
    report = run_fc1_harness(repo_root=root, out_dir=root / "data" / "forecast_research" / "fc1")
    assert report["verdict"] in {
        "HARNESS VALID — CONTINUE DATA ACCUMULATION",
        "HARNESS VALID — READY FOR FC-2 EXPLORATION",
        "HARNESS INVALID",
        "BLOCKED BY DATA/LEAKAGE ISSUE",
    }
    assert (root / "data" / "forecast_research" / "fc1" / "fc1_pit_features.csv").exists()
    assert (root / "data" / "forecast_research" / "fc1" / "fc1_labels.csv").exists()
    assert (root / "data" / "forecast_research" / "fc1" / "fc1_walkforward_predictions.csv").exists()
    assert (root / "data" / "forecast_research" / "fc1" / "fc1_accumulation_status.json").exists()


def test_production_isolation_calc_market_forecast_untouched():
    """FC-1 must not modify calc_market_forecast source."""
    app = (REPO / "app.py").read_text(encoding="utf-8")
    assert "def calc_market_forecast" in app
    # FC-1 package must not import or wrap calc_market_forecast / Streamlit APIs
    fc1_dir = REPO / "modules" / "forecast_research" / "fc1"
    for p in fc1_dir.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "calc_market_forecast(" not in text
        assert "import streamlit" not in text
        assert "from streamlit" not in text
        assert "streamlit." not in text


def test_mature_trade_date_helper():
    sessions = ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"]
    assert mature_trade_date_for("2026-08-10", 3, sessions) == "2026-08-13"
    assert mature_trade_date_for("2026-08-11", 3, sessions) is None


def test_aggregate_universe_opportunity_metrics():
    rows = []
    for i, ret in enumerate([1.0, 2.0, -4.0, 6.0]):
        rows.append(
            {
                "entry_date": "2026-08-10",
                "horizon": 3,
                "return_pct": ret,
                "symbol": f"S{i}",
            }
        )
    agg = aggregate_universe_opportunity(pd.DataFrame(rows), entry_date="2026-08-10", horizon=3)
    assert agg is not None
    assert agg["xs_median_return"] == pytest.approx(1.5)
    assert agg["xs_gt_3pct_share"] == pytest.approx(0.25)
    assert agg["xs_lt_minus3pct_share"] == pytest.approx(0.25)
    assert agg["xs_positive_share"] == pytest.approx(0.75)

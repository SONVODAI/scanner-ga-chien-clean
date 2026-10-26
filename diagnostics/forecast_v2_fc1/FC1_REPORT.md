# Forecast V2 — FC-1 Research Harness Report

- Version: `forecast_v2_fc1_v1`
- Generated: `2026-08-25T14:19:10Z`
- **Verdict: HARNESS VALID — CONTINUE DATA ACCUMULATION**

## Dataset

- T0 coverage: `2026-07-23` → `2026-08-24` (27 dates)
- COMPLETE: 8 | PARTIAL: 19
- Label maturity: {"T3": {"matured_dates": 24, "gate": 40, "remaining_to_gate": 16, "gate_met": false}, "T5": {"matured_dates": 22, "gate": 30, "remaining_to_gate": 8, "gate_met": false}, "T10": {"matured_dates": 17, "gate": 20, "remaining_to_gate": 3, "gate_met": false}}

## Walk-forward protocol

- Expanding window; **no random K-fold**
- Train labels require `trade_date < t` and `mature_trade_date < t`
- Score only when outcome for `t` is matured in the label store

## Baseline leaderboard (do not over-interpret tiny N)

### T3
- Prediction dates: 24 | episodes: 7
- `unconditional`: status=OK binary_n=16 brier=0.2616908461219996 hit=0.4375 mae_n=16 mae=1.3461937996500368 interp=None
- `persistence`: status=OK binary_n=20 brier=0.5 hit=0.5 mae_n=20 mae=1.7808505316308287 interp=None
- `real_only`: status=OK binary_n=1 brier=1.0 hit=0.0 mae_n=1 mae=4.129206631039439 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `live_only`: status=OK binary_n=1 brier=1.0 hit=0.0 mae_n=1 mae=4.129206631039439 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `real_live`: status=OK binary_n=1 brier=1.0 hit=0.0 mae_n=1 mae=4.129206631039439 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `breadth_only`: status=OK binary_n=12 brier=0.24441836519541446 hit=0.4166666666666667 mae_n=12 mae=1.4639735004963195 interp=None
- `legacy_fc_only`: status=OK binary_n=10 brier=0.24570325602019616 hit=0.6 mae_n=10 mae=2.3635975324633565 interp=None
- `regime_pit`: status=OK binary_n=10 brier=0.22584084467120183 hit=0.6 mae_n=10 mae=1.2379608410113452 interp=None
- `composition_early_share`: status=OK binary_n=12 brier=0.18817131829700343 hit=0.6666666666666666 mae_n=12 mae=1.344879133857373 interp=None

### T5
- Prediction dates: 22 | episodes: 6
- `unconditional`: status=OK binary_n=12 brier=0.54658777962525 hit=0.4166666666666667 mae_n=12 mae=2.218872732256853 interp=None
- `persistence`: status=OK binary_n=16 brier=0.4375 hit=0.5625 mae_n=16 mae=2.2100042784998806 interp=None
- `real_only`: status=OK binary_n=0 brier=None hit=None mae_n=0 mae=None interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `live_only`: status=OK binary_n=0 brier=None hit=None mae_n=0 mae=None interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `real_live`: status=OK binary_n=0 brier=None hit=None mae_n=0 mae=None interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `breadth_only`: status=OK binary_n=8 brier=0.46216582761372543 hit=0.375 mae_n=8 mae=3.402959001829621 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `legacy_fc_only`: status=OK binary_n=6 brier=0.41508657725059833 hit=0.5 mae_n=6 mae=2.494906944935164 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `regime_pit`: status=OK binary_n=6 brier=0.33418367346938777 hit=0.6666666666666666 mae_n=6 mae=0.9672255626420737 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `composition_early_share`: status=OK binary_n=8 brier=0.5825547145822377 hit=0.25 mae_n=8 mae=2.8623675598251648 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT

### T10
- Prediction dates: 17 | episodes: 4
- **INSUFFICIENT_EVIDENCE**: T10 explicitly INSUFFICIENT_EVIDENCE for ranking (n_prediction_dates=17, max_baseline_ok=6)
- `unconditional`: status=OK binary_n=2 brier=0.5 hit=0.5 mae_n=2 mae=2.477397926624919 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `persistence`: status=OK binary_n=6 brier=0.8333333333333334 hit=0.16666666666666666 mae_n=6 mae=4.3061980459713505 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `real_only`: status=INSUFFICIENT_EVIDENCE binary_n=None brier=None hit=None mae_n=None mae=None interp=None
- `live_only`: status=INSUFFICIENT_EVIDENCE binary_n=None brier=None hit=None mae_n=None mae=None interp=None
- `real_live`: status=INSUFFICIENT_EVIDENCE binary_n=None brier=None hit=None mae_n=None mae=None interp=None
- `breadth_only`: status=INSUFFICIENT_EVIDENCE binary_n=None brier=None hit=None mae_n=None mae=None interp=None
- `legacy_fc_only`: status=INSUFFICIENT_EVIDENCE binary_n=None brier=None hit=None mae_n=None mae=None interp=None
- `regime_pit`: status=OK binary_n=1 brier=0.0 hit=1.0 mae_n=1 mae=2.061817218620865 interp=TINY_N_DO_NOT_RANK_AS_SIGNIFICANT
- `composition_early_share`: status=INSUFFICIENT_EVIDENCE binary_n=None brier=None hit=None mae_n=None mae=None interp=None

## Leakage audit

- lifecycle_forbidden_as_t0_features: **PASS**
- future_dates_excluded_from_feature_transforms: **PASS**
- rolling_norm_fit_past_only: **PASS**
- labels_unavailable_before_maturity: **PASS**
- safe_reconstructable_tagged: **PASS**
- no_future_outcome_columns_in_feature_matrix: **PASS**
- train_precedes_prediction: **PASS**

## Data accumulation

- Direction switches (T3 favorable_median): 7
- Gates met: {"T3": false, "T5": false, "T10": false, "switches": false}
- Note: No calendar ETA: trading-day scheduling not projected. Remaining counts are date deficits only.

## Production isolation

- No UI / Streamlit surface changes
- Legacy FORECAST heuristic function untouched
- REAL/LIVE/BUY/SELL/Edge Research untouched
- Legacy `market_forecast` field semantics unchanged (feature/baseline only)


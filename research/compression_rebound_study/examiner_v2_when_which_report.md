# Examiner V2 — WHEN / WHICH (clean trading-session clock)

Generated `2026-09-08T15:40:28Z` UTC. **Human-examiner research only.**
Not an edge. Not a rule. Not a production candidate list. No BUY/SELL recommendation.

Independent unit: **eligible market date**. Stock-days on the same date share one market episode.
Source: `compression_stock_research_clean_outcomes.csv`. Production T3/T5/T10 columns were not used for this study.
Eligible sessions in file: 31. Blind forward dates (no outcome inference): `2026-09-04, 2026-09-07, 2026-09-08`.
Percentile labels require ≥10 same-date mature clean-T5 names (so TOP10 can exist). This floor was not tuned.

## Executive summary

- Clean-clock T5 sample: **26** dates (last mature T0 `2026-08-27`). T3: 28 dates. T10: 21 dates.
- YẾU DẦN T5: median-of-date-medians 0.75; beat same-day universe median on 57.7% of 26 dates.
- RẤT YẾU T5: median-of-date-medians 1.24; beat same-day universe median on 42.1% of 19 dates.
- ĐANG HỒI T5: median-of-date-medians -0.05; beat same-day universe median on 30.8% of 26 dates.
- Low vs high within-date RS5 quintile (T5): median(date median_Q1 − median_Q5)=0.32; same sign on 61.5% of 26 dates.
- Low vs high within-date RS10 quintile (T5): median(date median_Q1 − median_Q5)=0.97; same sign on 84.6% of 26 dates.
- Low vs high within-date RSI14 quintile (T5): median(date median_Q1 − median_Q5)=0.69; same sign on 76.9% of 26 dates.
- Among YẾU DẦN names, T5_TOP20 vs other same-date YẾU DẦN — non-flat features with highest date-agreement (descriptive, not selected as a model):
  - RS5: lower_in_winners, median date-spread -0.798, agree 83.3% of 24 dates, single-episode sample
  - within-date RS5 percentile: lower_in_winners, median date-spread -0.069, agree 83.3% of 24 dates, single-episode sample
  - RSI14 change vs 3 sessions: lower_in_winners, median date-spread -0.820, agree 81.0% of 21 dates, single-episode sample
  - distance to EMA9 %: lower_in_winners, median date-spread -0.385, agree 79.2% of 24 dates, single-episode sample
  - drawdown vs prior-5 high close: lower_in_winners, median date-spread -0.939, agree 78.3% of 23 dates, single-episode sample
  - RSI14 change vs 5 sessions: lower_in_winners, median date-spread -1.560, agree 73.7% of 19 dates, single-episode sample
- Forward 2026-09-04 / 09-07 / 09-08 remain unlabeled. No conclusion is drawn from them.

## Clean-clock revalidation

For each health state and each eligible date with mature clean returns, the date contributes one mean, one median, one win rate. Cross-date summaries are medians of those date values. Stock-days are not pooled as independent trials.

| horizon | state | n_dates | med of date-means | med of date-medians | % dates > uni mean | % dates > uni median | med date winrate |
|---|---|---:|---:|---:|---:|---:|---:|
| T3 | 🌱 ĐANG HỒI | 28 | -0.25 | -0.15 | 32.1 | 32.1 | 0.4 |
| T3 | ⛔ RẤT YẾU | 21 | 2.15 | 1.82 | 71.4 | 66.7 | 0.8 |
| T3 | 🟡 TRUNG TÍNH | 28 | 0.30 | -0.24 | 42.9 | 32.1 | 0.4 |
| T3 | 🔴 YẾU | 28 | 0.47 | 0.42 | 53.6 | 60.7 | 0.5 |
| T3 | ⚠️ YẾU DẦN | 28 | 0.08 | 0.00 | 67.9 | 67.9 | 0.4 |
| T5 | 🌱 ĐANG HỒI | 26 | 0.10 | -0.05 | 19.2 | 30.8 | 0.5 |
| T5 | ⛔ RẤT YẾU | 19 | 1.47 | 1.24 | 47.4 | 42.1 | 0.6 |
| T5 | 🟡 TRUNG TÍNH | 26 | 0.55 | 0.21 | 50.0 | 38.5 | 0.5 |
| T5 | 🔴 YẾU | 26 | 1.11 | 0.52 | 53.8 | 50.0 | 0.5 |
| T5 | ⚠️ YẾU DẦN | 26 | 1.28 | 0.75 | 57.7 | 57.7 | 0.6 |
| T10 | 🌱 ĐANG HỒI | 21 | 0.08 | 0.00 | 14.3 | 28.6 | 0.5 |
| T10 | ⛔ RẤT YẾU | 18 | 0.61 | 0.48 | 50.0 | 50.0 | 0.6 |
| T10 | 🟡 TRUNG TÍNH | 21 | 1.18 | 0.82 | 38.1 | 42.9 | 0.6 |
| T10 | 🔴 YẾU | 21 | 1.51 | 1.17 | 52.4 | 38.1 | 0.7 |
| T10 | ⚠️ YẾU DẦN | 21 | 1.85 | 1.30 | 66.7 | 52.4 | 0.6 |

Within-date quintiles (Q1=lowest feature that day, Q5=highest). Spread = date-median return(Q1) − date-median return(Q5). Positive spread means the low quintile had the higher same-day median clean return.

| horizon | feature | n_dates | med(Q1−Q5 date-median) | % dates Q1>Q5 |
|---|---|---:|---:|---:|
| T3 | rs5 | 28 | 0.60 | 67.9 |
| T5 | rs5 | 26 | 0.32 | 61.5 |
| T10 | rs5 | 21 | 1.39 | 71.4 |
| T3 | rs10 | 28 | 0.66 | 75.0 |
| T5 | rs10 | 26 | 0.97 | 84.6 |
| T10 | rs10 | 21 | 1.81 | 81.0 |
| T3 | rsi14 | 28 | 0.81 | 67.9 |
| T5 | rsi14 | 26 | 0.69 | 76.9 |
| T10 | rsi14 | 21 | 1.40 | 81.0 |

T5 by market date (mature clean T5 only; n / median / winrate>0). Full T3/T10 live in `examiner_v2_date_level.csv`.

| date | ĐH n/med/wr | TT n/med/wr | YẾU n/med/wr | YĐ n/med/wr | RY n/med/wr | uni med |
|---|---|---|---|---|---|---:|
| 2026-07-23 | 4/0.69/0.50 | 4/-1.00/0.25 | 2/0.14/0.50 | 55/0.64/0.55 | 77/0.72/0.57 | 0.70 |
| 2026-07-24 | 3/0.39/0.67 | 12/-1.32/0.42 | 5/-1.15/0.20 | 41/0.47/0.51 | 81/1.24/0.63 | 0.80 |
| 2026-07-27 | 3/-0.28/0.33 | 8/0.61/0.75 | 4/3.09/1.00 | 54/5.08/0.87 | 73/6.37/0.96 | 5.75 |
| 2026-07-28 | 3/-0.93/0.33 | 10/3.58/0.90 | 10/2.84/0.70 | 63/5.20/0.90 | 56/7.00/1.00 | 5.45 |
| 2026-07-29 | 15/-0.09/0.47 | 40/1.17/0.70 | 20/2.72/0.70 | 55/1.57/0.80 | 12/5.53/0.75 | 1.57 |
| 2026-07-30 | 18/3.13/0.61 | 55/1.40/0.75 | 25/2.38/0.80 | 41/1.99/0.85 | 3/1.52/0.67 | 1.79 |
| 2026-07-31 | 25/1.81/0.68 | 35/3.02/0.94 | 31/3.62/0.90 | 49/3.91/0.90 | 2/7.67/0.50 | 3.38 |
| 2026-08-03 | 64/1.95/0.72 | 51/2.06/0.86 | 16/2.18/0.94 | 10/0.78/0.60 | 1/-5.59/0.00 | 1.87 |
| 2026-08-04 | 71/0.70/0.59 | 37/0.41/0.54 | 19/0.91/0.58 | 14/1.62/0.79 | 1/-3.52/0.00 | 0.68 |
| 2026-08-05 | 58/1.16/0.71 | 30/2.36/0.77 | 36/1.76/0.92 | 17/1.75/0.82 | 1/-2.86/0.00 | 1.74 |
| 2026-08-06 | 42/-0.27/0.48 | 42/0.00/0.48 | 15/0.30/0.53 | 40/0.71/0.62 | 3/3.64/0.67 | 0.38 |
| 2026-08-07 | 71/-2.31/0.20 | 44/-0.83/0.34 | 13/-1.35/0.31 | 13/-1.47/0.15 | 1/-2.24/0.00 | -1.96 |
| 2026-08-10 | 74/-2.07/0.20 | 42/-1.60/0.26 | 12/-3.08/0.17 | 13/-2.51/0.23 | 1/-2.96/0.00 | -2.15 |
| 2026-08-11 | 83/-2.07/0.29 | 32/-2.64/0.19 | 10/-3.37/0.00 | 17/-2.80/0.06 | — | -2.45 |
| 2026-08-12 | 80/-2.47/0.23 | 31/-2.74/0.10 | 20/-3.26/0.05 | 11/-3.12/0.09 | — | -2.96 |
| 2026-08-13 | 59/-1.89/0.31 | 20/-1.16/0.35 | 29/-1.83/0.14 | 34/-2.64/0.15 | — | -1.89 |
| 2026-08-14 | 36/1.35/0.61 | 19/1.07/0.68 | 21/1.28/0.71 | 64/2.33/0.84 | 2/0.38/0.50 | 1.83 |
| 2026-08-17 | 41/1.77/0.71 | 20/2.17/0.95 | 6/2.06/0.67 | 74/2.74/0.86 | 1/-0.76/0.00 | 2.43 |
| 2026-08-18 | 36/0.00/0.47 | 29/1.94/0.79 | 6/2.51/0.83 | 70/2.32/0.81 | 1/1.47/1.00 | 1.74 |
| 2026-08-19 | 25/0.54/0.60 | 24/2.46/0.83 | 5/5.57/1.00 | 84/3.60/0.90 | 4/2.55/1.00 | 2.88 |
| 2026-08-20 | 24/1.11/0.67 | 33/3.07/0.82 | 6/0.75/0.50 | 74/3.18/0.89 | 5/3.10/0.80 | 3.04 |
| 2026-08-21 | 73/0.27/0.56 | 42/0.00/0.43 | 16/0.00/0.44 | 9/-0.42/0.44 | 2/-0.23/0.50 | 0.07 |
| 2026-08-24 | 83/-1.24/0.23 | 32/-0.44/0.31 | 17/-1.22/0.24 | 10/-0.86/0.10 | — | -1.17 |
| 2026-08-25 | 55/-0.84/0.27 | 36/-0.51/0.31 | 31/-0.32/0.32 | 20/-1.24/0.20 | — | -0.80 |
| 2026-08-26 | 69/-3.17/0.16 | 33/-2.56/0.18 | 18/-1.82/0.22 | 22/-1.62/0.23 | — | -2.52 |
| 2026-08-27 | 49/-2.35/0.22 | 34/-2.87/0.12 | 27/-1.96/0.15 | 32/-1.35/0.28 | — | -2.10 |

This is a revalidation check only. A higher beat-rate for a weak state on the clean clock does **not** become a rule.

## WHEN findings

Breadth shares and 1/2/3-session changes are in `examiner_v2_date_level.csv`. HHI = Σ p² on the five state fractions (1 = one state has everyone; 0.20 = equal fifths). Entropy = −Σ p log2(p) (max log2(5) ≈ 2.32).

Inspected windows (not used to fit anything): 2026-08-13..08-20, 2026-08-28 onward, 2026-09-07 onward.

| date | %ĐH | %TT | %YẾU | %YĐ | %RY | %weak3 | Δweak3 d1 | HHI | dom | MR | VNIDX | YĐ T5 med | uni T5 med |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| 2026-07-23 | 2.8 | 2.8 | 1.4 | 38.7 | 54.2 | 94.4 | n/a | 0.45 | RAT_YEU | n/a | n/a | 0.64 | 0.70 |
| 2026-07-31 | 17.6 | 24.6 | 21.8 | 34.5 | 1.4 | 57.7 | 9.2 | 0.26 | YEU_DAN | n/a | n/a | 3.91 | 3.38 |
| 2026-08-06 | 29.6 | 29.6 | 10.6 | 28.2 | 2.1 | 40.8 | 2.8 | 0.27 | DANG_HOI | n/a | n/a | 0.71 | 0.38 |
| 2026-08-12 | 56.3 | 21.8 | 14.1 | 7.7 | 0.0 | 21.8 | 2.8 | 0.39 | DANG_HOI | n/a | n/a | -3.12 | -2.96 |
| 2026-08-13 | 41.5 | 14.1 | 20.4 | 23.9 | 0.0 | 44.4 | 22.5 | 0.29 | DANG_HOI | 7.0 | -1.57 | -2.64 | -1.89 |
| 2026-08-14 | 25.4 | 13.4 | 14.8 | 45.1 | 1.4 | 61.3 | 16.9 | 0.31 | YEU_DAN | 5.6 | -1.96 | 2.33 | 1.83 |
| 2026-08-17 | 28.9 | 14.1 | 4.2 | 52.1 | 0.7 | 57.0 | -4.2 | 0.38 | YEU_DAN | 6.2 | -0.02 | 2.74 | 2.43 |
| 2026-08-18 | 25.4 | 20.4 | 4.2 | 49.3 | 0.7 | 54.2 | -2.8 | 0.35 | YEU_DAN | 5.7 | 0.25 | 2.32 | 1.74 |
| 2026-08-19 | 17.6 | 16.9 | 3.5 | 59.2 | 2.8 | 65.5 | 11.3 | 0.41 | YEU_DAN | 5.0 | -0.31 | 3.60 | 2.88 |
| 2026-08-20 | 16.9 | 23.2 | 4.2 | 52.1 | 3.5 | 59.9 | -5.6 | 0.36 | YEU_DAN | 5.3 | -0.08 | 3.18 | 3.04 |
| 2026-08-21 | 51.4 | 29.6 | 11.3 | 6.3 | 1.4 | 19.0 | -40.8 | 0.37 | DANG_HOI | 9.0 | 2.00 | -0.42 | 0.07 |
| 2026-08-24 | 58.5 | 22.5 | 12.0 | 7.0 | 0.0 | 19.0 | -0.0 | 0.41 | DANG_HOI | 9.6 | 0.07 | -0.86 | -1.17 |
| 2026-08-25 | 38.7 | 25.4 | 21.8 | 14.1 | 0.0 | 35.9 | 16.9 | 0.28 | DANG_HOI | 7.4 | -0.04 | -1.24 | -0.80 |
| 2026-08-26 | 48.6 | 23.2 | 12.7 | 15.5 | 0.0 | 28.2 | -7.7 | 0.33 | DANG_HOI | n/a | n/a | -1.62 | -2.52 |
| 2026-08-27 | 34.5 | 23.9 | 19.0 | 22.5 | 0.0 | 41.5 | 13.4 | 0.26 | DANG_HOI | 8.3 | 0.53 | -1.35 | -2.10 |
| 2026-08-28 | 26.1 | 40.1 | 7.0 | 26.1 | 0.7 | 33.8 | -7.7 | 0.30 | TRUNG_TINH | 7.6 | -0.28 | n/a | n/a |
| 2026-09-03 | 28.9 | 22.5 | 5.6 | 40.8 | 2.1 | 48.6 | 14.8 | 0.30 | YEU_DAN | 6.3 | 0.32 | n/a | n/a |
| 2026-09-04 | 21.1 | 24.6 | 5.6 | 47.9 | 0.7 | 54.2 | 5.6 | 0.34 | YEU_DAN | 6.3 | 1.28 | n/a | n/a |
| 2026-09-07 | 14.1 | 16.9 | 3.5 | 62.7 | 2.8 | 69.0 | 14.8 | 0.44 | YEU_DAN | 4.3 | -1.92 | n/a | n/a |
| 2026-09-08 | 19.0 | 16.9 | 4.2 | 57.7 | 2.1 | 64.1 | -4.9 | 0.40 | YEU_DAN | 4.9 | 0.53 | n/a | n/a |

`market_transition` is unavailable and was not invented. 2026-09-04/07/08 outcome cells are blank by design.

## WHICH findings

Labels are **same-date percentiles of clean_T5_return** among mature names that day: T5_TOP20 / T5_TOP10 / T5_BOTTOM20. No absolute return cutoff.
Primary comparison: YẾU DẦN ∩ T5_TOP20 vs other YẾU DẦN on the **same date**. Robustness: YẾU, RẤT YẾU, combined weak, and vs T5_BOTTOM20.
Each date contributes one median(feature|winners) and one median(feature|others). The table below is the median of those date-level values, plus how often the date-level spread has the same sign as the overall median spread.

### YẾU DẦN · T5_TOP20 vs other same-date YẾU DẦN

| feature | n_dates | med spread | min | max | direction | % dates agree | episode flag |
|---|---:|---:|---:|---:|---|---:|---|
| previous session was ĐANG HỒI | 24 | 0.000 | 0.000 | 1.000 | flat | 91.7 | SINGLE_EPISODE_SAMPLE |
| RS5 | 24 | -0.798 | -6.715 | 2.825 | lower_in_winners | 83.3 | SINGLE_EPISODE_SAMPLE |
| within-date RS5 percentile | 24 | -0.069 | -0.197 | 0.199 | lower_in_winners | 83.3 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 3 sessions | 21 | -0.820 | -4.130 | 2.335 | lower_in_winners | 81.0 | SINGLE_EPISODE_SAMPLE |
| distance to EMA9 % | 24 | -0.385 | -1.238 | 1.820 | lower_in_winners | 79.2 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in RẤT YẾU | 23 | 0.000 | 0.000 | 1.000 | flat | 78.3 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-5 high close | 23 | -0.939 | -4.197 | 1.175 | lower_in_winners | 78.3 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 5 sessions | 19 | -1.560 | -6.470 | 6.310 | lower_in_winners | 73.7 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 3 sessions | 21 | -0.675 | -22.085 | 5.215 | lower_in_winners | 71.4 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 5 sessions | 14 | -880474.500 | -14540002.500 | 2831800.000 | lower_in_winners | 71.4 | SINGLE_EPISODE_SAMPLE |
| previous session was ĐANG HỒI/TRUNG TÍNH | 24 | 0.000 | 0.000 | 1.000 | flat | 70.8 | SINGLE_EPISODE_SAMPLE |
| distance to MA20 % | 24 | -0.373 | -4.566 | 4.178 | lower_in_winners | 70.8 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 1 session | 17 | -452979.000 | -4201979.500 | 2847079.500 | lower_in_winners | 70.6 | SINGLE_EPISODE_SAMPLE |
| OBV direction vs prior session | 17 | 0.000 | -1.000 | 2.000 | flat | 70.6 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 5 minus current | 23 | 0.069 | -0.336 | 0.586 | higher_in_winners | 69.6 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 1 session | 23 | -0.400 | -5.985 | 1.530 | lower_in_winners | 69.6 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-10 high close | 23 | -0.785 | -5.075 | 3.762 | lower_in_winners | 69.6 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 5 minus current | 23 | -0.028 | -0.292 | 0.268 | lower_in_winners | 65.2 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 5 sessions | 19 | -0.710 | -19.585 | 5.390 | lower_in_winners | 63.2 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 1 session | 23 | -0.350 | -7.535 | 2.920 | lower_in_winners | 60.9 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 1 session | 23 | -0.265 | -3.100 | 1.980 | lower_in_winners | 60.9 | SINGLE_EPISODE_SAMPLE |
| RSI14 | 24 | -0.265 | -8.215 | 10.540 | lower_in_winners | 58.3 | SINGLE_EPISODE_SAMPLE |
| volume / MA20 | 24 | 0.095 | -0.348 | 1.064 | higher_in_winners | 58.3 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 5 sessions | 19 | -0.325 | -4.690 | 9.495 | lower_in_winners | 57.9 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in ĐANG HỒI/TRUNG TÍNH | 23 | 0.000 | -1.000 | 4.000 | flat | 56.5 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 3 minus current | 23 | 0.053 | -0.234 | 0.870 | higher_in_winners | 56.5 | SINGLE_EPISODE_SAMPLE |
| volume vs prior session | 23 | 0.046 | -0.678 | 0.395 | higher_in_winners | 56.5 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 3 sessions | 16 | -1929639.500 | -5690293.000 | 2380183.000 | lower_in_winners | 56.2 | SINGLE_EPISODE_SAMPLE |
| RS10 | 24 | 0.140 | -6.345 | 6.180 | higher_in_winners | 54.2 | SINGLE_EPISODE_SAMPLE |
| within-date RS10 percentile | 24 | 0.007 | -0.208 | 0.560 | higher_in_winners | 54.2 | SINGLE_EPISODE_SAMPLE |
| RS10 pct minus RS5 pct | 24 | -0.005 | -0.148 | 0.620 | lower_in_winners | 54.2 | SINGLE_EPISODE_SAMPLE |
| within-date RSI14 percentile | 24 | -0.016 | -0.197 | 0.465 | lower_in_winners | 54.2 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 3 sessions | 21 | 0.005 | -9.815 | 4.895 | higher_in_winners | 52.4 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 3 minus current | 23 | 0.000 | -0.261 | 0.320 | higher_in_winners | 52.2 | SINGLE_EPISODE_SAMPLE |
| state changes in prior 5 sessions | 22 | 0.000 | -1.000 | 2.000 | flat | 50.0 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in YẾU DẦN | 23 | 0.000 | -3.000 | 1.500 | flat | 43.5 | SINGLE_EPISODE_SAMPLE |
| current-state streak | 24 | 0.000 | -2.000 | 1.000 | flat | 41.7 | SINGLE_EPISODE_SAMPLE |

### YẾU DẦN · T5_TOP10 vs other same-date YẾU DẦN

| feature | n_dates | med spread | min | max | direction | % dates agree | episode flag |
|---|---:|---:|---:|---:|---|---:|---|
| previous session was ĐANG HỒI | 22 | 0.000 | 0.000 | 1.000 | flat | 95.5 | SINGLE_EPISODE_SAMPLE |
| distance to EMA9 % | 22 | -0.356 | -1.103 | 0.860 | lower_in_winners | 81.8 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in RẤT YẾU | 21 | 0.000 | 0.000 | 1.000 | flat | 76.2 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 1 session | 21 | -0.355 | -5.985 | 1.875 | lower_in_winners | 76.2 | SINGLE_EPISODE_SAMPLE |
| OBV direction vs prior session | 15 | 0.000 | -1.000 | 2.000 | flat | 73.3 | SINGLE_EPISODE_SAMPLE |
| previous session was ĐANG HỒI/TRUNG TÍNH | 22 | 0.000 | 0.000 | 1.000 | flat | 72.7 | SINGLE_EPISODE_SAMPLE |
| RS5 | 22 | -0.438 | -6.715 | 1.780 | lower_in_winners | 72.7 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-5 high close | 21 | -0.916 | -4.197 | 1.167 | lower_in_winners | 71.4 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-10 high close | 21 | -0.785 | -5.075 | 3.110 | lower_in_winners | 71.4 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 5 sessions | 17 | -0.785 | -6.470 | 2.770 | lower_in_winners | 70.6 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 3 sessions | 19 | -1.295 | -5.250 | 2.070 | lower_in_winners | 68.4 | SINGLE_EPISODE_SAMPLE |
| within-date RS5 percentile | 22 | -0.044 | -0.290 | 0.111 | lower_in_winners | 68.2 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 5 minus current | 21 | 0.113 | -0.282 | 0.586 | higher_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 5 sessions | 12 | -1522401.250 | -14540002.500 | 2831800.000 | lower_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 5 sessions | 17 | -0.310 | -19.585 | 8.145 | lower_in_winners | 64.7 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 5 sessions | 17 | 0.245 | -5.350 | 9.830 | higher_in_winners | 64.7 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 3 sessions | 14 | -1139433.750 | -17782672.000 | 3309578.000 | lower_in_winners | 64.3 | SINGLE_EPISODE_SAMPLE |
| distance to MA20 % | 22 | -0.437 | -4.363 | 2.689 | lower_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 3 sessions | 19 | -0.590 | -22.085 | 6.375 | lower_in_winners | 63.2 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 1 session | 21 | -0.340 | -7.535 | 2.920 | lower_in_winners | 61.9 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 1 session | 21 | -0.350 | -1.770 | 3.100 | lower_in_winners | 61.9 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 3 minus current | 21 | 0.069 | -0.243 | 0.870 | higher_in_winners | 61.9 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 1 session | 15 | -173250.000 | -8871815.000 | 5620800.000 | lower_in_winners | 60.0 | SINGLE_EPISODE_SAMPLE |
| RS10 | 22 | -0.903 | -5.695 | 7.590 | lower_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| within-date RS10 percentile | 22 | -0.018 | -0.320 | 0.634 | lower_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| volume / MA20 | 22 | 0.051 | -0.348 | 1.064 | higher_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 5 minus current | 21 | -0.039 | -0.303 | 0.202 | lower_in_winners | 57.1 | SINGLE_EPISODE_SAMPLE |
| volume vs prior session | 21 | 0.062 | -0.689 | 0.339 | higher_in_winners | 57.1 | SINGLE_EPISODE_SAMPLE |
| RSI14 | 22 | 0.707 | -10.090 | 10.390 | higher_in_winners | 54.5 | SINGLE_EPISODE_SAMPLE |
| within-date RSI14 percentile | 22 | 0.033 | -0.232 | 0.465 | higher_in_winners | 54.5 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 3 sessions | 19 | 0.265 | -9.815 | 7.100 | higher_in_winners | 52.6 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 3 minus current | 21 | 0.014 | -0.387 | 0.285 | higher_in_winners | 52.4 | SINGLE_EPISODE_SAMPLE |
| current-state streak | 22 | 0.000 | -1.500 | 0.500 | flat | 50.0 | SINGLE_EPISODE_SAMPLE |
| RS10 pct minus RS5 pct | 22 | 0.009 | -0.250 | 0.620 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| state changes in prior 5 sessions | 20 | 0.250 | -1.000 | 2.000 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in ĐANG HỒI/TRUNG TÍNH | 21 | 0.000 | -1.000 | 3.000 | flat | 47.6 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in YẾU DẦN | 21 | 0.000 | -3.000 | 1.000 | flat | 42.9 | SINGLE_EPISODE_SAMPLE |

### YẾU DẦN · T5_TOP20 vs T5_BOTTOM20

| feature | n_dates | med spread | min | max | direction | % dates agree | episode flag |
|---|---:|---:|---:|---:|---|---:|---|
| previous session was ĐANG HỒI | 24 | 0.000 | 0.000 | 1.000 | flat | 91.7 | SINGLE_EPISODE_SAMPLE |
| previous session was ĐANG HỒI/TRUNG TÍNH | 24 | 0.000 | 0.000 | 1.000 | flat | 70.8 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 1 session | 17 | -475251.500 | -4173327.500 | 5091900.000 | lower_in_winners | 70.6 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 5 minus current | 23 | -0.067 | -0.384 | 0.338 | lower_in_winners | 69.6 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-10 high close | 23 | -0.457 | -5.357 | 6.830 | lower_in_winners | 69.6 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 5 sessions | 19 | -2.100 | -21.840 | 9.970 | lower_in_winners | 68.4 | SINGLE_EPISODE_SAMPLE |
| RS5 | 24 | -0.610 | -6.640 | 3.225 | lower_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| within-date RS5 percentile | 24 | -0.056 | -0.303 | 0.206 | lower_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| RSI14 | 24 | -2.020 | -11.350 | 14.020 | lower_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 5 minus current | 23 | 0.169 | -0.505 | 0.972 | higher_in_winners | 65.2 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 3 minus current | 23 | -0.067 | -0.433 | 0.345 | lower_in_winners | 65.2 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-5 high close | 23 | -1.056 | -3.739 | 3.516 | lower_in_winners | 65.2 | SINGLE_EPISODE_SAMPLE |
| volume vs prior session | 23 | -0.052 | -0.663 | 0.405 | lower_in_winners | 65.2 | SINGLE_EPISODE_SAMPLE |
| OBV direction vs prior session | 17 | 0.000 | -1.000 | 2.000 | flat | 64.7 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 5 sessions | 19 | -1.200 | -16.560 | 12.530 | lower_in_winners | 63.2 | SINGLE_EPISODE_SAMPLE |
| RS10 pct minus RS5 pct | 24 | 0.023 | -0.364 | 0.620 | higher_in_winners | 62.5 | SINGLE_EPISODE_SAMPLE |
| within-date RSI14 percentile | 24 | -0.093 | -0.345 | 0.514 | lower_in_winners | 62.5 | SINGLE_EPISODE_SAMPLE |
| distance to EMA9 % | 24 | -0.268 | -1.487 | 2.908 | lower_in_winners | 62.5 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 3 sessions | 16 | -1123790.000 | -5852643.000 | 14388900.000 | lower_in_winners | 62.5 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 3 sessions | 21 | 1.580 | -11.530 | 10.830 | higher_in_winners | 61.9 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 3 sessions | 21 | -0.580 | -8.220 | 13.790 | lower_in_winners | 61.9 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in RẤT YẾU | 23 | 0.000 | -2.000 | 4.000 | flat | 60.9 | SINGLE_EPISODE_SAMPLE |
| RS10 | 24 | -0.170 | -9.390 | 9.640 | lower_in_winners | 58.3 | SINGLE_EPISODE_SAMPLE |
| within-date RS10 percentile | 24 | -0.028 | -0.451 | 0.563 | lower_in_winners | 58.3 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 5 sessions | 19 | 0.310 | -7.000 | 6.985 | higher_in_winners | 57.9 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 3 sessions | 21 | -1.000 | -23.170 | 8.400 | lower_in_winners | 57.1 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in YẾU DẦN | 23 | -0.500 | -3.000 | 1.500 | lower_in_winners | 56.5 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 1 session | 23 | -0.380 | -7.760 | 4.660 | lower_in_winners | 56.5 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 3 minus current | 23 | 0.042 | -0.403 | 0.986 | higher_in_winners | 56.5 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 1 session | 23 | -0.245 | -5.050 | 4.630 | lower_in_winners | 56.5 | SINGLE_EPISODE_SAMPLE |
| distance to MA20 % | 24 | -0.223 | -6.335 | 5.591 | lower_in_winners | 54.2 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in ĐANG HỒI/TRUNG TÍNH | 23 | 0.000 | -3.000 | 3.000 | flat | 52.2 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 1 session | 23 | 0.370 | -4.590 | 2.980 | higher_in_winners | 52.2 | SINGLE_EPISODE_SAMPLE |
| volume / MA20 | 24 | 0.014 | -0.537 | 0.918 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 5 sessions | 14 | -833825.250 | -13173355.000 | 11677600.000 | lower_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| current-state streak | 24 | 0.000 | -3.000 | 1.500 | flat | 45.8 | SINGLE_EPISODE_SAMPLE |
| state changes in prior 5 sessions | 22 | 0.000 | -1.000 | 2.000 | flat | 31.8 | SINGLE_EPISODE_SAMPLE |

### Robustness · YẾU · T5_TOP20 vs other YẾU

| feature | n_dates | med spread | min | max | direction | % dates agree | episode flag |
|---|---:|---:|---:|---:|---|---:|---|
| current-state streak | 22 | 0.000 | -1.000 | 1.000 | flat | 81.8 | SINGLE_EPISODE_SAMPLE |
| previous session was ĐANG HỒI | 22 | 0.000 | -1.000 | 1.000 | flat | 81.8 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 3 minus current | 22 | -0.071 | -0.213 | 0.521 | lower_in_winners | 72.7 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-5 high close | 22 | -0.412 | -4.721 | 1.631 | lower_in_winners | 72.7 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 5 sessions | 20 | 0.383 | -6.185 | 12.355 | higher_in_winners | 70.0 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 5 sessions | 20 | 1.623 | -6.475 | 11.270 | higher_in_winners | 70.0 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in RẤT YẾU | 22 | 0.000 | -1.000 | 1.500 | flat | 68.2 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 5 minus current | 22 | 0.067 | -0.526 | 0.275 | higher_in_winners | 68.2 | SINGLE_EPISODE_SAMPLE |
| OBV direction vs prior session | 18 | 0.000 | -2.000 | 1.000 | flat | 66.7 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 5 sessions | 14 | 599204.500 | -13756137.500 | 9092582.000 | higher_in_winners | 64.3 | SINGLE_EPISODE_SAMPLE |
| RS5 | 22 | 0.340 | -1.920 | 4.775 | higher_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 1 session | 22 | 0.405 | -7.110 | 2.500 | higher_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| within-date RS5 percentile | 22 | 0.060 | -0.162 | 0.359 | higher_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 5 minus current | 22 | -0.039 | -0.264 | 0.521 | lower_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| RSI14 | 22 | -0.652 | -8.510 | 7.940 | lower_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 1 session | 22 | -0.488 | -3.800 | 3.960 | lower_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| within-date RSI14 percentile | 22 | -0.037 | -0.338 | 0.248 | lower_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-10 high close | 22 | -0.588 | -4.554 | 1.631 | lower_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| distance to MA20 % | 22 | -0.498 | -5.713 | 4.112 | lower_in_winners | 63.6 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 5 sessions | 20 | 1.160 | -4.205 | 9.325 | higher_in_winners | 60.0 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 3 sessions | 22 | 0.195 | -6.880 | 10.380 | higher_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 3 sessions | 22 | 1.457 | -12.880 | 7.695 | higher_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 3 minus current | 22 | 0.046 | -0.407 | 0.201 | higher_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 3 sessions | 22 | -0.818 | -10.200 | 10.140 | lower_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| volume / MA20 | 22 | -0.023 | -1.623 | 1.861 | lower_in_winners | 59.1 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 3 sessions | 16 | 370304.000 | -18376597.000 | 13196902.000 | higher_in_winners | 56.2 | SINGLE_EPISODE_SAMPLE |
| RS10 | 22 | -0.835 | -4.290 | 9.220 | lower_in_winners | 54.5 | SINGLE_EPISODE_SAMPLE |
| within-date RS10 percentile | 22 | -0.070 | -0.338 | 0.433 | lower_in_winners | 54.5 | SINGLE_EPISODE_SAMPLE |
| volume vs prior session | 22 | -0.083 | -2.066 | 1.146 | lower_in_winners | 54.5 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in ĐANG HỒI/TRUNG TÍNH | 22 | 0.250 | -2.000 | 3.000 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in YẾU DẦN | 22 | -0.250 | -1.000 | 4.000 | lower_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| previous session was ĐANG HỒI/TRUNG TÍNH | 22 | 0.000 | -1.000 | 1.000 | flat | 50.0 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 1 session | 22 | 0.130 | -3.180 | 3.110 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| RS10 pct minus RS5 pct | 22 | 0.021 | -0.574 | 0.289 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| distance to EMA9 % | 22 | 0.031 | -2.260 | 1.674 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 1 session | 18 | -19674.750 | -4038100.000 | 18187819.000 | lower_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| state changes in prior 5 sessions | 22 | 0.000 | -2.000 | 1.500 | flat | 36.4 | SINGLE_EPISODE_SAMPLE |

### Robustness · RẤT YẾU · T5_TOP20 vs other RẤT YẾU

| feature | n_dates | med spread | min | max | direction | % dates agree | episode flag |
|---|---:|---:|---:|---:|---|---:|---|
| previous session was ĐANG HỒI | 10 | 0.000 | 0.000 | 0.000 | flat | 100.0 | SINGLE_EPISODE_SAMPLE |
| previous session was ĐANG HỒI/TRUNG TÍNH | 10 | 0.000 | 0.000 | 0.000 | flat | 100.0 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 3 minus current | 9 | -0.352 | -1.373 | 0.296 | lower_in_winners | 88.9 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 5 minus current | 9 | -0.077 | -1.366 | 0.137 | lower_in_winners | 88.9 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 3 sessions | 7 | 3.565 | -0.385 | 19.810 | higher_in_winners | 85.7 | SINGLE_EPISODE_SAMPLE |
| RS10 pct minus RS5 pct | 10 | -0.067 | -0.592 | 0.053 | lower_in_winners | 80.0 | SINGLE_EPISODE_SAMPLE |
| within-date RSI14 percentile | 10 | -0.023 | -0.144 | 0.109 | lower_in_winners | 80.0 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 5 sessions | 5 | 5.580 | -3.785 | 25.370 | higher_in_winners | 80.0 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 5 sessions | 5 | 12.085 | -3.970 | 14.135 | higher_in_winners | 80.0 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 5 sessions | 5 | 6.145 | -2.935 | 14.790 | higher_in_winners | 80.0 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in ĐANG HỒI/TRUNG TÍNH | 9 | 0.000 | 0.000 | 0.500 | flat | 77.8 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 3 minus current | 9 | -0.028 | -0.127 | 0.123 | lower_in_winners | 77.8 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 5 minus current | 9 | -0.070 | -0.574 | 0.401 | lower_in_winners | 77.8 | SINGLE_EPISODE_SAMPLE |
| RS5 | 10 | 1.165 | -0.920 | 4.860 | higher_in_winners | 70.0 | SINGLE_EPISODE_SAMPLE |
| within-date RS5 percentile | 10 | 0.054 | -0.070 | 0.465 | higher_in_winners | 70.0 | SINGLE_EPISODE_SAMPLE |
| RSI14 | 10 | -0.427 | -5.630 | 23.230 | lower_in_winners | 70.0 | SINGLE_EPISODE_SAMPLE |
| volume / MA20 | 10 | -0.079 | -1.381 | 0.136 | lower_in_winners | 70.0 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 1 session | 9 | 0.460 | -2.515 | 4.350 | higher_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 1 session | 3 | -926000.000 | -13943721.000 | 1458750.000 | lower_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 3 sessions | 3 | 1701600.000 | -45228960.500 | 3534500.000 | higher_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| OBV direction vs prior session | 3 | -1.000 | -2.000 | 0.000 | lower_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| RS10 | 10 | -1.360 | -16.210 | 5.080 | lower_in_winners | 60.0 | SINGLE_EPISODE_SAMPLE |
| within-date RS10 percentile | 10 | -0.051 | -0.239 | 0.099 | lower_in_winners | 60.0 | SINGLE_EPISODE_SAMPLE |
| distance to EMA9 % | 10 | -0.033 | -7.899 | 2.548 | lower_in_winners | 60.0 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 3 sessions | 7 | -1.100 | -6.775 | 7.420 | lower_in_winners | 57.1 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 3 sessions | 7 | 2.050 | -6.810 | 4.315 | higher_in_winners | 57.1 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 1 session | 9 | -0.050 | -6.990 | 1.160 | lower_in_winners | 55.6 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 1 session | 9 | -0.315 | -2.955 | 1.290 | lower_in_winners | 55.6 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-5 high close | 9 | -0.819 | -8.280 | 4.419 | lower_in_winners | 55.6 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-10 high close | 9 | -0.819 | -8.280 | 4.681 | lower_in_winners | 55.6 | SINGLE_EPISODE_SAMPLE |
| volume vs prior session | 9 | -0.037 | -2.971 | 0.300 | lower_in_winners | 55.6 | SINGLE_EPISODE_SAMPLE |
| current-state streak | 10 | 0.000 | -5.000 | 1.000 | flat | 50.0 | SINGLE_EPISODE_SAMPLE |
| distance to MA20 % | 10 | 0.094 | -17.874 | 2.661 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| state changes in prior 5 sessions | 8 | 0.250 | -1.000 | 2.000 | higher_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 5 sessions | 2 | -48775836.000 | -100888572.000 | 3336900.000 | lower_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in RẤT YẾU | 9 | 0.000 | -3.000 | 2.000 | flat | 44.4 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in YẾU DẦN | 9 | 0.000 | -2.000 | 2.000 | flat | 44.4 | SINGLE_EPISODE_SAMPLE |

### Robustness · combined weak · T5_TOP20 vs other weak

| feature | n_dates | med spread | min | max | direction | % dates agree | episode flag |
|---|---:|---:|---:|---:|---|---:|---|
| previous session was ĐANG HỒI | 26 | 0.000 | 0.000 | 1.000 | flat | 92.3 | SINGLE_EPISODE_SAMPLE |
| distance to EMA9 % | 26 | -0.467 | -1.293 | 1.054 | lower_in_winners | 76.9 | SINGLE_EPISODE_SAMPLE |
| OBV direction vs prior session | 19 | 0.000 | -1.000 | 1.000 | flat | 73.7 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in RẤT YẾU | 25 | 0.000 | -1.000 | 1.500 | flat | 68.0 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-5 high close | 25 | -0.635 | -2.677 | 2.295 | lower_in_winners | 68.0 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 5 sessions | 15 | -112343.500 | -8846376.000 | 3105700.000 | lower_in_winners | 66.7 | SINGLE_EPISODE_SAMPLE |
| current-state streak | 26 | 0.000 | -1.000 | 1.500 | flat | 65.4 | SINGLE_EPISODE_SAMPLE |
| RSI14 | 26 | -0.830 | -7.110 | 4.160 | lower_in_winners | 65.4 | SINGLE_EPISODE_SAMPLE |
| within-date RSI14 percentile | 26 | -0.037 | -0.222 | 0.232 | lower_in_winners | 65.4 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 3 sessions | 23 | -0.955 | -4.150 | 6.525 | lower_in_winners | 65.2 | SINGLE_EPISODE_SAMPLE |
| previous session was ĐANG HỒI/TRUNG TÍNH | 26 | 0.000 | 0.000 | 1.000 | flat | 61.5 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 3 sessions | 23 | -0.435 | -11.520 | 10.975 | lower_in_winners | 60.9 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 3 sessions | 23 | 0.330 | -8.350 | 8.160 | higher_in_winners | 60.9 | SINGLE_EPISODE_SAMPLE |
| drawdown vs prior-10 high close | 25 | -0.317 | -3.052 | 1.365 | lower_in_winners | 60.0 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 3 sessions | 17 | -83806.000 | -7821161.000 | 2319110.500 | lower_in_winners | 58.8 | SINGLE_EPISODE_SAMPLE |
| RS10 | 26 | 0.087 | -6.010 | 3.505 | higher_in_winners | 57.7 | SINGLE_EPISODE_SAMPLE |
| within-date RS10 percentile | 26 | 0.015 | -0.236 | 0.338 | higher_in_winners | 57.7 | SINGLE_EPISODE_SAMPLE |
| distance to MA20 % | 26 | -0.311 | -5.265 | 1.193 | lower_in_winners | 57.7 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in ĐANG HỒI/TRUNG TÍNH | 25 | 0.000 | -0.500 | 2.000 | flat | 56.0 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 1 session | 25 | -0.190 | -1.775 | 3.825 | lower_in_winners | 56.0 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 3 minus current | 25 | 0.048 | -0.477 | 0.433 | higher_in_winners | 56.0 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 3 minus current | 25 | -0.014 | -0.197 | 0.257 | lower_in_winners | 56.0 | SINGLE_EPISODE_SAMPLE |
| best RS10 pct in prior 5 minus current | 25 | -0.014 | -0.338 | 0.296 | lower_in_winners | 56.0 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 1 session | 25 | -0.300 | -5.410 | 3.300 | lower_in_winners | 56.0 | SINGLE_EPISODE_SAMPLE |
| volume vs prior session | 25 | -0.013 | -0.522 | 0.247 | lower_in_winners | 56.0 | SINGLE_EPISODE_SAMPLE |
| state changes in prior 5 sessions | 24 | 0.000 | -1.000 | 1.000 | flat | 54.2 | SINGLE_EPISODE_SAMPLE |
| RS5 | 26 | -0.070 | -3.140 | 6.415 | lower_in_winners | 53.8 | SINGLE_EPISODE_SAMPLE |
| within-date RS5 percentile | 26 | -0.003 | -0.204 | 0.440 | lower_in_winners | 53.8 | SINGLE_EPISODE_SAMPLE |
| RS10 pct minus RS5 pct | 26 | -0.004 | -0.556 | 0.252 | lower_in_winners | 53.8 | SINGLE_EPISODE_SAMPLE |
| OBV change vs 1 session | 19 | -315700.000 | -4193979.500 | 12732246.000 | lower_in_winners | 52.6 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 5 sessions | 21 | -0.025 | -8.800 | 12.970 | lower_in_winners | 52.4 | SINGLE_EPISODE_SAMPLE |
| RS10 change vs 5 sessions | 21 | 0.280 | -5.255 | 12.760 | higher_in_winners | 52.4 | SINGLE_EPISODE_SAMPLE |
| RSI14 change vs 5 sessions | 21 | 0.255 | -8.150 | 6.035 | higher_in_winners | 52.4 | SINGLE_EPISODE_SAMPLE |
| prior-5 sessions in YẾU DẦN | 25 | 0.000 | -2.000 | 1.000 | flat | 52.0 | SINGLE_EPISODE_SAMPLE |
| RS5 change vs 1 session | 25 | -0.130 | -2.980 | 4.790 | lower_in_winners | 52.0 | SINGLE_EPISODE_SAMPLE |
| best RS5 pct in prior 5 minus current | 25 | 0.004 | -0.630 | 0.352 | higher_in_winners | 52.0 | SINGLE_EPISODE_SAMPLE |
| volume / MA20 | 26 | -0.007 | -0.322 | 0.922 | lower_in_winners | 50.0 | SINGLE_EPISODE_SAMPLE |

Market Real / regime / breadth percentages are **constant within a date**, so they cannot distinguish winners from others on the same date. They belong to WHEN, not WHICH.

## Temporary compression vs structural weakness

Descriptive contrast only. No composite score was built.
If “short-term compressed on a healthier base” were visible at T0, YẾU DẦN T5_TOP20 names would tend to show, versus other same-date YẾU DẦN:

- lower current RS5 rank than RS10 rank (positive `rs10_minus_rs5_pct`)
- a drop from a better RS rank in the prior 3/5 sessions (`rs5_rank_drop_*` > 0)
- shorter current-state streak / more prior healthy states
- shallower 10-session drawdown than chronic weakness

| test piece | direction | med spread | % dates agree | n_dates | concentrated? |
|---|---|---:|---:|---:|---|
| within-date RS5 percentile | lower_in_winners | -0.069 | 83.3 | 24 | no |
| within-date RS10 percentile | higher_in_winners | 0.007 | 54.2 | 24 | no |
| RS10 pct minus RS5 pct | lower_in_winners | -0.005 | 54.2 | 24 | no |
| best RS5 pct in prior 3 minus current | higher_in_winners | 0.053 | 56.5 | 23 | no |
| best RS5 pct in prior 5 minus current | higher_in_winners | 0.069 | 69.6 | 23 | no |
| best RS10 pct in prior 3 minus current | higher_in_winners | 0.000 | 52.2 | 23 | no |
| best RS10 pct in prior 5 minus current | lower_in_winners | -0.028 | 65.2 | 23 | no |
| current-state streak | flat | 0.000 | 41.7 | 24 | no |
| prior-5 sessions in ĐANG HỒI/TRUNG TÍNH | flat | 0.000 | 56.5 | 23 | no |
| prior-5 sessions in RẤT YẾU | flat | 0.000 | 78.3 | 23 | no |
| drawdown vs prior-5 high close | lower_in_winners | -0.939 | 78.3 | 23 | no |
| drawdown vs prior-10 high close | lower_in_winners | -0.785 | 69.6 | 23 | no |
| distance to EMA9 % | lower_in_winners | -0.385 | 79.2 | 24 | no |
| distance to MA20 % | lower_in_winners | -0.373 | 70.8 | 24 | no |
| volume / MA20 | higher_in_winners | 0.095 | 58.3 | 24 | no |
| OBV direction vs prior session | flat | 0.000 | 70.6 | 17 | no |

Agreement across dates is the claim-check. A single large episode can still dominate; see the next section.

## Date-level robustness

Episode definition: a new episode starts when the gap between consecutive eligible sessions exceeds **4 calendar days** (weekend-tolerant; the National Day hole splits 2026-08-28 from 2026-09-03).

Date-level effect `e_d` = median(feature | winners, date d) − median(feature | others, date d).
Episode L1 share = Σ_d∈ep |e_d| / Σ_all |e_d|.
EPISODE_CONCENTRATED if max episode L1 share > 50%, **or** dropping that episode flips the sign of median(e_d).
Leave-one-window-out columns in `examiner_v2_feature_comparison.csv` recompute median(e_d) after removing 2026-08-13..08-20, 2026-08-28 onward, or 2026-09-07 onward. Those windows were listed in the brief; they were not chosen by scanning outcomes.

YẾU DẦN T5_TOP20 vs others: **0/37** features flagged EPISODE_CONCENTRATED.
Episode ids present on T5-mature dates: [1].

## Episode concentration warnings

- Almost all mature clean-T5 dates sit in **one** pre–National Day episode (2026-07-23..2026-08-28). Post-holiday T5 is immature, so leave-one-episode-out is weak.
- Results that survive only inside 2026-08-13..08-20 should be treated as that window’s description, not a repeated market regularity.
- 2026-08-26 is a snapshot-fill session (observations missed it). It is in the clean calendar but is a lower-quality T0 print.

## Data limitations / PIT warnings

- T0 features prefer freeze-on-overlap from the parent extract; 2026-08-28 freeze is midday.
- Clean T+n uses stored panel closes on confirmed sessions only. No missing close was interpolated.
- No official HOSE gazette file; National Day window is evidence-derived (see Examiner V1 audit §14).
- RS5/RS10 are own-price changes, not vs VNINDEX.
- Within-date percentiles use the full eligible universe that day (T0), then labels use mature clean T5 only.
- Weekend observation rows are excluded from this study’s date unit.
- `market_transition` does not exist historically.
- Small N_dates (T10 shorter than T3). Date-agreement can look high by chance.

## BLIND_FORWARD_EPISODES

T0/breadth only. **No outcome interpretation.**

| date | n | %ĐH | %TT | %YẾU | %YĐ | %RY | %weak3 | ΔYĐ d1 | Δweak3 d1 | dom | HHI | MR | regime | VNIDX |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---:|
| 2026-09-04 | 142 | 21.1 | 24.6 | 5.6 | 47.9 | 0.7 | 54.2 | 7.0 | 5.6 | YEU_DAN | 0.34 | 6.3 | 🟡 TRUNG TÍNH | 1.28 |
| 2026-09-07 | 142 | 14.1 | 16.9 | 3.5 | 62.7 | 2.8 | 69.0 | 14.8 | 14.8 | YEU_DAN | 0.44 | 4.3 | 🔴 MÙA ĐÔNG | -1.92 |
| 2026-09-08 | 142 | 19.0 | 16.9 | 4.2 | 57.7 | 2.1 | 64.1 | -4.9 | -4.9 | YEU_DAN | 0.40 | 4.9 | 🔴 MÙA ĐÔNG | 0.53 |

YẾU DẦN T0 location on blind dates (features only):

| date | n YĐ | med RS5 | med RS10 | med RSI14 | med RS5 pct | med dd10 | med vol_ratio20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-04 | 68 | -2.07 | -0.92 | 43.38 | 0.28 | -3.55 | 0.82 |
| 2026-09-07 | 89 | -3.17 | -0.29 | 43.16 | 0.38 | -4.24 | 0.91 |
| 2026-09-08 | 82 | -2.87 | -0.14 | 43.38 | 0.37 | -4.45 | 0.65 |

These rows are context for a later examiner pass after clean T5 matures. They were not used to choose features.

## What remains unknown

- Whether any WHEN pattern repeats outside this single July–August 2026 stretch.
- Whether 2026-08-26 snapshot T0 is comparable to freeze T0.
- Whether “good rebound” should be T5, T3, or path T3→T5→T10. This file labels on T5 only.
- Foreign flow, WMA45, OHLC structure, and official holiday gazette.
- Causal structure: breadth expansion and single-name rebound can be the same market move.
- Any out-of-sample period after 2026-09-08.

Do not load these tables into Edge Memory, discovery, or the BOT.

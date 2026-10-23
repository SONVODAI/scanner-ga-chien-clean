# Setup × Intraday P×V × Forward Outcome

Research date: 2026-09-16  
Scope: **DATA, not rules.** Isolated under `research/setup_intraday_pxv_forward/`.  
Production: **not modified.** Candidate Router, Elite, Rotation, scanner GROUP_RANK, frozen P×V interpreter, Telegram, live-shadow, Streamlit, VPS, `/opt/mrbot-camera` untouched.

**Headline:** Frozen 5m P×V × setup × forward outcome is **NOT TESTABLE** in this workspace because canonical Camera 5m parquet is absent. Setup × daily T3/T5/T10 **controls** can be tabulated from EOD freeze labels (quarantined: not intra-day as-of). No BUY/SELL rules.

---

## Observation unit

| Item | Value |
| --- | --- |
| Preferred scientific unit | `symbol × session_date × setup_asof × 5m_bar_asof` |
| Status | **NOT TESTABLE in this workspace** |
| Fallback (P×V stripped) | `symbol × trade_date × setup_label_with_chronology_class` |
| Fallback status | PARTIAL / QUARANTINE for EOD freeze group; UNSAFE for last-wins / T+1 observation group |
| Production contracts | unchanged |

Do not treat a later saved group as the group known at an earlier 5m bar.

---

## A. Data inventory

Camera resolution: `{"found": [], "missing": ["/var/lib/mrbot/intraday_memory", "/workspace/intraday_memory", "/workspace/data/intraday_pxv_v1"], "canonical_5m_available": false, "verdict": "UNSAFE FOR THIS STUDY"}`

- **pattern_history.csv (root GENESIS_V24)**: present=True rows=35616 dates=2026-07-02→2026-09-16 (n_dates=48) symbols=151 
- **group_evolution_history.csv**: present=True rows=11624 dates=2026-05-26→2026-09-16 (n_dates=78) symbols=164 
- **buy_elite_learning_history.csv**: present=True rows=996 dates=2026-06-25→2026-09-16 (n_dates=53) symbols=138 
- **t0_observation_freeze.csv**: present=True rows=2702 dates=2026-08-13→2026-09-16 (n_dates=20) symbols=142 
- **observations.csv**: present=True rows=5400 dates=2026-07-23→2026-09-16 (n_dates=39) symbols=142 
- **outcomes.csv**: present=True rows=13644 dates=2026-07-23→2026-09-10 (n_dates=36) symbols=142 
- **pattern_lifecycle.csv**: present=True rows=4974 dates=2026-07-23→2026-09-10 (n_dates=36) symbols=142 
- **data/earning_learning/pattern_history.csv**: present=True rows=25418 dates=2026-07-23→2026-09-16 (n_dates=39) symbols=142 
- **market_daily_t0.csv**: present=True rows=18 dates=2026-08-13→2026-09-14 (n_dates=18) symbols=1 
- **market_t0_snapshot.csv**: present=True rows=23 dates=2026-08-13→2026-09-16 (n_dates=20) symbols=1 
- **canonical 5m Camera parquet**: present=False rows=0 dates=None→None (n_dates=0) symbols=0 {"found": [], "missing": ["/var/lib/mrbot/intraday_memory", "/workspace/intraday_memory", "/workspace/data/intraday_pxv_v1"], "canonical_5m_available": false, "verdict": "UNSAFE FOR THIS STUDY"}
- **per-symbol daily OHLCV panel**: present=False rows=0 dates=None→None (n_dates=0) symbols=0 No dedicated daily bars store in repo. Forward T3/T5/T10 already materialized in outcomes/lifecycle from observation-row steps.

Session coverage vs union of all dated sources (90 union dates):

| source | n_dates | missing_vs_union | date_min | date_max | n_weekdays | missing_vs_weekday_union |
| --- | --- | --- | --- | --- | --- | --- |
| pattern_history | 48 | 42 | 2026-07-02 | 2026-09-16 | 37 | 39 |
| evolution | 78 | 12 | 2026-05-26 | 2026-09-16 | 76 | 0 |
| elite | 53 | 37 | 2026-06-25 | 2026-09-16 | 53 | 23 |
| freeze | 20 | 70 | 2026-08-13 | 2026-09-16 | 20 | 56 |
| observations | 39 | 51 | 2026-07-23 | 2026-09-16 | 35 | 41 |
| lifecycle | 36 | 54 | 2026-07-23 | 2026-09-10 | 32 | 44 |
| market_t0 | 18 | 72 | 2026-08-13 | 2026-09-14 | 18 | 58 |

Weekend row counts (contamination check): `{"pattern_history": 2972, "freeze": 0, "observations": 568, "evolution": 326, "elite": 0}`

Timestamp clock buckets (VN, UTC-aware when `Z` present; naive CSV times localized as VN):

| source | POST_CLOSE | LUNCH | n | n_parse_ok | recorded_after_trade_date | recorded_same_trade_date | recorded_before_trade_date | PM_SESSION | AM_SESSION | PRE_OPEN | ATC | OPEN_AUCTION |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t0_freeze.recorded_at | 2575 | 127 | 2702 | 2702 | 15 | 2687 | 0 | — | — | — | — | — |
| t0_freeze.frozen_at | 2575 | 127 | 2702 | 2702 | 15 | 2687 | 0 | — | — | — | — | — |
| observations.recorded_at | 3251 | 587 | 5400 | 5400 | 2141 | 3259 | 0 | 710.0 | 568.0 | 142.0 | 142.0 | — |
| pattern_history.date+time (naive VN) | 22896 | 3759 | 35616 | 35616 | 0 | 35616 | 0 | 5705.0 | 2084.0 | 442.0 | 359.0 | 371.0 |
| group_evolution.date+time (naive VN) | 10992 | 142 | 11624 | 11624 | 0 | 11624 | 0 | — | 163.0 | 327.0 | — | — |
| elite.date+time (naive VN) | 966 | 30 | 996 | 996 | 0 | 996 | 0 | — | — | — | — | — |

### Outcome definitions (existing earning-learning convention)

- Horizons: **T3 / T5 / T10** = `DEFAULT_HORIZONS = (3, 5, 10)`
- Indexing: **+n observation rows of the same symbol** in `observations.csv` (approximates trading sessions when that symbol is observed every session; gaps stretch calendar span)
- `return_pct = (target_price / entry_price − 1) × 100`
- `is_win = return_pct > 0` (zero is a loss)
- Favorable excursion: `max_gain_pct` on the forward price slice
- Adverse excursion: `max_drawdown_pct` on the forward price slice (typically ≤ 0)
- `is_leader` if MFE ≥ 5 / 8 / 12 percent at T3 / T5 / T10
- T3/T5/T10 on the same `observation_id` are **nested, not independent**
- Independent daily OHLCV panel: **absent** (cannot rebuild trading-session T+n from bars here)
- `pattern_history` `t*_return` columns: fill `{"t1_return": {"n_non_null": 0, "n_rows": 35616}, "t3_return": {"n_non_null": 0, "n_rows": 35616}, "t5_return": {"n_non_null": 0, "n_rows": 35616}, "t10_return": {"n_non_null": 0, "n_rows": 35616}}` — **do not** treat as known at snapshot time

Frozen P×V research defaults (**documented, not changed**): `{"RESEARCH_DEFAULT_EXPANSION_X": 2.0, "RESEARCH_DEFAULT_CONTRACTION_X": 0.7, "RESEARCH_DEFAULT_PACE_AHEAD_X": 1.5, "RESEARCH_DEFAULT_SESSION_MEDIAN_BARS": 6}`

Required 5m families (from `modules/intraday_pxv_v1/features.py` + `evidence.py`): interval volume EXPANSION/CONTRACTION/NORMAL vs prior-session median; price up/down; P×V CONFIRMING / WEAK / SELL_EXPANSION / FLAT; cumulative pace / TOD RVOL; evidence STRENGTHEN / NEUTRAL / CONFLICT / WEAKEN. All **NOT TESTABLE** without Camera.

---

## B. Chronology verdict

| source | class | reason |
| --- | --- | --- |
| canonical 5m Camera parquet | UNSAFE FOR THIS STUDY | No parquet under camera_data_root candidates in this workspace. Frozen P×V features cannot be computed. Do not invent bars. |
| frozen P×V interpreter / data/intraday_pxv_v1 ledger | UNSAFE FOR THIS STUDY | Output store absent; interpreter is code-only. Historical STRENGTHEN/CONFIRMING states were never persisted here. |
| pattern_history.csv group at a given row timestamp | PARTIAL / QUARANTINE | Row carries a group at CSV save clock. Useful as as-of IF that clock is true observation time. Documented Elite path says CSV time is save clock, last-wins — same risk here. PRE_OPEN 08:30 rows are not 5m session bars. Do not use a later same-day row as the morning group. |
| pattern_history last row per symbol×date | UNSAFE FOR THIS STUDY | Last-wins. If group evolved intra-day, the saved label is future relative to earlier 5m bars. |
| group_evolution_history.csv | PARTIAL / QUARANTINE | Dated group snapshots exist. Times cluster pre-open / save clock. Rank/score often empty. Safe only as ordered history of saved labels, not as 5m as-of. |
| t0_observation_freeze.group | PARTIAL / QUARANTINE | Same-day post-close freeze (typically ~15:54 VN). Valid as EOD T0 setup for daily T3/T5/T10. UNSAFE as intra-day as-of for 5m P×V (group already embeds the finished session). |
| observations.csv group / recorded_at | UNSAFE FOR THIS STUDY | recorded_at is frequently next calendar morning UTC. Using that group as T0 intra-day knowledge is look-ahead. |
| pattern_lifecycle.group | UNSAFE FOR THIS STUDY | Lifecycle copies observation group (T+1 clock) plus later outcome fill. Not first_seen setup. |
| buy_elite_learning_history.group | PARTIAL / QUARANTINE | One row per symbol×date, last file order wins. CSV time is save clock not candidate_first_seen_ts. Group is pass-through scan label on an Elite-filtered subset (selection bias). |
| daily volume_ratio / volume_ratio20 on freeze or pattern_history | UNSAFE FOR THIS STUDY | Daily (or session-injected daily) volume vs 20-day mean. Not frozen 5m expansion/contraction/CONFIRMING. Must not proxy P×V. |
| outcomes.csv / pattern_lifecycle T3 T5 T10 | SAFE AS-OF for forward daily outcomes | Horizons are forward from T0 observation price. Nested by construction. Computed as +n observation rows per symbol, which approximates trading sessions when coverage is complete. MFE=max_gain_pct, MAE=max_drawdown_pct on the forward slice. |
| pattern_history t1/t3/t5/t10 columns on the same snapshot row | UNSAFE FOR THIS STUDY as contemporaneous features | Forward returns attached onto historical snapshot rows are filled later. Using them as if known at sample time is look-ahead. They may still be used as outcomes if join is by symbol×date and fill is complete — prefer earning_learning outcomes. |
| market_daily_t0 VNINDEX OHLCV | SAFE AS-OF for market regime (EOD) | AFTER_CLOSE snapshots. Use as regime control, not as 5m P×V. |

**Can historical setup/group be reconstructed as-of without look-ahead?**

- **At 5m bar time:** **NO** in this workspace (no Camera; group sources are save-clock or EOD).
- **As EOD T0 setup for daily outcomes:** **PARTIAL** via `t0_observation_freeze.group` (post-close same day). Quarantine: not intra-day.
- **From pattern_history first snapshot/day:** **PARTIAL / QUARANTINE** (clock often PRE_OPEN; save clock ≠ first_seen).
- **From last snapshot, lifecycle group, or observations.recorded_at:** **UNSAFE**.

pattern_history first vs last (look-ahead audit): `{"symbol_date_pairs": 3046, "pairs_with_multiple_snapshots": 1102, "pairs_with_group_change_any_clock": 77, "pairs_with_intra_session_group_change": 29, "first_clock": {"POST_CLOSE": 1767, "AM_SESSION": 502, "LUNCH": 301, "PM_SESSION": 253, "PRE_OPEN": 107, "OPEN_AUCTION": 94, "ATC": 22}, "last_clock": {"POST_CLOSE": 2300, "PM_SESSION": 291, "AM_SESSION": 260, "LUNCH": 115, "PRE_OPEN": 41, "ATC": 34, "OPEN_AUCTION": 5}}`

Freeze vs pattern_history group disagreement: `{"freeze_vs_ph_first_disagree": 70, "freeze_vs_ph_last_disagree": 56, "n_joined": 417, "freeze_vs_ph_first_rate": 0.16786570743405277, "freeze_vs_ph_last_rate": 0.1342925659472422}`

---

## C. Sample-size table

Study setups are **not pooled**.

| Setup | N freeze EOD | N PH first/day | N PH last/day | N elite actionable rows | 5m P×V |
| --- | --- | --- | --- | --- | --- |
| CP MẠNH | 41 | 118 | 126 | 17 | NOT TESTABLE |
| PULL ĐẸP | 5 | 21 | 22 | 9 | NOT TESTABLE |
| PULL VỪA | 202 | 359 | 369 | 251 | NOT TESTABLE |
| MUA EARLY | 856 | 2548 | 2529 | 128 | NOT TESTABLE |
| MUA BREAK | 19 | 0 | 0 | 0 | NOT TESTABLE |
| TÍCH LŨY | 322 | 0 | 0 | 0 | NOT TESTABLE |

Full source breakdown:

| setup | source | N | testable_for_intraday_pxv | testable_for_setup_baseline |
| --- | --- | --- | --- | --- |
| CP MẠNH | t0_freeze EOD group (quarantine) | 41 | NOT TESTABLE — no canonical 5m Camera | YES |
| PULL ĐẸP | t0_freeze EOD group (quarantine) | 5 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| PULL VỪA | t0_freeze EOD group (quarantine) | 202 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA EARLY | t0_freeze EOD group (quarantine) | 856 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA BREAK | t0_freeze EOD group (quarantine) | 19 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| TÍCH LŨY | t0_freeze EOD group (quarantine) | 322 | NOT TESTABLE — no canonical 5m Camera | YES |
| CP MẠNH | pattern_history ALL rows (not a valid unit) | 1902 | NOT TESTABLE — no canonical 5m Camera | YES |
| PULL ĐẸP | pattern_history ALL rows (not a valid unit) | 82 | NOT TESTABLE — no canonical 5m Camera | YES |
| PULL VỪA | pattern_history ALL rows (not a valid unit) | 3452 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA EARLY | pattern_history ALL rows (not a valid unit) | 30180 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA BREAK | pattern_history ALL rows (not a valid unit) | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| TÍCH LŨY | pattern_history ALL rows (not a valid unit) | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| CP MẠNH | pattern_history FIRST snapshot/day (quarantine as-of) | 118 | NOT TESTABLE — no canonical 5m Camera | YES |
| PULL ĐẸP | pattern_history FIRST snapshot/day (quarantine as-of) | 21 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| PULL VỪA | pattern_history FIRST snapshot/day (quarantine as-of) | 359 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA EARLY | pattern_history FIRST snapshot/day (quarantine as-of) | 2548 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA BREAK | pattern_history FIRST snapshot/day (quarantine as-of) | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| TÍCH LŨY | pattern_history FIRST snapshot/day (quarantine as-of) | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| CP MẠNH | pattern_history LAST snapshot/day (UNSAFE as-of) | 126 | NOT TESTABLE — no canonical 5m Camera | YES |
| PULL ĐẸP | pattern_history LAST snapshot/day (UNSAFE as-of) | 22 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| PULL VỪA | pattern_history LAST snapshot/day (UNSAFE as-of) | 369 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA EARLY | pattern_history LAST snapshot/day (UNSAFE as-of) | 2529 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA BREAK | pattern_history LAST snapshot/day (UNSAFE as-of) | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| TÍCH LŨY | pattern_history LAST snapshot/day (UNSAFE as-of) | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| CP MẠNH | group_evolution ALL rows | 177 | NOT TESTABLE — no canonical 5m Camera | YES |
| PULL ĐẸP | group_evolution ALL rows | 22 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| PULL VỪA | group_evolution ALL rows | 623 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA EARLY | group_evolution ALL rows | 3151 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA BREAK | group_evolution ALL rows | 81 | NOT TESTABLE — no canonical 5m Camera | YES |
| TÍCH LŨY | group_evolution ALL rows | 1288 | NOT TESTABLE — no canonical 5m Camera | YES |
| CP MẠNH | elite history ALL conclusions | 38 | NOT TESTABLE — no canonical 5m Camera | YES |
| PULL ĐẸP | elite history ALL conclusions | 17 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| PULL VỪA | elite history ALL conclusions | 451 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA EARLY | elite history ALL conclusions | 464 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA BREAK | elite history ALL conclusions | 4 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| TÍCH LŨY | elite history ALL conclusions | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| CP MẠNH | elite BUY ELITE + MUA NHỎ last-wins subset | 17 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| PULL ĐẸP | elite BUY ELITE + MUA NHỎ last-wins subset | 9 | NOT TESTABLE — no canonical 5m Camera | WEAK |
| PULL VỪA | elite BUY ELITE + MUA NHỎ last-wins subset | 251 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA EARLY | elite BUY ELITE + MUA NHỎ last-wins subset | 128 | NOT TESTABLE — no canonical 5m Camera | YES |
| MUA BREAK | elite BUY ELITE + MUA NHỎ last-wins subset | 0 | NOT TESTABLE — no canonical 5m Camera | NO |
| TÍCH LŨY | elite BUY ELITE + MUA NHỎ last-wins subset | 0 | NOT TESTABLE — no canonical 5m Camera | NO |

If N=0 for a setup in a chronology-safe 5m frame, the setup is **NOT TESTABLE** at that frame — do not reconstruct it with a later label.

Source-specific **NOT TESTABLE** (do not fill from another file):

- **MUA BREAK** and **TÍCH LŨY**: `pattern_history` first/last per day **N=0**. Those labels exist on freeze/evolution only.
- **PULL ĐẸP**: freeze EOD N=5 → daily baseline **INSUFFICIENT**; 5m **NOT TESTABLE**.
- **MUA BREAK**: freeze EOD N=19 → daily baseline **INSUFFICIENT**; 5m **NOT TESTABLE**.
- All six setups: chronology-safe 5m P×V **NOT TESTABLE** (no Camera).

---

## D. Setup × P×V × outcome

**All cells N=0, evidence quality = NOT TESTABLE.**

First 18 rows (full CSV: `artifacts/D_setup_x_pxv_x_outcome.csv`):

| setup | pxv_condition | N | T3_winrate | T3_avg | T5_winrate | T5_avg | T10_winrate | T10_avg | evidence_quality | blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CP MẠNH | 5m_volume_EXPANSION | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | 5m_volume_CONTRACTION | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | 5m_volume_NORMAL | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | price_UP | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | price_FLAT | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | price_DOWN | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | P×V_CONFIRMING | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | P×V_WEAK | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | SELL_EXPANSION | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | pace_ahead_or_RVOL | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | evidence_STRENGTHEN | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | evidence_NEUTRAL | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | evidence_CONFLICT | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | evidence_WEAKEN | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | transition_CONTRACTION→EXPANSION | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | transition_NEUTRAL→STRENGTHEN | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| CP MẠNH | transition_WEAKEN→STRENGTHEN | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |
| PULL ĐẸP | 5m_volume_EXPANSION | 0 | — | — | — | — | — | — | NOT TESTABLE | canonical 5m Camera parquet absent; frozen P×V features not computable |

Generic current interpreter baseline (STRENGTHEN / NEUTRAL / CONFLICT / WEAKEN): likewise **NOT TESTABLE** (`artifacts/E_generic_pxv_interpreter_baseline.csv`).

Daily `volume_ratio20` on freeze is **not** used as a substitute 5m expansion feature.

---

## E. Baseline comparisons (setup without P×V)

These tables answer: *does the setup itself have a daily forward base rate?*  
They do **not** answer the P×V question. Use them so a good setup is not mistaken for a good 5m signal.

### E1. Unconditional setup — t0 freeze EOD group ⨝ pattern_lifecycle (QUARANTINE)

| Setup | Source | N | T3 N | T3 win% | T3 avg | T3 med | T3 MFE | T3 MAE | T5 N | T5 win% | T5 avg | T10 N | T10 win% | T10 avg | T10 med | T10 MFE | T10 MAE | evidence quality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_FREEZE_JOIN | t0_freeze ⨝ lifecycle (EOD group) | 2276 | 2276 | 37.7 | -0.54 | -0.68 | 0.88 | -1.63 | 1992 | 42.2 | -0.52 | 1282 | 40.2 | -1.04 | -0.94 | 3.71 | -3.42 | ADEQUATE_FOR_SETUP_BASELINE_ONLY |
| CP MẠNH | t0_freeze ⨝ lifecycle (EOD group, QUARANTINE) | 38 | 38 | 39.5 | -0.23 | -0.60 | 1.02 | -1.21 | 33 | 36.4 | -1.22 | 23 | 21.7 | -4.47 | -3.04 | 0.83 | -5.36 | PROVISIONAL |
| PULL ĐẸP | t0_freeze ⨝ lifecycle (EOD group, QUARANTINE) | 5 | 5 | 40.0 | 0.77 | -0.56 | 1.34 | -0.77 | 4 | 25.0 | -1.19 | 0 | — | — | — | — | — | INSUFFICIENT |
| PULL VỪA | t0_freeze ⨝ lifecycle (EOD group, QUARANTINE) | 180 | 180 | 36.1 | -0.82 | -0.38 | 0.72 | -1.82 | 157 | 34.4 | -1.70 | 72 | 38.9 | -1.67 | -1.84 | 2.54 | -3.89 | PROVISIONAL |
| MUA EARLY | t0_freeze ⨝ lifecycle (EOD group, QUARANTINE) | 801 | 801 | 37.3 | -0.50 | -0.73 | 0.93 | -1.58 | 752 | 41.5 | -0.48 | 520 | 36.0 | -1.74 | -1.64 | 3.45 | -3.96 | ADEQUATE_FOR_SETUP_BASELINE_ONLY |
| MUA BREAK | t0_freeze ⨝ lifecycle (EOD group, QUARANTINE) | 17 | 17 | 29.4 | -1.75 | -3.65 | 0.78 | -3.07 | 14 | 28.6 | -2.07 | 12 | 16.7 | -2.22 | -6.40 | 3.23 | -6.30 | INSUFFICIENT |
| TÍCH LŨY | t0_freeze ⨝ lifecycle (EOD group, QUARANTINE) | 289 | 289 | 44.3 | -0.09 | -0.11 | 1.34 | -1.26 | 263 | 50.6 | 0.18 | 176 | 48.3 | 0.02 | 0.00 | 4.54 | -2.16 | ADEQUATE_FOR_SETUP_BASELINE_ONLY |

ALL-freeze join row is the control for “same setup without a P×V condition” — here the P×V condition does not exist, so this **is** the unconditional setup outcome.

### E2. Generic current P×V interpretation

**NOT TESTABLE** (no ledger, no Camera).

### E3. Elite actionable subset

Selection-biased. See raw CSV `E_setup_unconditional_baselines_raw.csv` rows sourced `elite BUY/MUA NHỎ`. Elite conclusions mix: `{"WATCHLIST - MARKET YẾU": 353, "MUA NHỎ / ƯU TIÊN": 327, "WATCHLIST": 208, "BUY ELITE": 78, "CHƯA ĐỦ ĐỒNG THUẬN": 30}`

### E4. UNSAFE contrasts (leakage, not findings)

Rows sourced `observations ⨝ lifecycle` and `pattern_history LAST/day` are computed only to show how last-wins / T+1 clocks move N and rates. Do not promote them.

---

## F. Strongest observations

None of the following is a trading rule. None is a 5m P×V result.

- **Camera 5m data is missing** in every resolved `camera_data_root` candidate. Core study **NOT TESTABLE**.
- **EOD freeze group is post-close.** Using it as the setup that was known at 10:05 would leak the finished session into the label.
- **observations.group is T+1 clock.** SUPPORTED look-ahead.
- Setup daily base rates (EOD freeze, FRAGILE/control):

- **CP MẠNH** (control only, FRAGILE): T3 N=38 win=39.5% avg=-0.23; T10 N=23 win=21.7% avg=-4.47. EOD group, not 5m P×V.
- **PULL VỪA** (control only, FRAGILE): T3 N=180 win=36.1% avg=-0.82; T10 N=72 win=38.9% avg=-1.67. EOD group, not 5m P×V.
- **MUA EARLY** (control only): T3 N=801 win=37.3% avg=-0.50; T10 N=520 win=36.0% avg=-1.74. EOD group, not 5m P×V.
- **TÍCH LŨY** (control only): T3 N=289 win=44.3% avg=-0.09; T10 N=176 win=48.3% avg=0.02. EOD group, not 5m P×V.

---

## G. Contradictory observations

- **TÍCH LŨY** T10 winrate 48.3% vs ALL-freeze 40.2% (Δ +8.1 pp, T10 N=176). Setup base-rate only, one-regime window. FRAGILE control — not P×V.

- Elite-first Candidate path vs scanner-group identity: **CONTRADICTED** that Elite rows represent the scanner universe (F10).
- First vs last pattern_history group disagreement, if N>0, **contradicts** using a later saved group as morning as-of (F8).

---

## H. Insufficient-evidence areas

- Every 5m P×V condition and every transition sequence: **NOT TESTABLE**.
- Intra-day setup-as-of at 09:15–14:45 joined to frozen features: **NOT TESTABLE**.
- **PULL ĐẸP**: T3 N=5 T10 N=0 (INSUFFICIENT). Do not interpret P×V or even setup edge.
- **MUA BREAK**: T3 N=17 T10 N=12 (INSUFFICIENT). Do not interpret P×V or even setup edge.
- Corporate actions: **NOT TESTABLE**.
- Incomplete 5m bars / session completeness vs 09:15–11:30 & 13:00–14:45 grid: **NOT TESTABLE** (no bars).
- Repeated 5m observations from the same symbol×session: would require clustered standard errors **if** Camera existed; not estimated.
- Overlapping T3/T5/T10: by design nested; do not treat the three horizons as three independent samples.
- Market-regime concentration on freeze join:

| setup | market_regime | N |
| --- | --- | --- |
| CP MẠNH | 🔴 Forecast rủi ro | 38 |
| GÀ TĂNG TỐC | 🔴 Forecast rủi ro | 159 |
| MUA BREAK | 🔴 Forecast rủi ro | 17 |
| MUA EARLY | 🔴 Forecast rủi ro | 801 |
| PULL VỪA | 🔴 Forecast rủi ro | 180 |
| PULL ĐẸP | 🔴 Forecast rủi ro | 5 |
| THEO DÕI | 🔴 Forecast rủi ro | 787 |
| TÍCH LŨY | 🔴 Forecast rủi ro | 289 |

---

## I. Leakage / bias findings

| Check | Result |
| --- | --- |
| Look-ahead from setup labels | Last-wins pattern_history / evolution / elite: **UNSAFE**. Freeze EOD: **quarantine** (not 5m as-of). observations.recorded_at next morning: **UNSAFE**. |
| CSV save clock vs true first_seen | Elite candidates.py documents save clock ≠ first_seen. pattern_history `time` treated the same: **PARTIAL**. |
| Incomplete 5m bars | **NOT TESTABLE** (no Camera). |
| Survivorship / selected-symbol | Watchlist ~140 names; Elite actionable is a further filter. Freeze/observations cover scanner universe more broadly than Elite. |
| Repeated symbol×session | pattern_history: `1102 / 3046` pairs have >1 snapshot. Valid 5m study would cluster or pick one as-of. |
| Overlapping T3/T5/T10 | Nested on `observation_id`. |
| Corporate actions | No calendar; unadjusted observation prices. |
| Market-regime concentration | See freeze × regime table. Freeze coverage is a short 2026 window (see inventory), not a multi-year panel. |
| Freeze observation_id dups | 0 |
| Daily volume as P×V | Explicitly **UNSAFE**; not used. |

Quarantine policy used: empty P×V cells rather than filling with daily volume or last-wins group.

---

## Finding classes (only these labels)

| id | claim | class | why |
| --- | --- | --- | --- |
| F1 | Different scanner setups have materially different frozen 5m P×V signatures associated with better/worse forward outcomes. | NOT TESTABLE | Canonical 5m Camera bars are absent. No historical P×V ledger. Conditional tables are empty by construction. |
| F2 | Volume expansion means the same thing across setups. | NOT TESTABLE | 5m expansion state cannot be computed without Camera bars. Daily volume_ratio must not be substituted. |
| F3 | Volume contraction has different meaning in pullback vs momentum setups. | NOT TESTABLE | Same blocker as F2. Hypotheses (PULL ĐẸP dry-up, CP MẠNH expansion) were not encoded and were not measured. |
| F4 | Transitions (CONTRACTION→EXPANSION, NEUTRAL→STRENGTHEN, WEAKEN→STRENGTHEN) are more informative than a single 5m state. | NOT TESTABLE | Sequences require ordered 5m evidence states. None available. |
| F5 | The current generic P×V interpreter loses useful setup-specific information. | NOT TESTABLE | Cannot compare generic STRENGTHEN/WEAKEN vs setup-conditional outcomes without 5m features. Architecture (Elite first → generic P×V) is a design fact, not an outcome fact. |
| F6 | t0_observation_freeze.group is an end-of-day T0 setup, not an intra-day as-of setup. | SUPPORTED | recorded_at/frozen_at clock buckets are POST_CLOSE on the trade date (VN ~15:54). Valid for daily T3/T5/T10 baseline; invalid for 5m as-of. |
| F7 | observations.csv group cannot be used as T0 as-of setup. | SUPPORTED | 2141/5400 observation rows have recorded_at on a later calendar date than trade_date; remaining clocks are mixed same-day. The column is not a T0 as-of first_seen. |
| F8 | pattern_history last-wins group is look-ahead vs first snapshot of the same symbol×session. | SUPPORTED | first≠last on 77 of 3046 symbol×date pairs; intra-session changes 29. |
| F9 | Scanner setups have different unconditional daily T3/T5/T10 base rates (control, not a P×V signal). | FRAGILE | EOD freeze ⨝ lifecycle can be tabulated per setup. Sample sizes and regime concentration may be uneven; this is a control table so P×V is not confused with a good setup. Not chronology-safe for intra-day. |
| F10 | Elite BUY subset is an unbiased sample of scanner setups. | CONTRADICTED | Elite history is filtered to actionable conclusions and last-wins per symbol×date. Live Candidate pipeline is Elite-first. Using Elite rows as if they were the scanner universe is selected-symbol bias. |
| F11 | Corporate-action-adjusted prices are available for this study. | NOT TESTABLE | No CA calendar in repo. Outcomes use observation prices as stored. |
| F12 | PULL ĐẸP / CP MẠNH / MUA BREAK historical as-of samples exist at 5m resolution. | NOT TESTABLE | 5m resolution absent. Daily EOD freeze counts are not 5m as-of counts. PULL ĐẸP freeze N=5 and MUA BREAK freeze N=19 are also insufficient as daily baselines. |
| F13 | MUA BREAK and TÍCH LŨY can be reconstructed as-of from pattern_history.csv. | NOT TESTABLE | pattern_history first/last per day N=0 for both labels. Evolution and freeze contain those groups. Copying a later source onto PH timestamps would be look-ahead. Leave as NOT TESTABLE from PH. |
| F14 | Freeze ⨝ lifecycle outcomes are diversified across market regimes. | CONTRADICTED | Joined freeze rows are 100% labeled market_regime='🔴 Forecast rủi ro'. Any setup base-rate table is concentrated in one forecast-risk window. |
| F15 | Dated scanner CSVs contain only VN trading sessions. | CONTRADICTED | Weekend rows: pattern_history=2972, observations=568, evolution=326. Freeze weekend rows=0. Union includes 14 weekend dates. Quarantine weekend dates for any follow-up. |
| F16 | T3/T5/T10 are exact +n VN trading sessions. | FRAGILE | earning_learning walks +n observation rows per symbol. T3 median calendar span=4d, p90=6d, max=11d — gaps in observation coverage stretch the horizon. No independent daily OHLCV panel to rebuild session-exact T+n here. |

---

## What would make the core question testable

1. Canonical 5m Camera parquet with `timestamp` ≤ as-of, incomplete bars quarantined.
2. Setup label whose **first_seen** at or before that as-of is stored (not last-wins, not T+1 `recorded_at`, not post-close freeze used as 10:05 knowledge).
3. Frozen P×V features computed with **unchanged** research defaults, plus optional transition flags on consecutive usable 5m states.
4. Forward T3/T5/T10 from existing earning-learning convention, clustered by symbol×session, with setup-unconditional and generic-interpreter controls.
5. Stop: still no BUY/SELL rules; classify SUPPORTED / FRAGILE / NO EVIDENCE / CONTRADICTED / NOT TESTABLE.

---

## Isolation record

Wrote only:

- `research/setup_intraday_pxv_forward/run_study.py`
- `research/setup_intraday_pxv_forward/README.md`
- `research/setup_intraday_pxv_forward/REPORT.md`
- `research/setup_intraday_pxv_forward/artifacts/*`

Did not change Candidate Router, Elite, Rotation, scanner, frozen P×V, live-shadow, Telegram, Streamlit, VPS, or `/opt/mrbot-camera`.

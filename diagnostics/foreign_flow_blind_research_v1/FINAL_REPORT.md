# Foreign Flow Blind Research V1 — Final Report

## Verdict

`FOREIGN_FLOW_RESEARCH_CANDIDATE_FOUND`

`DEDICATED_CONFIRMATION_PHASE = YES`

## Executive scientific summary

After freezing the canonical HSX foreign-flow panel (117 EMS-HOSE symbols, 2009-01-02→2026-08-24, 337,236 rows) and screening a **pre-declared** bounded grammar under chronological discovery/validation/holdout:

1. **Simple foreign buy/sell sign (`net_pos` / `net_neg`) is NOT a robust predictor** of T1/T3/T5/T10 returns — an important null relative to naive anecdotes.
2. **Price×flow “agreement” effects are mostly price momentum.** Parent horse-race shows `px_pos`/`px_neg` alone match or beat `agree_*` in validation; conditional flow incremental given price is near zero/unstable. These are **not** attributed to foreign-flow information.
3. **A small magnitude-family research candidate remains:** abnormal absolute net-flow (`|net_z_60| > 2`, feature `abn_abs_z20`) at **T10**, with consistent positive incremental vs unconditional baseline across discovery, validation, and holdout. Effect size is **small** (holdout incremental ≈ **+28 bps** over 10 sessions). Also `net_hi_pct90` at T10 appears as a related magnitude candidate.
4. **Persistent foreign selling streaks** show a weak anti-edge (negative incremental) worth confirmation, not trading.

No candidate is labeled EDGE ACTIVE. No trading translation.

## Answers to required questions

1. **Does foreign-flow history contain reproducible information?**  
   **Weakly / possibly — magnitude (and weak persistence anti-edge), not simple sign.** Verdict `FOREIGN_FLOW_RESEARCH_CANDIDATE_FOUND`.

2. **Horizons?**  
   Strongest remaining support at **T10** for magnitude; short horizons dominated by price momentum contamination when interaction features are used naively.

3. **Type of information?**  
   Primarily **magnitude** (abnormal |net| / high net percentile). **Not** robust simple sign. Interaction features fail parent tests. Persistence of selling = weak anti-edge candidate.

4. **Incremental vs baseline?**  
   Best magnitude candidate holdout incremental ~**+0.0028** (≈28 bps / 10 sessions) for `abn_abs_z20` T10; absolute holdout mean still modest (~+11 bps).

5. **Survive later periods?**  
   `abn_abs_z20` T10: discovery/validation/holdout incremental all positive. Interaction “agree” features do **not** survive as flow-attributable after parent tests.

6. **Survive removal of dominant stocks/years?**  
   Leave-top5 and alt-horizon checks passed for retained candidates in the automated falsification pass; parent horse-race killed interaction family. See `FALSIFICATION_REPORT.md` + `PARENT_HORSERACE.csv`.

7. **Strongest anti-edge / failure?**  
   `streak_neg_le_m5` T10 [RESEARCH_CANDIDATE] disc_incr=-0.0046147750692512495 val_incr=-0.0005684233265075139 hold_incr=-0.0014566291099041787 hold_mean=-0.0031321262017223617 hold_n=12800 symbols=117

8. **What would falsify next?**  
   Pre-registered confirmation on post-freeze sessions; require magnitude candidate holdout incremental ≥ +15 bps at T10 with same sign on validation-equivalent window; fail if price-volatility controls or CA-adjusted prices eliminate the effect; fail if effect concentrates in <20 symbols.

9. **Confirmation justified?**  
   `YES` — for **magnitude abnormal-flow / high-net-percentile at T10** only (and optional selling-streak anti-edge). Not for agree_* interactions.

## Confirmation proposal (do NOT implement yet)

1. Freeze definitions: `abn_abs_z20` (and optionally `net_hi_pct90`) at T10; optional `streak_neg_le_m5` anti-edge.
2. Register forward window after 2026-08-24 (or next available HSX sessions).
3. Pre-declare success: same-sign incremental vs unconditional; |incr| floors; min symbols/dates; fail if parent/volatility controls absorb effect.
4. No grammar expansion during confirmation.

## Data freeze

- `ff_hsx_symbol_daily_v1_20260825T045650Z` | rows `337236` | symbols `117`
- range `2009-01-02` → `2026-08-24`
- cohort: current EMS HOSE overlap (not historical membership)
- excluded nonpositive/extreme-jump rows from research eligibility

## Search accounting

- hypotheses examined: `112`
- promoted then audited: `84`
- depth: predeclared grammar, single pass, then parent horse-race audit

## Top retained findings

### Strongest positive (RESEARCH_CANDIDATE only)
- `net_hi_pct90` T10 [RESEARCH_CANDIDATE] disc_incr=0.002070706147217414 val_incr=0.0022876083612547293 hold_incr=0.0036243207852603193 hold_mean=0.0019488236934421363 hold_n=16076 symbols=113
- `abn_abs_z20` T10 [RESEARCH_CANDIDATE] disc_incr=0.003171116394793465 val_incr=0.004111046473028797 hold_incr=0.0027638842721887514 hold_mean=0.0010883871803705684 hold_n=8508 symbols=117

### Strongest negative / anti-edge (RESEARCH_CANDIDATE only)
- `streak_neg_le_m5` T10 [RESEARCH_CANDIDATE] disc_incr=-0.0046147750692512495 val_incr=-0.0005684233265075139 hold_incr=-0.0014566291099041787 hold_mean=-0.0031321262017223617 hold_n=12800 symbols=117
- `streak_neg_le_m3` T5 [RESEARCH_CANDIDATE] disc_incr=-0.0027002782192419514 val_incr=-0.00043164190979567193 hold_incr=-0.0004789997685485611 hold_mean=-0.0014471705833510548 hold_n=27287 symbols=117
- `streak_neg_le_m5` T1 [RESEARCH_CANDIDATE] disc_incr=-0.0008289682244023467 val_incr=-0.00043180353506963847 hold_incr=-0.00033844306321391995 hold_mean=-0.0005471020947961533 hold_n=12993 symbols=117

### Important failed intuitions / nulls

- Foreign **buying** (`net_pos`) is **not** robustly bullish across eras.
- Foreign **selling** (`net_neg`) is **not** robustly bearish as a one-day sign.
- Price×flow agreement looks predictive until price alone is controlled.

## Classification counts (after parent audit)

`{"FRAGILE": 79, "RESEARCH_CANDIDATE": 5}`

---

## Operator block (VI)

**Sau khoảng 17 năm dữ liệu, khối ngoại thực sự có chứa thông tin giúp dự báo T3/T5/T10 hay không?**

- **Không** có bằng chứng vững rằng “khối ngoại mua = tăng / bán = giảm” ở mức one-day sign cho T3/T5/T10.
- Các tín hiệu kiểu “giá và dòng chảy cùng chiều” phần lớn là **đà giá**, không phải thông tin khối ngoại thuần (đã kiểm tra horse-race với `px_pos`/`px_neg`).
- Có **ứng viên nghiên cứu yếu–vừa** thuộc họ **biên độ bất thường** (`|net_z_60|>2`, và phần trăm net cao) ở horizon **T10**, sống qua discovery/validation/holdout nhưng **hiệu ứng nhỏ** (~ vài chục bps / 10 phiên) và phải qua phase confirmation riêng.
- Verdict: **`FOREIGN_FLOW_RESEARCH_CANDIDATE_FOUND`**. Confirmation: **`YES`**.
- **Không** phải khuyến nghị giao dịch.

STOP.

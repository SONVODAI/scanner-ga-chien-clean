# Foreign Flow Historical Audit

**Audit ID:** `foreign_flow_historical_audit_v1`  
**Mode:** DIAGNOSTIC ONLY — no production backfill, no Edge search, no model training.

## Dual verdict

| Axis | Verdict |
|------|---------|
| Historical data | **`FOREIGN_FLOW_HISTORY_RESEARCH_READY`** |
| Backfill | **`BACKFILL_WORTHWHILE`** |

**Scope of readiness:** stock-level **HOSE** foreign buy/sell/net VALUE (+ co-located OHLC) for multi-year blind research of `Foreign Flow T0 → stock T3/T5/T10`.  
**Not ready as-is:** EMS-142 historical universe aggregates, ADV/turnover norms, deep Market-context joins.

---

## Vietnamese (operator)

**Ta lấy lại được bao nhiêu lịch sử khối ngoại, và đã đáng để đào edge T3/T5/T10 chưa?**

HSX official API cho **mỗi mã HOSE** khoảng **tới ~2009** (VNM/HPG/FPT: **4402** phiên, ~**17 năm**), đủ buy/sell VALUE (VND) + volume + OHLC cùng payload — **đủ sâu** để nghiên cứu edge cổ phiếu theo hướng mù (blind), **không** cần chờ chỉ 17 phiên EMS. Nhưng: chỉ **117/142** mã EMS có trên HSX (25 mã HNX/UPCOM trống); **không** được chiếu 142 hôm nay ngược quá khứ (survivorship); chuẩn hóa theo thanh khoản/ADV và gắn Market FC/breadth vẫn **mỏng**. **Đáng backfill** dataset lịch sử theo **từng mã HOSE**, rồi mới mở phase Edge Research độc lập — **chưa** train / chưa hard-code giả thuyết.

---

## 1. Official HSX historical depth

**Endpoint:** `GET https://api.hsx.vn/mk/api/v1/market/securities/foreign/{SYM}?pageSize=N[&pageIndex=P]`

| Observation | Evidence |
|-------------|----------|
| Fields | `mainBuyer/SellerForeignValue` (VND), volumes (shares), optional bigLot_*, OHLC (`openPrice`…`closePrice`), room fields |
| Units | **VND** (VALUE); shares (volume) |
| `reportDate` | Unix UTC midnight → session date; weekday-only (no Sat/Sun in VNM hist) |
| Pagination | `pageSize` controls returned count; `pageIndex` pages older windows at smaller sizes |
| Cap / depth | `pageSize=5000` → VNM/HPG/FPT **4402** rows from **2009-01-02** → 2026-08-24 (~17y). `pageSize=2000` only returns recent 2000 sessions |
| Gaps vs business days | ~90 “missing” vs `bdate_range` — mostly VN holidays (Tết, etc.), not random holes |
| Duplicates | Unique `reportDate` per page in probes |
| Newer listings | NAB from 2024-03-07 (615); SIP from 2023-08-07 (760) |
| Non-HOSE | CEO/FOX/MML/ACV/… → **empty list** |
| Rate | ~0.15–0.4s sleep stable in audit; large `pageSize=5000` payloads are heavy (IncompleteRead risk if truncated) |

Sample across large/mid/small EMS names + anchors: long-listed HOSE consistently deep; empties are exchange-eligibility, not API failure.

**Can we recover all eligible HOSE members?** Yes in principle (one GET per symbol with large `pageSize` or paginated walks). Not all EMS-142 (see §2).

Artifacts: `SOURCE_DEPTH_MATRIX.csv`, `hsx_pagesize_experiments.csv`, `vnm_depth_walk.json`.

---

## 2. Universe membership

### A. Current EMS-142 projected backward
- **117/142** HSX-eligible (HOSE); **25** empty (HNX/UPCOM-style: ACV, CEO, FOX, PVS, …).
- Using today’s 142 (or today’s 117) for 2009–2025 = **survivorship / listing bias**. Must label explicitly if used.

### B. Historical membership-as-of
- EMS exact `snapshot_date` rule exists in code (`ems_universe_symbols`).
- Local EMS depth: **only 17 sessions** (2026-07-31→08-24); membership **unchanged** (142∩142) in that window.
- Honest membership-asof **cannot** be reconstructed before EMS start without another listing source.

**Do not silently treat today’s 142 as historical membership.**

---

## 3. Price / outcome matchability

| Need | Availability |
|------|----------------|
| T1/T3/T5/T10/T20 session returns | **YES** from HSX foreign payload OHLC for HOSE history (~2009+) |
| MFE/MAE / path drawdown | **YES** if intervening session closes present (same series) |
| Local EMS prices | Only **17** sessions |
| Root `pattern_history` prices | **43** dates, incomplete universe |

**Conclusion:** Outcome engineering for a HOSE stock-level foreign-flow panel does **not** depend on the 17 EMS dates — HSX already ships closes with foreign rows.

Trading-session calendar (not calendar days) remains mandatory.

---

## 4. Feature possibilities (audit only)

See `FEATURE_AVAILABILITY_MATRIX.csv`.

**PIT-safe now (HSX alone):** buy/sell/net value & volume; consecutive/cumulative nets; transitions; own-history z/percentile; price–flow divergence using co-located OHLC.

**Conditional / weak:** net÷turnover, participation share, ADV5/10/20 — **market volume absent** from this HSX endpoint; `percent` observed as `0.0` (unreliable).

**Never:** missing → 0.

---

## 5. Market / sector context join

| Context | Overlap with HSX foreign depth |
|---------|--------------------------------|
| Market FC (hist core / PH) | ~**42** weekdays from 2026-06-25 — tiny vs 17y HSX |
| REAL/LIVE/breadth (MDT0) | **8** sessions from 2026-08-13 |
| Forecast T0 rich DNA | **17** sessions |
| Sector | EL observations ~**27** dates; EMS has no sector |

**Implication:** Regime-conditioned propositions (“flow in strong vs weak market”) are **data-limited today**; stock-level flow→return research is not.

---

## 6–7. Coverage & sample size

Compact matrices: `COVERAGE_BUCKET_MATRIX.csv`, `RESEARCH_COVERAGE_SUMMARY.csv`, `RESEARCH_SAMPLE_SIZE.csv`.

| Panel | Symbols | Sessions (est.) | Obs (est.) |
|-------|---------|-----------------|------------|
| HSX foreign + OHLC | ~117 HOSE | ~4402 longlisted | ~O(10⁵) |
| + ADV/turnover | ~117 | ~17 local | tiny |
| + Market context | ~117 | ~8–42 | small |
| + EMS membership-asof | 142 | 17 | small |

Row counts ≠ independent market episodes. Multi-year stock panels provide many stock×day rows but shared market shocks; episode separation still required later.

---

## 8. Historical depth checklist

| Layer | ≥1m | ≥3m | ≥6m | ≥1y | ≥2y |
|-------|-----|-----|-----|-----|-----|
| 1. Official HSX raw | YES | YES | YES | YES | **YES (~17y)** |
| 2. Foreign + price (HSX OHLC) | YES | YES | YES | YES | **YES** |
| 3. Foreign + liquidity ADV | NO* | NO | NO | NO | NO |
| 4. Foreign + Market context | YES | NO | NO | NO | NO |
| 5. Foreign + membership-asof EMS | NO | NO | NO | NO | NO |

\*Unless a separate historical volume/turnover source is approved later.

---

## 9. Future blind Edge Research design (design only)

**Object:** stock-level HOSE panel: features from foreign flow at T0 → outcomes T3/T5/T10 (and T20 if used).

**Must not encode:** “foreign selling causes underperformance” (or the reverse) as truth — only as one falsifiable candidate among many.

**Research grammar (later):** baselines (unconditional / liquidity-matched); incremental edge; episode/regime separation; concentration (large-cap/sector); falsification; OOS/holdout; search accounting / multiple testing — analogous in spirit to Edge Research, **not** hard-wired hypotheses.

**Free dimensions:** sign, magnitude, persistence, transitions, normalization (when dens available), lag, anti-edge, sector (when available), price/flow divergence, regime interaction (when context deepens).

---

## 10. Bias / leakage

See `BIAS_AND_LEAKAGE_AUDIT.md`.

---

## 11. Backfill recommendation

**`BACKFILL_WORTHWHILE`** — build a **canonical per-symbol HOSE foreign+OHLC history store** from HSX (not a silent EMS-142 historical aggregate).

Design only: `BACKFILL_DESIGN.md`. **Do not execute in this task.**

---

## Artifacts

| File | Role |
|------|------|
| `FOREIGN_FLOW_HISTORICAL_AUDIT.md` | This report |
| `SOURCE_DEPTH_MATRIX.csv` | Per-symbol probe depths |
| `FEATURE_AVAILABILITY_MATRIX.csv` | Feature PIT/depth |
| `RESEARCH_COVERAGE_SUMMARY.csv` | Layer depth verdicts |
| `RESEARCH_SAMPLE_SIZE.csv` | Sample size estimates |
| `COVERAGE_BUCKET_MATRIX.csv` | Era buckets |
| `BIAS_AND_LEAKAGE_AUDIT.md` | Bias register |
| `BACKFILL_DESIGN.md` | Schema + safe plan (not executed) |
| `EVIDENCE.json` | Machine-readable counts |
| `ems142_hsx_eligibility.json` | 117 vs 25 split |

---

## Final verdicts

**`FOREIGN_FLOW_HISTORY_RESEARCH_READY`**  
**`BACKFILL_WORTHWHILE`**

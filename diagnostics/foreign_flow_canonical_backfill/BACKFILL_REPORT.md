# Canonical HSX Foreign Flow Historical Backfill — Report

**Branch:** `cursor/hsx-foreign-flow-canonical-backfill-aad2`  
**Schema:** `ff_hsx_symbol_daily_v1`  
**Grain:** `trade_date × symbol` (NOT today's EMS-142 projected backward)  
**Store:** `data/foreign_flow_history/`

> This report is updated as stages complete. Final verdict appears at the bottom when freeze is written.

---

## Dual research-freeze gate

| Gate | Status |
|------|--------|
| Canonical backfill | *pending Stage B* |
| Blind research ready | *pending freeze* |

---

## Stage A — pilot (COMPLETE)

| Symbol | Sessions | First | Last |
|--------|----------|-------|------|
| VNM | 4402 | 2009-01-02 | 2026-08-24 |
| HPG | 4402 | 2009-01-02 | 2026-08-24 |
| FPT | 4402 | 2009-01-02 | 2026-08-24 |
| MWG | 3025 | (listing-dependent) | 2026-08-24 |
| NAB | 615 | (newer listing) | 2026-08-24 |
| SSI | 4402 | 2009-01-02 | 2026-08-24 |
| DIG | 4245 | (listing-dependent) | 2026-08-24 |

**Cross-check vs PR #93 audit:** VNM/HPG/FPT session count **4402** and first date **2009-01-02** match exactly. Units VND. Net = buy − sell exact.

**Resumability proof:** re-run Stage A → all symbols `skipped_completed`.

---

## Stage B — current EMS HOSE overlap (117)

*In progress — see checkpoint / this report's final section.*

---

## Stage C — broader historical HOSE

**Not claimed complete.** No safe full historical HOSE membership reconstruction available beyond current EMS HOSE eligibility list. Symbol-level history preserved without membership-as-of claims.

---

## Exclusions

25 current EMS HNX/UPCOM symbols excluded (HSX empty; not fabricated). See eligibility manifest and freeze `exclusions`.

---

## Production safety

No modifications to Forecast Memory, Forecast T0, MDRR, P0 production collector, Market First, FC/REAL/LIVE, Edge Research, Camera, Streamlit, systemd, or trading logic.

---

## Final verdict

*(filled on freeze)*

# Canonical HSX Foreign Flow Historical Backfill — Report

**Schema:** `ff_hsx_symbol_daily_v1`  
**Grain:** `trade_date × symbol`  
**Store:** `data/foreign_flow_history/`  
**Freeze dataset:** `ff_hsx_symbol_daily_v1_20260825T045650Z`  
**Created:** `2026-08-25T04:56:50Z`

## Final verdict

`FOREIGN_FLOW_CANONICAL_BACKFILL_COMPLETE`

`BLIND_FOREIGN_FLOW_RESEARCH_READY = YES`

## Coverage summary

| Metric | Value |
|--------|-------|
| Symbols attempted (Stage B EMS HOSE) | 117 |
| Symbols completed | 117 |
| Symbols failed | 0 |
| Symbols rate-limited | 0 |
| Total rows | 337236 |
| Earliest date | 2009-01-02 |
| Latest date | 2026-08-24 |
| Median sessions/symbol | 2858 |
| Max sessions/symbol | 4402 |
| Current EMS HOSE coverage | 117/117 |
| Excluded HNX/UPCOM | 25 |
| Disk footprint (bytes) | 302404651 |
| Integrity hard failures | 0 |

## Stage A pilot

Complete. Cross-check vs PR #93: VNM/HPG/FPT = **4402** sessions from **2009-01-02**. Resume skip-completed proven.

## Stage B — EMS HOSE 117

**COMPLETE** — all 117 HOSE-eligible EMS symbols persisted under `data/foreign_flow_history/canonical/by_symbol/`.

## Stage C — broader historical HOSE

**Not claimed complete.** No safe full historical HOSE membership reconstruction beyond current EMS HOSE eligibility.

## Exclusions (not fabricated)

ACV, BVS, C4G, CEO, DDV, DRI, FOX, HUT, IDC, LAS, MBS, MML, MSR, NTP, OIL, PLC, PVB, PVC, PVS, SHS, TNG, TVN, VGI, VGS, VGT

## Known biases

- Current EMS HOSE overlap is present-day relevance, not historical membership-as-of.
- Listing-age bias: long-listed names have deeper history than recent listings.
- No complete historical HOSE membership reconstruction claimed.
- Raw provider OHLC; corporate-action adjustment unverified.
- Market-context / ADV overlap much shorter than foreign-flow history.

## Price outcome readiness (no labels computed)

Same-provider OHLC supports later session-based T1/T3/T5/T10/(T20) and path MFE/MAE.  
Outcome labels are **not** mixed into T0 canonical rows.

## Resumability

Checkpoint: `data/foreign_flow_history/manifests/backfill_checkpoint.json`.  
Re-run stages skip `status=completed`. Partial failure does not destroy completed symbols. Proven after SIGPIPE resume.

## Dataset / hash manifest

See `data/foreign_flow_history/manifests/research_freeze.json` (per-symbol sha256 + coverage).

## Production safety

No P0 / Forecast / MDRR / Edge / Camera / Streamlit / systemd mutations.

STOP — no edge discovery performed.

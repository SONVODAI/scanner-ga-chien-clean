# Expected Trigger Frequency (from Blind Research V1 only)

**Source:** `diagnostics/foreign_flow_blind_research_v1` registry / temporal validation.  
**No post-2026-08-24 performance used.**

Confirmation window length is driven by **independent temporal evidence** (unique trigger dates), not round calendar months.

## Historical rates (eligible candidate rows with matured T10 in V1 splits)

Approximate session denominators use V1 split date coverage (`n_dates` of broad eligible universe ≈ trading sessions with activity): discovery ≈ 1995, validation ≈ 1250, holdout ≈ 1145.

### Primary — `abn_abs_z20`

| Split | stock×day n | unique dates | unique symbols | stock×day / session | dates / session | symbols / trigger-date |
|-------|-------------|--------------|----------------|---------------------|-----------------|------------------------|
| Discovery | 5944 | 1738 | 64 | ~2.98 | ~0.87 | ~3.4 |
| Validation | 7110 | 1230 | 101 | ~5.69 | ~0.98 | ~5.8 |
| Holdout | 8508 | 1137 | 117 | ~7.43 | ~0.99 | ~7.5 |

**Forward planning rate (holdout-era):** expect ~**7–8** stock×day triggers per session and a trigger on **nearly every** session (~99% of dates), with ~**7–8** symbols per trigger date. Same-day symbols are **not** independent.

### Secondary — `net_hi_pct90`

| Split | stock×day n | unique dates | unique symbols | stock×day / session | dates / session | symbols / trigger-date |
|-------|-------------|--------------|----------------|---------------------|-----------------|------------------------|
| Discovery | 16124 | 1728 | 64 | ~8.08 | ~0.87 | ~9.3 |
| Validation | 16647 | 1250 | 95 | ~13.32 | ~1.00 | ~13.3 |
| Holdout | 16076 | 1145 | 113 | ~14.04 | ~1.00 | ~14.0 |

**Forward planning rate (holdout-era):** ~**14** stock×day / session; essentially every session; ~**14** symbols / date.

### Optional anti-edge — `streak_neg_le_m5`

Holdout: n=12800, dates=1143, symbols=117 → ~**11.2** stock×day / session, ~**1.0** date coverage.

## Independence reminder

- **stock×day rows** inflate N; use for descriptive volume only.
- **unique trigger dates** ≈ primary unit of temporal evidence.
- **unique symbols** guard against name concentration.
- Do not treat 7 same-day triggers as 7 independent trials.

## Proposed confirmation windows

Derived from holdout trigger frequency and PASS breadth floors (80 unique dates minimum; 180 preferred).

### Minimum evaluation window (first judgment allowed)

- **~90 trading sessions** of post-freeze T0 collection after lookbacks are warm, **plus** 10 sessions for T10 maturity.
- Expected matured unique dates ≈ **85–90** for primary (given ~0.99 date hit rate).
- Expected matured stock×day ≈ **650–700** for `abn_abs_z20`; ≈ **1200+** for `net_hi_pct90`.
- State at this point: may enter `CONFIRMATION_IN_PROGRESS`; final `CONFIRMED` / `FAILED_CONFIRMATION` only when preferred breadth met (unless max patience forces `INCONCLUSIVE`).

### Preferred window (final judgment target)

- **~200 trading sessions** of post-freeze T0 triggers matured through T10.
- Expected matured unique dates ≈ **195–200**.
- Expected matured stock×day ≈ **1400–1600** (`abn_abs_z20`); ≈ **2800** (`net_hi_pct90`).
- This is the intended sample for PASS/FAIL.

### Maximum patience window

- **504 trading sessions** (~2 calendar years of VN sessions) measured from the first eligible post-freeze T0 session.
- If preferred breadth still unmet → `INCONCLUSIVE`.
- If preferred breadth met earlier → judge then; do not keep waiting to improve results.

## Calendar implication (approximate)

| Window | Trigger sessions | + T10 maturity | Rough calendar |
|--------|------------------|----------------|----------------|
| Minimum | ~90 | +10 | ~4–5 months to first monitoring |
| Preferred | ~200 | +10 | ~9–11 months to final judgment |
| Max patience | 504 | +10 | ~2+ years then stop |

Exact calendar depends on holiday schedule; count **trading sessions**, not months.

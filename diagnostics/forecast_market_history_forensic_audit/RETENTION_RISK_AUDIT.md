# Retention Risk Audit — Forecast Market History

**Scope:** Read-only code + schema inspection. No production mutation.

---

## Principle (target)

> Raw observations retained indefinitely; derived schemas may evolve; historical T0 must never be deleted merely because a newer schema exists.

---

## Findings

| Store | Writer | Retention behavior | Risk | Severity |
|-------|--------|--------------------|------|----------|
| `pattern_history.csv` (root) | `pattern_manager.write_pattern_history` | **Full rewrite** of entire CSV each save (`out.to_csv(PATTERN_FILE)`) | Accidental truncation/schema loss if write fails mid-way; GitHub overwrite of remote copy | **HIGH** |
| `data/earning_learning/pattern_history.csv` | `earning_learning._append_pattern_history` | Append-only with dedupe by observation hash; comment says “chống phình” (anti-bloat) via changed-only append | Does **not** purge old dates; low loss risk | LOW |
| `earning_money_snapshots.csv` | EMS / Streamlit capture | Append by snapshot_date (production path); workspace is cumulative | No code purge found; risk if operator replaces file | MEDIUM (ops) |
| `market_daily_t0.csv` | `market_t0_capture.append_market_daily_t0` | Append / merge; evening can update same trade_date fields | Mutable within-day; not historical truncate | LOW–MED |
| `forecast_t0_daily.csv` | `t0_persistence.persist_t0_record` | **First-write-wins** (`ALREADY_FROZEN`) | Safe against overwrite | LOW |
| `forecast_outcomes.csv` | `outcome_maturity` | Append-only; separate from T0 | Safe | LOW |
| `mdrr_daily.csv` | `mdrr.persist` | First-write-wins (`ALREADY_PRESENT`) | Safe | LOW |
| `historical_market_core.csv` | `historical_recovery.persist` | First-write-wins | Safe | LOW |
| `p0_market_daily.csv` | `p0_daily` | First-write-wins; foreign enrichment only when null | Safe; enrichment is fill-null only | LOW |
| Edge production observation backups | `production_backup._enforce_retention` | Keeps last N backups | Deletes **old backups**, not primary research CSVs | LOW (backup only) |
| Camera / `intraday_memory` parquet | collector | Feature matrix claims “no purge in code”; **no parquet present in this workspace** | Unknown on VPS; must verify retention on host | MEDIUM (unknown host) |

---

## Specific risks that can destroy history

1. **Root `pattern_history.csv` full rewrite** — largest risk to the longest MARKET CORE archive (43 dates FC+REAL). A failed/partial write or intentional “reset” loses multi-month scan memory.
2. **Operator `git checkout` / restore of data paths** — prior Forecast deploy audits already flagged unsafe checkout of `data/` and root CSVs.
3. **EMS replacement** — if EMS file is replaced rather than appended, Forecast T0 / outcomes / MDRR lose the only 142-DNA source.
4. **No automated archival** of root PH / EMS to immutable object store — single-disk copies.

---

## What does NOT purge Forecast Memory

- Forecast Memory daily stage does not delete prior T0/MDRR/P0/outcomes.
- Maturity only appends outcome rows.
- MDT0 gate skips freeze when MDT0 absent (does not invent PARTIAL irreversible rows when gated).

---

## Recommendations (design only — not implemented)

1. Treat root `pattern_history.csv` as **append-only or snapshot-versioned**; stop full rewrite, or write to dated partitions.
2. Nightly copy of `pattern_history.csv`, EMS, MDT0, `data/forecast_research/*` to cold storage.
3. Never `git checkout --` data paths on production.
4. Confirm VPS Camera/intraday parquet retention policy explicitly.

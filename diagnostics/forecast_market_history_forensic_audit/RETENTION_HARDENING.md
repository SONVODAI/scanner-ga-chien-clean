# Market History Retention Hardening

**Branch:** `cursor/p0-market-history-retention-aad2`  
**Verdict:** `MARKET_HISTORY_RETENTION_HARDENED`

---

## 1. Root cause of PH rewrite risk

`pattern_manager.write_pattern_history` performed a **non-atomic full-file `to_csv` replace**.

Failure modes:

1. **Interrupted write** truncated/corrupted `pattern_history.csv`.
2. **Incomplete in-memory frame** passed to `write_pattern_history` could overwrite disk (defense relied only on callers using `merge_history(read_…, new)`).
3. **`read_pattern_history` preferred GitHub over local** when a token existed — a **stale/thinner remote** could be merged/written and erase local dates.

`save_pattern_history` already did `merge_history(read_pattern_history(), new_samples)`, but write itself was not fail-closed or atomic.

---

## 2. Writers audited

| Store | Writer | Before | After |
|-------|--------|--------|-------|
| root `pattern_history.csv` | `pattern_manager.write_pattern_history` | Full rewrite, non-atomic | Disk ∪ proposed; date-shrink **refuse**; bounded backup; **atomic** replace |
| root PH read | `read_pattern_history` | GitHub-first | Local∪GitHub (never thinner remote alone) |
| EL `pattern_history.csv` | `earning_learning._append_pattern_history` | Append + hash dedupe | Unchanged (already append-safe) |
| `earning_money_snapshots.csv` | `snapshot_storage.save_history` | Atomic + backup keep=30 | Unchanged (already durable) |
| `market_daily_t0.csv` | `append_market_daily_t0` + storage write | First-write-wins by id | Unchanged |
| `forecast_t0_daily.csv` | `persist_t0_record` | First-write-wins; non-atomic | + atomic + backup + date guard |
| `forecast_outcomes.csv` | `persist_outcome_record` | Idempotent (date,horizon); non-atomic | + atomic + backup + date guard |
| `historical_market_core.csv` | `persist_historical_record` | First-write-wins; non-atomic | + atomic + backup + date guard |
| `mdrr_daily.csv` | `persist_mdrr_record` | First-write-wins; non-atomic | + atomic + backup + date guard |
| `p0_market_daily.csv` | `persist_p0_record` / enrich | First-write / null-fill; non-atomic | + atomic + backup + date guard |

---

## 3. Minimal durability changes

New: `modules/durable_csv.py` — `atomic_write_csv`, `create_bounded_backup` (keep=5 + hash manifest), `assert_date_coverage_not_shrunk`, `durable_replace_csv`.

Hardened: `pattern_manager.py`, `t0_persistence.py`, `mdrr.py`, `historical_recovery.py`, `p0_daily.py`.

No FC/REAL/LIVE formula changes. No new timer. No Streamlit requirement for Forecast Memory. No Edge/Camera/systemd changes.

---

## 4. Tests

`tests/test_market_history_retention.py` — **10 passed**:

- partial in-memory PH cannot erase old dates  
- date-shrink refuse leaves prior file  
- interrupted atomic write leaves prior file  
- same-day multi-scan compatible  
- bounded PH backups  
- Forecast T0 / MDRR immutable  
- P0 dates not deleted on enrich  
- outcomes idempotent by `(trade_date, horizon)`  
- schema evolution does not delete old T0  

Also re-ran Forecast-related gates (contract / hist+MDRR / P0 / integration) successfully.

---

## 5. Existing historical rows changed?

**No.** This task only changed code + tests. Production/workspace history CSVs were not rewritten by the hardening work.

---

## 6. Daily collection semantics changed?

**No functional change** to what is collected or when:

- Forecast Memory timer path unchanged  
- MDT0 gate unchanged  
- PH still saves on Streamlit scan path; now safer on write  
- EMS / MDT0 writers unchanged  

---

## 7. Remaining retention risks

- GitHub remote PH push still replaces remote content (local is protected first; remote could lag).  
- EL storage path still depends on TextStorage implementation.  
- Camera/intraday parquet retention not in scope (not present in workspace).  
- Operator `git checkout` of data paths remains an ops hazard.  
- Bounded backups keep last **5** only (by design).

---

## 8. Deployment recommendation

Deploy code-only (no data checkout) with Forecast Memory integration branch:

1. Pull retention hardening onto production HEAD after Forecast acceptance.  
2. Smoke: one Pattern Memory save → confirm `.pattern_history_backups/` appears and date count does not shrink.  
3. Do **not** restore/replace `pattern_history.csv` from Git during deploy.

---

## Final verdict

`MARKET_HISTORY_RETENTION_HARDENED`

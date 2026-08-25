# Foreign Flow Confirmation — Production Deployment Readiness

## Verdict

`FOREIGN_FLOW_CONFIRMATION_READY_TO_DEPLOY`  
`SAFE_TO_START_PROSPECTIVE_CONFIRMATION_AFTER_DEPLOY = YES`

**Constraints:** Operator must confirm live VPS HEAD before checkout; sync freeze canonical history for 60/252 continuity; **do not deploy PR #97 tip or `main`**. This audit did **not** deploy to VPS.

---

## 1. Production HEAD

| Source | Ref | Live verified? |
|--------|-----|----------------|
| Last documented prod | `8514fd7b2` (`phase-3k5b-waiting-data-retry`) | **NO** (no VPS access) |
| Forecast Memory intended | `d5d46be08` | Unknown if landed |
| GitHub `main` | `19cc913a7` | **Not production** |
| **Deploy this** | `bc8152810` integrate branch | Built this task |

See `PRODUCTION_LINEAGE.md`.

## 2. Required commit set

Clean integrate `bc8152810` = Forecast Memory tip `d5d46be08` + **52 files** (confirmation + HSX client + durable_csv retention helpers + hook).  
**Excluded:** ~50 PR #97 WIP Stage B CSV commits and blind-research runner.

## 3. Integration ref

`cursor/foreign-flow-confirmation-prod-integrate-aad2` @ **`bc8152810554129e31a9f59437e0e3c6583462ca`**

## 4. Diff vs production

- vs documented FM tip `d5d46be08`: **+52 files / ~7k lines** (safe)
- vs PR #97 tip: avoids **+124 data files / ~347k lines** WIP CSV baggage
- vs `main`: divergent — do not use

## 5. Tests

**62 passed / 0 failed** (1 vnstock legacy warning on Cloud Agent).  
Details: `PREDEPLOY_TEST_GATE.json`.

## 6. Runtime dependency status

| Component | Cloud Agent | Production expectation | Action |
|-----------|-------------|------------------------|--------|
| Python | 3.12.3 | 3.10+ at `/opt/mrbot-camera-venv` | Verify on VPS |
| numpy/pandas/scipy | present | present | No upgrade this task |
| vnstock | legacy banner | documented **≥4.0.5** for P0 collector | Confirm; **do not upgrade** here |
| HSX client | urllib stdlib | same | OK |
| Forecast Memory modules | on integrate base | required | Import smoke on VPS |
| Daily orchestrator | present | present | OK |

**Drift:** Cloud Agent vnstock ≠ documented production collector vnstock. Confirmation HSX path does **not** require vnstock. P0 remains isolated.

## 7. Data safety

New namespace `data/foreign_flow_confirmation/` only.  
Must not checkout/reset Forecast/Edge/EL/P0/pattern_history.  
Freeze `canonical/by_symbol` synced via **rsync**, not WIP git history.  
See `DATA_SAFETY.md`.

## 8. Automation path

Existing timer → daily research → Forecast Memory stage → P0 → **`ff_confirmation_forward`** → exact-date ingest → events → later T10.  
No second timer. Failures isolated. Idempotent.  
See `AUTOMATION_PROOF.md`.

## 9. Post-freeze semantics

- First eligible T0: `trade_date > 2026-08-24` (`LAST_IN_SAMPLE` gate in ledger/forward_panel/daily).
- Delayed ingest supported via checkpoint flag; frozen definitions only; no criteria change.
- Protocol hash bound to freeze artifacts.

## 10. Anti-peeking proof

- `counts_only_status` / operator summary strip mean/win/incremental.
- Baseline metrics stored `null` until judgment allowed.
- `compute_pass_fail_guard` refuses early PASS/FAIL.
- Tests assert banned keys absent.

## 11–12. Runbooks

- Deploy: `VPS_DEPLOY_RUNBOOK.md`
- Rollback: `ROLLBACK_RUNBOOK.md` (preserve confirmation data)
- First acceptance: `FIRST_LIVE_ACCEPTANCE.md`

---

## Deployment strategy (chosen)

```
operator confirms live HEAD
  → if lacks FM: bc8152810 still valid (contains FM ancestry) but larger blast radius — validate FM after
  → if already at/near d5d46be08: bc8152810 is minimal +52 file delta
  → checkout exact bc8152810
  → rsync freeze canonical (if needed)
  → smoke + first acceptance
  → never deploy df73282aa tip or main
```

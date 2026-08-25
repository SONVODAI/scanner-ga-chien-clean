# Production Lineage — Foreign Flow Confirmation

## Critical: GitHub `main` is NOT production

`origin/main` @ `19cc913a7` is dominated by Earning Learning / pattern journal updates.  
**Do not deploy `main` for this feature.**

## Last documented production HEAD (not live-verified this task)

| Item | Value |
|------|-------|
| Commit | `8514fd7b2` |
| Branch | `cursor/phase-3k5b-waiting-data-retry-aad2` |
| Evidence | `diagnostics/forecast_memory_ops_readiness/VPS_DEPLOY_RUNBOOK.md` |
| Live VPS check this task | **UNAVAILABLE** (`/opt/mrbot-camera` not on Cloud Agent) |

Operator **must** run `git rev-parse HEAD` on VPS before deploy and record it.

## Forecast Memory / retention status (documented intent)

```
8514fd7b2  phase-3k5b waiting-data retry   ← last documented prod base
    │
    ├─ … Forecast Data Contract / MDRR / P0 / HSX universe foreign …
    │
d5d46be08  cursor/forecast-memory-prod-integrate-aad2
    │         (production_daily_integration MDT0 stage + P0 hook)
    │
    ├─ 712e04371 forensic audit
    ├─ 15950622a / e07e12afb retention hardening (durable_csv)
    │
    └─ [PR #97 stacked ancestry — DO NOT deploy tip]
         └─ ~50 WIP Stage B CSV commits
         └─ blind research
         └─ confirmation protocol
         └─ forward panel wiring df73282aa
```

Whether Forecast Memory (`d5d46be08`) or retention is **already live** on VPS is **unknown** until operator confirms HEAD.

## PR #97 ancestry (why not deploy tip)

PR #97 head `df73282aa` first-parent history includes the entire Stage B WIP backfill (~50 commits, ~347k lines of canonical CSV).  
That is research history baggage, not a minimal production delta.

## Clean integration ref (this task)

```
d5d46be08  Forecast Memory tip
    │
    └─ bc8152810  cursor/foreign-flow-confirmation-prod-integrate-aad2
         52 files / +7003 lines
         = retention durable_csv + HSX client modules
           + confirmation protocol/runtime
           + ff_confirmation_forward hook
         EXCLUDES WIP CSV stack
```

### Git graph (simplified)

```
main (19cc913a7) ─── earning journals ─── ✗ not prod

8514fd7b2 (doc prod) ─── ? live VPS HEAD (operator confirm)
    \
     \──(if FM not deployed)──► deploy path may land FM+FF via bc8152810
      \
d5d46be08 (FM integrate) ──► bc8152810 (FF confirmation clean integrate)  ✓ deploy this
                               ^
df73282aa (PR #97 tip) ── huge WIP data ancestry ── ✗ do not checkout tip
```

## Commits required vs excluded

| Include | Exclude |
|---------|---------|
| Content of `bc8152810` vs `d5d46be08` | PR #97 WIP Stage B progress commits |
| Separate **rsync** of freeze `canonical/by_symbol` | Blind research runner module |
| | Unrelated Edge/Camera/Streamlit PRs |
| | `origin/main` |

## Diff summary

| Compare | Files | Note |
|---------|-------|------|
| `d5d46be08..bc8152810` | **52** | Clean production delta |
| `d5d46be08..df73282aa` | 52 code+diag + **124 data** (~347k lines) | PR #97 tip baggage |
| `origin/main..bc8152810` | large / divergent | Wrong base |

# Live Candidate V2 Follow-up Watch V1

SHADOW / RESEARCH ONLY. Production scan, Market First, Buy Elite, Sweet Observer,
Learning Insight, and the ordinary V2 Action path do not depend on this directory
when the feature flag is OFF.

## Feature flag (default OFF)

```bash
# enable research cycle
export MRBOT_V2_FOLLOWUP_WATCH=1

# optional override directory
export MRBOT_V2_FOLLOWUP_DIR=/path/to/research/live_candidate_v2_followup
```

Unset / `0` / `false` / `off` keeps the feature fully inert.

## Runtime files (gitignored)

| File | Role |
|------|------|
| `followup_registry.json` | Durable ACTIVE / BUY_READY / EXPIRED / REJECTED registry |
| `followup_ledger.jsonl` | Append-only measurement arms A/B/C |
| `followup_session_log.jsonl` | Optional session diagnostics |

## TTL

Maximum **5 VNIndex trading sessions inclusive** of `original_session`.
Each session re-reads Setup / Market permission / Guardian / WHEN from current
inputs. Prior WAIT state and prior Setup are never inherited as buy rights.

## Arms

- **A_BASELINE_V2** — ordinary V2 Action snapshot
- **B_FOLLOWUP_WATCH** — follow-up multi-session path
- **C_FOLLOWUP_GUARDIAN** — follow-up + Guardian SELL reject tagging

## Rollback

1. Leave `MRBOT_V2_FOLLOWUP_WATCH` unset (default).
2. Do not schedule `scripts/run_v2_followup_watch.py`.
3. Registry/ledger files are additive under this directory only.

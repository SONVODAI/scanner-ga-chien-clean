# Live Candidate V2 Follow-up Watch V1 (+ Candidate Guardian)

SHADOW / RESEARCH ONLY. Production scan, Market First, Buy Elite, Sweet Observer,
Learning Insight, and the ordinary V2 Action path do not depend on this directory
when the feature flag is OFF.

## Feature flag (default OFF)

```bash
export MRBOT_V2_FOLLOWUP_WATCH=1
export MRBOT_V2_FOLLOWUP_DIR=/path/to/research/live_candidate_v2_followup
```

Unset / `0` / `false` / `off` keeps the feature fully inert.

See [ACTIVATION.md](./ACTIVATION.md) for post-approval enablement (no VPS scheduler
changes are applied by this PR).

## Automatic SHADOW path (flag ON only)

1. **Observe hook** (`observe_store.observe_from_collected_session`)
   - Records arm-A baseline
   - Ingests WAIT nominations into durable registry
   - Re-evaluates ACTIVE candidates (Setup / Market First / Candidate Guardian / TTL)
   - Writes `followup_camera_queue.json`
   - Best-effort as-of T3/T5/T10 maturity (no future prices)
2. **Camera 5m hook** (`LiveShadowFeed` WHEN cycle)
   - Merges Follow-up camera rows into actionable universe under existing cap
   - Strips any stale BUY_READY / buy rights before observation
3. **Manual / scheduled scripts**
   - `scripts/run_v2_followup_watch.py`
   - `scripts/run_v2_followup_mature.py`

## Runtime files (gitignored)

| File | Role |
|------|------|
| `followup_registry.json` | Durable ACTIVE / BUY_READY / EXPIRED / REJECTED registry |
| `followup_ledger.jsonl` | Append-only measurement arms A/B/C |
| `followup_camera_queue.json` | Current-session Camera fill rows |
| `followup_session_lock.json` | Per-session idempotency marker |

Corrupt registries are **quarantined** (`.corrupt.<timestamp>`), never silently reset.

## TTL / Candidate Guardian

- TTL = **5 VNIndex sessions inclusive** of `original_session`
- Quality: STRONGER / STABLE / WEAKENING / REJECTED
- Market Real &lt; 6 blocks BUY only; never rejects a still-strong name
- Position Guardian SELL is soft metadata only

## Arms

- **A_BASELINE_V2** — ordinary V2 Action snapshot
- **B_FOLLOWUP_WATCH** — follow-up without Candidate Guardian gates
- **C_FOLLOWUP_GUARDIAN** — follow-up + Candidate Guardian (registry path)

## Rollback

1. Leave `MRBOT_V2_FOLLOWUP_WATCH` unset (default).
2. Do not schedule the research scripts.
3. Artifacts under this directory only.

# Live Candidate V2 Follow-up Watch V1 (+ Candidate Guardian)

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
No infinite extension. Each session re-reads Setup / Market permission /
Candidate Guardian / WHEN from current inputs. Prior WAIT state and prior Setup
are never inherited as buy rights.

## Candidate Guardian (quality layer)

Classifies ACTIVE candidates each session:

| Label | Meaning |
|-------|---------|
| `STRONGER` | Trend + flow improving — continue WAIT for WHEN (never auto BUY_READY) |
| `STABLE` | Holds base / healthy pullback — keep watching |
| `WEAKENING` | Soft deterioration — arm C blocks BUY_READY |
| `REJECTED` | Confirmed trend break or setup collapse — leave Follow-up Watch |

Rules:

- Inspired by Position Guardian factors (EMA9 / MA20 / OBV / RS) but **not** a
  mechanical copy of held-position SELL → reject.
- Healthy pullback (price soft under EMA9, EMA9 ≥ MA20, OBV not broken) stays
  `STABLE`.
- **Market Real < 6** blocks BUY via Market Permission only; never rejects a
  still-strong candidate.
- Position Guardian `BÁN` is soft metadata only.
- Rejection reasons + post-reject T3/T5/T10 are ledgered to measure false rejects.

## Arms (parallel measurement)

- **A_BASELINE_V2** — ordinary V2 Action snapshot (no multi-session follow-up)
- **B_FOLLOWUP_WATCH** — follow-up 5 sessions **without** Candidate Guardian gates
- **C_FOLLOWUP_GUARDIAN** — follow-up + Candidate Guardian (registry / camera path)

Compare C vs B vs A for false-signal reduction, drawdown, and whether large winners
are retained.

## Rollback

1. Leave `MRBOT_V2_FOLLOWUP_WATCH` unset (default).
2. Do not schedule `scripts/run_v2_followup_watch.py`.
3. Registry/ledger files are additive under this directory only.

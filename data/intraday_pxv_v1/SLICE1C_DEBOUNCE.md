# Slice 1C — published-evidence debounce (shadow only)

Implemented. RAW one-bar P×V is unchanged. A separate PUBLISHED state requires
2 consecutive RAW STRENGTHEN/WEAKEN to enter or reverse. A single RAW NEUTRAL
returns published S/W to NEUTRAL. UNUSABLE stays authoritative.
`alert_eligible` remains false. Thresholds unchanged. No hysteresis, cooldown,
T+n, Camera writes, live poller, or production changes.

Ledger fields: `raw_evidence`, `published_evidence` (`evidence` = published).

## Official 16-session replay

This Cloud Agent host does **not** have the Camera archive or
`/tmp/pxv-v1-slice1-out/shadow_ledger.jsonl`. Production hashes on this checkout
are unchanged.

On the isolated VPS clone (do **not** checkout this PR on `/opt/mrbot-camera`):

```
cd /tmp/pxv-v1-slice1c   # clone this commit
# optional: copy existing Slice 1 ledger; Camera not required if ledger exists
python scripts/replay_intraday_pxv_v1_debounce.py \
  --ledger /tmp/pxv-v1-slice1-out/shadow_ledger.jsonl \
  --out /tmp/pxv-v1-slice1c-debounce
```

That writes only `--out`: new ledger with both fields, `debounce_compare.md`,
production hash before/after.

If Camera is mounted (`MRBOT_INTRADAY_DATA_ROOT=/var/lib/mrbot/intraday_memory`),
the same script does a full interpret replay (same gates, same candidates).

## State-machine identity (not a substitute for replay)

Official Slice 1B RAW runs: 967 S/W, 814 one-bar, 153 ≥2, 27 ≥3.

If PUBLISHED = second bar of each RAW S/W run:

| metric | expected published |
|---|---:|
| S/W runs | 153 |
| 1-bar | 126 (RAW exactly 2 bars) |
| ≥2 bars | 27 |
| first print | RAW persist≥2 first print + 5m |

That pattern is **DEBOUNCE_PARTIAL** under the pre-declared rule: 1-bar RAW
spikes are removed, but most remaining published events last one published bar
(confirmed-then-fade). Timing before 14:00 should survive.

Confirm on the VPS compare table. Do not use T+n to pick a verdict.

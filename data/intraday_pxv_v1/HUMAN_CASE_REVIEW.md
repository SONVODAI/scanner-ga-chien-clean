# Slice 1C published-evidence human case review

Read-only. No Interpreter change. No T+n. No live UI/alerts.

This Cloud Agent host does **not** have
`/tmp/pxv-v1-slice1c-debounce/shadow_ledger.jsonl`.
The 10–15 real timelines must be printed from that official ledger.
Do not invent symbols or bars.

One isolated command (not `/opt/mrbot-camera`):

```
python /tmp/pxv-v1-slice1c/scripts/review_intraday_pxv_v1_published_cases.py \
  --ledger /tmp/pxv-v1-slice1c-debounce/shadow_ledger.jsonl \
  --out /tmp/pxv-v1-slice1c-human-review
```

Requires isolated checkout at commit that contains
`scripts/review_intraday_pxv_v1_published_cases.py`.

## HUMAN REVIEW VERDICT (from official 1C census, not T+n)

**PARTIALLY_HUMAN_USABLE**

Published evidence is now readable as a *state*, not a 5-minute strobe.
It is not yet clean enough that every published print should become a UI toast.

## Official census (operator VPS replay)

| | RAW | PUBLISHED |
|---|---:|---:|
| S/W runs | 967 | 152 |
| 1-bar | 814 | 108 |
| ≥2 bars | 153 | 44 |
| ≥3 bars | 27 | 11 |
| ≥15 min | 11 | 3 |
| ≥30 min | 7 | 1 |
| S↔W reversals | 122 | 2 |

First published S/W: 09:15–10:00=9, 10:00–11:30=44, 13:00–14:00=74, 14:00–close=25.

Sessions: noisy=6, clean_persistent=9, never_leave_NEUTRAL=39, unusable=2.

Safety: `alert_eligible=0`, DGC published S/W=false, production hashes unchanged.

## A–G (human readability only)

**A.** Case-level USEFUL/BORDERLINE/NOISY/UNUSABLE counts require the official
ledger dump above. Do not invent them. The extractor labels coherence from
features already on each row (not T+n).

**B. 108 published one-bar runs** are a **mixture**, not a return of RAW flicker.
Each one required two consecutive RAW S/W bars. They are confirmed-then-fade
(spike entered the 6-bar window on the next print). That can be legitimate
short-lived information. They are still a majority of published *runs* (108/152
= 71%), so blasting each as a UI popup would feel noisy. Showing them as a
one-bar highlight on a visible Candidate strip is coherent.

**C. 44 ≥2-bar published runs** are materially more interpretable: the condition
held after confirmation. This is the standing-evidence set a human can read
without a stopwatch.

**D. 11 ≥3-bar published runs** are qualitatively cleaner again (and rare).
They are the “this is still on” cases. Too few to be the only UI surface.

**E. 2 remaining S↔W reversals** (122→2) are almost certainly **genuine
two-sided expansion** (or the last residue of it), not state-machine chatter.
A published reverse needs two RAW opposite bars. Dump those two sessions
with the review script before treating them as a bug.

**F. GMD 2026-08-28** must be printed from the ledger. If published never
leaves NEUTRAL while RAW flickers, silence is correct. The review script
always includes this session.

**G. Another state-machine change is not required** for evidence quality.
The approved 2-bar publish rule did the job: 814 RAW one-bar spikes are gone;
reversals collapsed; afternoon timing survived (74 first prints 13:00–14:00).
A third debounce or hysteresis would hide the 108 confirmed-then-fade events
without a human readability failure that those events are *false*. The gap is
**UI presentation**, not another Interpreter rule.

## Recommendation

**KEEP CURRENT STATE MACHINE**

Next product step (design only, not implemented): Candidate list visible in
the app; each name shows evolving PUBLISHED P×V (NEUTRAL / STRENGTHEN /
WEAKEN / UNUSABLE) as a strip, updated on 5m close. Optional informational
alert only when published holds ≥2 bars. Human decides. No BUY/SELL.

Architecture stays:

BOT Candidate → Dynamic/Core Watchlist → Live 5m Camera → RAW P×V →
PUBLISHED P×V → **visible on UI** → optional meaningful alert → Human decides.

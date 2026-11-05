# Follow-up Watch — Activation (post-approval only)

**Do not enable on VPS until explicitly approved.**

This document prepares the SHADOW automatic path. It does **not** modify
production VPS schedulers by itself.

## Feature flag (default OFF)

```bash
unset MRBOT_V2_FOLLOWUP_WATCH          # OFF — BOT unchanged
export MRBOT_V2_FOLLOWUP_WATCH=1       # ON — SHADOW research only
export MRBOT_V2_FOLLOWUP_DIR=/var/lib/mrbot/research/live_candidate_v2_followup
export MRBOT_V2_FOLLOWUP_MARKET_REAL=7.0
export MRBOT_V2_FOLLOWUP_TRADING_DATES=2026-10-06,2026-10-07,...
# optional:
export MRBOT_V2_FOLLOWUP_SCAN_CSV=/path/to/scan.csv
export MRBOT_V2_FOLLOWUP_PRICE_JSON=/path/to/symbol_session_prices.json
export MRBOT_V2_FOLLOWUP_VNINDEX_JSON=/path/to/vnindex_session_prices.json
```

## Runtime hooks (already in code, flag-gated)

| Hook | When flag ON |
|------|----------------|
| `observe_from_collected_session` | Ingest + session re-eval + camera queue + as-of mature |
| `LiveShadowFeed` WHEN cycle | Merge Follow-up camera rows into actionable universe (cap unchanged) |
| `scripts/run_v2_followup_watch.py` | Manual / scheduled research tick |
| `scripts/run_v2_followup_mature.py` | Manual / scheduled as-of maturity |

## Suggested cron (NOT installed — paste only after approval)

```cron
# EXAMPLE ONLY — do not install until approved.
# Post-close research tick (Asia/Ho_Chi_Minh 15:30 weekdays)
# 30 15 * * 1-5  cd /opt/mrbot && MRBOT_V2_FOLLOWUP_WATCH=1 \
#   python scripts/run_v2_followup_watch.py --session "$(date +\%F)" \
#   --trading-dates-file "$MRBOT_V2_FOLLOWUP_TRADING_DATES_FILE"
#
# Outcome maturity (Asia/Ho_Chi_Minh 18:00 weekdays)
# 0 18 * * 1-5  cd /opt/mrbot && MRBOT_V2_FOLLOWUP_WATCH=1 \
#   python scripts/run_v2_followup_mature.py --as-of "$(date +\%F)"
```

## Safety checks before enabling

1. Confirm `candidate_is_buy` / `alert_eligible` / `pxv_implies_buy` remain False.
2. Confirm production BUY / Elite / Sweet paths unchanged with flag OFF.
3. Confirm registry path is writable and backed up.
4. Confirm trading-dates source (prefer VNINDEX list; weekday fallback may include holidays).
5. Do **not** merge this PR into a deploy that sets the env var without approval.

# Rollback Runbook — Foreign Flow Confirmation

## Principle

Rollback **code** to pre-deploy HEAD.  
**Preserve** newly collected confirmation data unless corruption is demonstrated.

## Procedure

```bash
cd /opt/mrbot-camera
PRE=$(cat /tmp/mrbot-pre-ff-confirm.HEAD)
test -n "$PRE"

# 1) Stop only if a oneshot run is active (usually already dead)
systemctl status mrbot-daily-research.service --no-pager || true

# 2) Restore code only
git fetch origin  # if needed
git checkout "$PRE"
git rev-parse HEAD | tee /tmp/mrbot-rollback-ff-confirm.HEAD
test "$(git rev-parse HEAD)" = "$PRE"

# 3) DO NOT restore confirmation ledgers from backup by default
# Keep:
#   data/foreign_flow_confirmation/events/
#   data/foreign_flow_confirmation/outcomes/
#   data/foreign_flow_confirmation/forward_panel/
#   data/foreign_flow_confirmation/baselines/
#   data/foreign_flow_confirmation/manifests/

# 4) DO NOT git-checkout runtime Forecast/Edge/EL/P0 CSVs

# 5) Import smoke on rolled-back tree
/opt/mrbot-camera-venv/bin/python -c "print('rollback_code_ok')"
```

## When to restore confirmation data from backup

Only if integrity checks fail, e.g.:

- forward panel dates **shrunk** vs pre-deploy hash inventory
- event JSONL rewritten/corrupted (duplicate key storms with conflicting payloads)
- freeze canonical history damaged

Then restore **only** the corrupted subtree from `/var/backups/mrbot-ff-confirm-*`.

## Timer

Leave `mrbot-daily-research.timer` as it was pre-deploy (do not disable unless whole daily research must stop).

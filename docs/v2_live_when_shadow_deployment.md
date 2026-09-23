# V2 live SHADOW WHEN — future VPS deployment (do not execute from this change)

This document is the operator procedure for a later, separate deployment.
The code change that added it does not install units, does not start a
timer, does not call KBS, and does not write the Camera archive.

## Must not touch

- `/opt/mrbot-camera`
- `/var/lib/mrbot/intraday_memory`
- `mrbot-intraday-collect.service` / `mrbot-intraday-collect.timer`
- `mrbot-intraday-reconcile.service` / `mrbot-intraday-reconcile.timer`
- Rotation Watch (`scripts/run_rotation_watch.py`, no unit)
- post-close research and `scripts/vps_update_live_shadow_v2.sh` observe clocks
- Brain A nomination logic
- SweetSpot nomination logic
- `mrbot-v2-shadow-observe.service` / `mrbot-v2-shadow-observe.timer`
- `evaluate_shadow_action` thresholds and BUY permission flags

Do not run `scripts/vps_update_live_shadow_v2.sh` as the way to turn this
path on. That script installs the post-close observer only and must stay
that way.

## What is copied to `/opt/mrbot-live-shadow`

Use the existing allowlist installer. It already refuses `--live` and does
not enable any timer:

```bash
# PLAN ONLY. Prints the file list. Copies nothing.
bash scripts/vps_install_live_camera_consumer.sh

# Later, on the VPS, after a human sets APPROVED_REV to this merge SHA:
APPROVED_REV=<sha> INSTALL_CONFIRM=YES \
  bash scripts/vps_install_live_camera_consumer.sh install
```

New files on that allowlist:

- `modules/live_camera_shadow/cycle_lock.py`
- `modules/live_camera_shadow/when_schedule.py`
- `modules/live_candidate_v2_action/live_universe.py`

Also required, already on the allowlist: `scripts/run_live_camera_shadow.py`,
`modules/live_camera_shadow/feed.py`, `modules/live_camera_shadow/bars.py`,
`modules/intraday_memory/provider.py` (listed as `LATER_LIVE_ONLY`), and the
existing P×V / Action modules. The installer does not copy systemd units.

## What is installed later, and only by hand

Separate units. They are not drop-ins of the collect or observe units.

- `deploy/systemd/mrbot-v2-live-when.service`
- `deploy/systemd/mrbot-v2-live-when.timer`

```bash
install -m 644 deploy/systemd/mrbot-v2-live-when.service /etc/systemd/system/
install -m 644 deploy/systemd/mrbot-v2-live-when.timer /etc/systemd/system/
systemctl daemon-reload
# Do not enable yet. Dry-run first.
```

The service working directory is `/opt/mrbot-live-shadow`. It does not set
`MRBOT_INTRADAY_DATA_ROOT`. Output is
`/var/lib/mrbot/live_pxv_shadow/v2_live_when`. The published state copy is
the existing store `/var/lib/mrbot/live_pxv_shadow`.

## Plan / dry-run first

On the VPS, after the file copy and before `enable`:

```bash
cd /opt/mrbot-live-shadow
PYTHONPATH=/opt/mrbot-live-shadow \
  /opt/mrbot-camera-venv/bin/python scripts/run_live_camera_shadow.py --v2-when
```

Expected: exit 0, stderr contains `DRY RUN: refusing KBS` and
`v2_when_dry_run` with `kbs_polled: false`. No network read of KBS.
No write under `/var/lib/mrbot/intraday_memory`.

Then one manual oneshot only inside a cash-session fire window, after the
operator has accepted the dry-run:

```bash
systemctl start mrbot-v2-live-when.service
systemctl status mrbot-v2-live-when.service --no-pager
```

`start` of the service runs one cycle. It does not enable the timer.

## Verify archive isolation

```bash
# Archive mtime must not change across the oneshot.
stat -c '%y %n' /var/lib/mrbot/intraday_memory/bars.parquet \
  /var/lib/mrbot/intraday_memory/.collector.lock
# Live lock is a different file.
stat -c '%y %n' /var/lib/mrbot/live_pxv_shadow/v2_live_when/.v2_live_when.lock
# Collect and observe units were not restarted.
systemctl show mrbot-intraday-collect.timer mrbot-v2-shadow-observe.timer \
  -p Id -p ActiveState -p UnitFileState --no-pager
```

Journal of the oneshot must show `archive_writes: 0`.

## Verify KBS polls only the selected universe

The status JSON written to
`/var/lib/mrbot/live_pxv_shadow/v2_live_when/live_shadow_status.json`
has `v2_union.policy = v2_actionable_only` and `v2_union.symbols`.
That list must be a subset of the current Gate-B sidecar rows whose setup
is `PULL ĐẸP`, `PULL VỪA`, `CP MẠNH`, or `MUA BREAK`, with `eligible_from`
already reached, length at most 50. `MUA EARLY` and empty Sweet setups
must be absent. `fetched_symbols` must match that list. `kbs_polled` is
false when the list is empty.

## Verify timer windows

Do this before `enable --now` if the current clock is inside 09:20–14:50
on a weekday; otherwise a start would poll immediately.

```bash
systemd-analyze calendar --iterations=60 \
  'Mon..Fri *-*-* 09:20,25,30,35,40,45,50,55:45 Asia/Ho_Chi_Minh' \
  'Mon..Fri *-*-* 10:00,05,10,15,20,25,30,35,40,45,50,55:45 Asia/Ho_Chi_Minh' \
  'Mon..Fri *-*-* 11:00,05,10,15,20,25,30:45 Asia/Ho_Chi_Minh' \
  'Mon..Fri *-*-* 13:05,10,15,20,25,30,35,40,45,50,55:45 Asia/Ho_Chi_Minh' \
  'Mon..Fri *-*-* 14:00,05,10,15,20,25,30,35,40,45,50:45 Asia/Ho_Chi_Minh'
```

Expected: 49 fires per weekday, first `09:20:45`, last morning `11:30:45`,
first afternoon `13:05:45`, last `14:50:45`. No `12:*`. No time after
`14:50:45`. `Persistent=false`, so a stopped timer does not catch up.

Only after that check:

```bash
systemctl enable --now mrbot-v2-live-when.timer
systemctl list-timers mrbot-v2-live-when.timer --no-pager
```

## Disable / rollback independently

```bash
systemctl disable --now mrbot-v2-live-when.timer
systemctl stop mrbot-v2-live-when.service
rm -f /etc/systemd/system/mrbot-v2-live-when.timer \
      /etc/systemd/system/mrbot-v2-live-when.service
systemctl daemon-reload
```

That removes only the live WHEN path. Collect, reconcile, post-close
observe, `/opt/mrbot-camera`, and `/var/lib/mrbot/intraday_memory` stay
as they were. The shadow JSON under `/var/lib/mrbot/live_pxv_shadow` can
be left in place; Streamlit treats it as stale after 600 seconds.

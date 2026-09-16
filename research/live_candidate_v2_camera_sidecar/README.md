# LIVE CANDIDATE V2 — Slice 2 Camera sidecar (SHADOW ONLY)

Transport path for Camera observation. Candidate ≠ BUY.

This is **not** `data/live_candidate/dynamic_watchlist.json`.
Slice 2 does **not** publish to GitHub and does **not** start the live runner.

## Path

- Writer: `modules/live_candidate_v2_camera/`
- Default artifact: `research/live_candidate_v2_camera_sidecar/camera_sidecar.json`
- Sample: `research/live_candidate_v2_camera_sidecar/camera_sidecar.sample.json`

## Flow (tests inject LiveShadowFeed; no runner)

Brain A nomination → shadow Router (`enabled_sources={brain_a_scan_setup}`)
→ V2 sidecar rows → `LiveShadowFeed.run_cycle(watchlist=sidecar)`
→ synthetic completed 5m bars → generic P×V evidence.

Production `ENABLED_SOURCES` stays Elite-only. Brain B is not required.

## Units (Slice 2)

`close_vs_ref` is `close − named frozen field` as stored. Camera bars are
integer VND after `validate_raw_bar` (e.g. `27700`). Brain A frozen refs stay
in scan units (e.g. `ema9_at_first_seen=27.1`). Slice 2 does not convert and
does not invent a level.

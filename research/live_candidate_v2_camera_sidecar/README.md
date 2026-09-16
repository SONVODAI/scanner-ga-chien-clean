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

Canonical comparison unit is Camera **integer VND**, via the existing helper
`modules.intraday_memory.normalize.normalize_price_to_integer_vnd` (same
contract as `validate_raw_bar` / `CanonicalBar`).

- Brain A sidecar frozen refs stay as stored (scan-price units, e.g. `27.1`).
- Camera evidence `close` stays as stored (integer VND after validate, e.g. `27700`).
- At the observe boundary both sides are normalized once.
- `close_vs_ref` / `close_vs_ref_pct` emit only when both normalize.
- Helper rejection → `reference_state=UNIT_MISMATCH` and null deltas.
- Missing ref → `UNAVAILABLE`. No second scale convention. No BUY/SELL mapping.

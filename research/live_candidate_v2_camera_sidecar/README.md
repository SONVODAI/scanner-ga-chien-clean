# LIVE CANDIDATE V2 — Camera sidecar (SHADOW ONLY)

Transport path for Camera observation. Candidate ≠ BUY.

This is **not** `data/live_candidate/dynamic_watchlist.json`.
Does **not** publish to GitHub in Slice 3A and does **not** start the live runner.

## Path

- Writer: `modules/live_candidate_v2_camera/`
- Default artifact: `research/live_candidate_v2_camera_sidecar/camera_sidecar.json`
- Sample: `research/live_candidate_v2_camera_sidecar/camera_sidecar.sample.json`

## Slice 3A Cloud hook (default OFF)

Gate: `MRBOT_LIVE_CANDIDATE_V2_CLOUD_SIDECAR`
Truthy: `1` / `true` / `yes` / `on` (case-insensitive). Unset/empty/`0`/`false`/`no`/`off` = OFF.

When ON, `app.py` writes this sidecar locally after Elite and before production
Candidate publish. `freeze_ledger` is reloadable across Streamlit reruns and
process restarts. Missing file is a first run. Corrupted file is a V2 failure,
not a valid empty universe.

## Slice 3B GitHub Contents transport (default OFF)

Dedicated path: `research/live_candidate_v2_camera_sidecar/camera_sidecar.json`

Gate B: `MRBOT_LIVE_CANDIDATE_V2_GITHUB_PUBLISH`
Truthy: `1` / `true` / `yes` / `on` (case-insensitive). Default OFF.
Independent of Gate A. Enabling the local sidecar does **not** publish.
Enabling publish does **not** generate nominations.

Publish only a successfully written valid local document (including `rows: []`).
Fetch/validate distinguishes OK_ROWS, OK_EMPTY, NOT_FOUND, INVALID_DOCUMENT,
TRANSPORT_ERROR. Missing or corrupt GitHub objects are not an empty universe.

Reuses `fetch_github_watchlist_text` / `publish_watchlist_bytes` with the V2
path pinned. Production `GITHUB_WATCHLIST_PATH` and `fetch_published_watchlist()`
are unchanged. No KBS. No runner.


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

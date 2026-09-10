# LIVE SESSION 01 — controlled deployment preparation

**STOPPED after failed production preflight. No production mutation. LIVE SESSION 01 not started.**

Human deploy decision was APPROVED. This agent then checked whether it could execute the change reversibly. It cannot reach Streamlit Cloud admin or the Camera VPS from this environment, so it **did not deploy**.

## Verdict

| | Check | Answer |
|---|---|---|
| **A** | STREAMLIT_DEPLOYED_OK | **NO** |
| **B** | VPS_ARTIFACT_DEPLOYED_OK | **NO** |
| **C** | EXISTING_PRODUCTION_HEALTHY | **NO** (not proven from this agent) |
| **D** | CAMERA_ARCHIVE_UNCHANGED | **YES** |
| **E** | LIVE_RUNNER_STILL_STOPPED | **YES** |
| **F** | READY_TO_START_LIVE_SESSION_01 | **NO** |

`F=NO` — do **not** start the live Camera shadow runner.

## Preflight blocker (stop condition)

Recorded **before** any production write:

| Access | Result |
|---|---|
| Streamlit Cloud admin / deploy token | **ABSENT** |
| `GITHUB_TOKEN` in this environment | **ABSENT** (names only) |
| `EDGE_RESEARCH_DURABLE_URL` | **ABSENT** |
| `EDGE_RESEARCH_DURABLE_TOKEN` | **ABSENT** |
| SSH / `~/.ssh` | **ABSENT** |
| Cursor self-hosted worker on Camera VPS | **none connected** |
| Stacked transport revision on `origin/main` | **NO** (`main` is still `1f68283bd`) |

Secret **values were not printed**. Presence only.

`https://scanner-ga-chien-clean.streamlit.app` exists and is auth-gated (login redirect). This agent could not open production panels or confirm Streamlit secrets `GITHUB_TOKEN` / `EDGE_RESEARCH_DURABLE_*` on Cloud.

Per the deploy order (“stop immediately on any failed preflight/proof”), **no** merge to `main`, **no** VPS overlay, **no** artifact restart, **no** runner start.

## Rollback revisions recorded (unused — nothing deployed)

Keep these if a later operator with VPS/Streamlit access continues:

| Surface | Rollback revision / config |
|---|---|
| Streamlit Cloud / `origin/main` | `1f68283bdc25d6d2ce14413d13b4e0661100bcad` (“Update pattern history 2026-09-09 21:07:28”) |
| Approved stack (not deployed) | `fedc7d53cb9a902bb7aa73760f00d402f913ed22` on `cursor/live-e2e-transport-1dd0` |
| `/opt/mrbot-camera` | **not contacted** — leave on its current production checkout |
| `/var/lib/mrbot/intraday_memory` | **not contacted** — no hash baseline from VPS |
| `mrbot-edge-artifacts.service` | **not restarted** |
| Live runner | **never started** (no PID, no `--live`) |

If a later overlay **is** applied on the VPS, rollback is:

```bash
sudo bash /tmp/scanner-live-session-01/scripts/vps_rollback_live_shadow_artifacts.sh \
  /var/lib/mrbot/live_pxv_shadow_overlay_backup/<stamp>
```

Streamlit rollback if someone later merges the stack to `main`: reset/pin Cloud to `1f68283bd`.

## Source proofs that did pass (not a production deploy)

From `scripts/proof_live_session_01_deploy.py` on this checkout:

- `vnstock==0.2.9.2` still pinned in `requirements.txt`
- Existing production panel titles still present in `app.py`
- Read-only UI still has no KBS / Camera / Interpreter calls
- Empty / no-Candidate UI still renders “No active BOT Candidate.”
- `alert_eligible` forced false
- Live runner / overlay scripts do not add Telegram or order placement
- Live runner is stopped

These prove the **code** is still isolated. They do **not** prove Cloud or VPS are running the stack.

## What an operator with VPS + Streamlit access must do next

Small reversible steps. Stop on any failed proof.

1. **Streamlit Cloud** — deploy stacked revision `fedc7d53c` (merge/pin the research stack onto the Cloud app branch). Keep `vnstock==0.2.9.2`. Confirm secret **names** exist: `GITHUB_TOKEN`, `EDGE_RESEARCH_DURABLE_URL`, `EDGE_RESEARCH_DURABLE_TOKEN`. Do not paste values into git.
2. **VPS** — isolated clone only. Do **not** switch `/opt/mrbot-camera` onto the PR:

   ```bash
   git clone --branch cursor/live-e2e-transport-1dd0 \
     https://github.com/SONVODAI/scanner-ga-chien-clean.git /tmp/scanner-live-session-01
   cd /tmp/scanner-live-session-01
   git checkout fedc7d53cb9a902bb7aa73760f00d402f913ed22
   export MRBOT_ISOLATED_CLONE=/tmp/scanner-live-session-01
   export MRBOT_LIVE_PXV_SHADOW_STORE=/var/lib/mrbot/live_pxv_shadow
   export MRBOT_WATCHLIST_SOURCE=github
   sudo -E bash scripts/vps_overlay_live_shadow_artifacts.sh
   ```

   That copies **only** `artifact_server.py`, creates `/var/lib/mrbot/live_pxv_shadow`, writes runner env (unused), restarts **only** `mrbot-edge-artifacts.service`.
3. Re-run `python3 scripts/proof_live_session_01_deploy.py` **on a host that has** `EDGE_RESEARCH_DURABLE_URL` + token (and optionally `MRBOT_STREAMLIT_URL`). Require A–E = YES before F can become YES.
4. Do **not** start LIVE SESSION 01 until F=YES.

## Start command — DO NOT RUN (F=NO)

When a later proof returns `F_READY_TO_START_LIVE_SESSION_01=YES`, use this **one** block on the VPS isolated clone (human only, VN cash session). **Do not run it now.**

```bash
export MRBOT_REPO=/tmp/scanner-live-session-01
export MRBOT_LIVE_PXV_SHADOW_STORE=/var/lib/mrbot/live_pxv_shadow
export MRBOT_WATCHLIST_SOURCE=github
export MRBOT_LIVE_CANDIDATE_OUT="$MRBOT_REPO/data/live_candidate"
export MRBOT_LIVE_CAMERA_SHADOW_OUT="$MRBOT_REPO/data/intraday_pxv_live_shadow"
mkdir -p "$MRBOT_LIVE_CANDIDATE_OUT" "$MRBOT_LIVE_CAMERA_SHADOW_OUT"
set -a && source /etc/mrbot/live-shadow.env && set +a
nohup bash -c 'while true; do
  /opt/mrbot-camera-venv/bin/python "$MRBOT_REPO/scripts/run_live_camera_shadow.py" --live
  sleep 60
done' > "$MRBOT_LIVE_CAMERA_SHADOW_OUT/runner.log" 2>&1 & echo $! > /tmp/mrbot_live_session_01.pid
echo "PID=$(cat /tmp/mrbot_live_session_01.pid)"
```

Stop later: `kill "$(cat /tmp/mrbot_live_session_01.pid)"` — Camera archive stays untouched.

## Safety

- No merge to `main`
- No checkout of this PR on `/opt/mrbot-camera`
- Camera archive not written
- Artifact service not restarted
- Live runner not started
- No BUY/SELL, Telegram, alerts, threshold, debounce, or Candidate scoring changes
- Streamlit `vnstock==0.2.9.2` unchanged

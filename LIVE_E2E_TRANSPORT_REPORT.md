# LIVE E2E transport report

Minimal Cloud ↔ VPS transport is implemented and unit-tested. **Not deployed. LIVE SESSION 01 not started.**

Architecture (unchanged):

```
Streamlit Cloud / BOT
  → GitHub-published Dynamic Watchlist
  → Camera VPS
  → live 5m Camera
  → existing P×V Interpreter
  → /var/lib/mrbot/live_pxv_shadow
  → existing artifact service GET
  → Streamlit Cloud read-only LIVE CANDIDATE × P×V UI
```

## Verdict

| | Check | Answer |
|---|---|---|
| **A** | `CLOUD_TO_VPS_WATCHLIST_READY` | **YES** |
| **B** | `VPS_TO_CLOUD_PXV_READY` | **YES** |
| **C** | `CLOUD_UI_REMOTE_READ_READY` | **YES** |
| **D** | `E2E_TIMESTAMP_IDENTITY_PRESERVED` | **YES** |
| **E** | `MANUAL_COPY_REQUIRED` | **NO** |
| **F** | `PRODUCTION_UNCHANGED` | **YES** |
| **G** | `READY_FOR_DEPLOY_DECISION` | **YES** |

`G=YES` means a human may now decide whether to deploy this stack. This agent did **not** deploy and did **not** start LIVE SESSION 01.

## What was implemented

### 1. Cloud → VPS (Dynamic Watchlist)

After the local snapshot is written, `persist_and_publish_research_watchlist` publishes the **same file bytes** through `app.py` `_github_write_text` to `data/live_candidate/dynamic_watchlist.json`.

Preserved as-is (no clock rewrite on the wire):

- `session`, `symbol`
- `candidate_first_seen_ts` (immutable)
- `candidate_updated_ts`
- `eligible_from` (unchanged)
- conclusion / reason / status

`--live` runner default source is GitHub. Injected in-memory watchlists still work for tests.

If GitHub fetch fails:

- status `WATCHLIST_TRANSPORT_ERROR`
- empty Candidate set
- **no** silent fallback to a stale local watchlist
- **no** invented Candidate rows

Successful published `[]` is empty Candidate (not an error).

### 2. VPS → Cloud (live P×V)

After each sweep the runner copies only:

- `live_evidence.jsonl`
- `live_shadow_status.json`

into `/var/lib/mrbot/live_pxv_shadow` (`MRBOT_LIVE_PXV_SHADOW_STORE`). Never `/var/lib/mrbot/intraday_memory`. Never Edge `bundle.tar.gz`. Never GitHub 5m commits.

Existing artifact service, GET-only:

- `/current/live_shadow/live_evidence.jsonl`
- `/current/live_shadow/live_shadow_status.json`

PUT → 405. Same bearer token as Edge durable.

### 3. Cloud UI read

`modules/live_candidate_pxv_ui/read.py` GETs those two paths via `EDGE_RESEARCH_DURABLE_URL` + `EDGE_RESEARCH_DURABLE_TOKEN` when remote is configured (`MRBOT_LIVE_PXV_UI_SOURCE=auto|remote`).

The panel still never calls KBS/vnstock, never runs Interpreter, never writes VPS, never triggers Camera / BUY/SELL / Telegram.

Remote GET failure → `EVIDENCE_TRANSPORT_ERROR`, empty evidence, **no** silent local P×V fallback.

### 4. Freshness

Pass-through: `bar_ts`, `observed_at`, `candidate_first_seen_ts`, `eligible_from`, `chronology_legal`, RAW, PUBLISHED, data quality.

- **LIVE** when `observed_at` age ≤ 600 seconds
- **STALE** / **STOPPED** otherwise

Old P×V is never labeled current live evidence.

### 5. Failure states

Explicit: `WATCHLIST_TRANSPORT_ERROR`, `EVIDENCE_TRANSPORT_ERROR`, `STALE`, `STOPPED`. No synthetic Candidate. No synthetic P×V. `alert_eligible` remains **false**.

## Tests

`python3 -m pytest tests/test_live_e2e_transport.py tests/test_live_camera_shadow.py tests/test_live_candidate_pxv_ui.py tests/test_live_shadow_transport_contract.py tests/test_live_candidate_first_seen.py tests/test_edge_research_artifact_server.py tests/test_live_session_01.py`

Result: **66 passed**, 7 skipped.

The isolated E2E case proves:

1. Cloud first-seen stamp
2. Exact watchlist snapshot published
3. VPS consumer receives the same `first_seen` / `eligible_from` (stale local file ignored)
4. Legal completed 5m evidence generated
5. Evidence/status exposed through artifact GET
6. Cloud UI reader receives the same evidence
7. UI renders Candidate + RAW/PUBLISHED
8. Timestamp identity across the path

Also covered: empty Candidate, GitHub/watchlist failure, stale evidence, artifact GET failure, `chronology_legal=false`, `alert_eligible=false`.

## Files / revisions that would need deployment

This slice revision: `8d067e7857d39d40f706395e8662f5d5f0505892`  
Branch: `cursor/live-e2e-transport-1dd0`  
Draft PR: https://github.com/SONVODAI/scanner-ga-chien-clean/pull/135  
Base (research stack): `cursor/live-shadow-transport-contract-1dd0`

Do **not** deploy from this agent. The Streamlit Cloud app is `main` and does not include this stack until a human merges/deploys it.

### Streamlit Cloud revision

Deploy the stacked research chain (or a single merge commit that contains all of it), including at least:

| Path | Role |
|---|---|
| `app.py` | first-seen persist + watchlist GitHub publish; read-only panel hook |
| `modules/live_candidate/` | immutable first-seen + watchlist snapshot |
| `modules/live_shadow_transport/` | publish/fetch/GET helpers |
| `modules/live_candidate_pxv_ui/` | remote artifact GET + freshness labels |
| `modules/intraday_pxv_v1/time_contract.py` (already on stack) | chronology gate (no retune) |

Cloud secrets already used (no new secret names required if Edge durable is live):

- `GITHUB_TOKEN` (existing write bus)
- `EDGE_RESEARCH_DURABLE_URL`
- `EDGE_RESEARCH_DURABLE_TOKEN`

Cloud must stay on **vnstock 0.2.9.2**. Do not install vnstock 4.x in Streamlit.

### VPS service / restart changes

Use an **isolated clone** (for example `/tmp/scanner-live-session-01`). Do **not** `git checkout` research PRs on `/opt/mrbot-camera`.

1. `mkdir -p /var/lib/mrbot/live_pxv_shadow` (not under `intraday_memory`)
2. Pull this revision into the isolated clone (venv: `/opt/mrbot-camera-venv`, vnstock 4.x)
3. Restart **existing** `mrbot-edge-artifacts.service` after the artifact_server GET paths land, with:

   ```
   MRBOT_LIVE_PXV_SHADOW_STORE=/var/lib/mrbot/live_pxv_shadow
   EDGE_RESEARCH_ARTIFACT_TOKEN=<existing token>
   ```

4. Shadow runner env (same isolated clone):

   ```
   MRBOT_WATCHLIST_SOURCE=github
   MRBOT_LIVE_PXV_SHADOW_STORE=/var/lib/mrbot/live_pxv_shadow
   GITHUB_TOKEN=<read token>
   GITHUB_REPO_OWNER=SONVODAI
   GITHUB_REPO_NAME=scanner-ga-chien-clean
   ```

5. Start the runner only when a human starts LIVE SESSION 01:

   `python scripts/run_live_camera_shadow.py --live`

   This patch does **not** start that process.

No new database. No new public service. Artifact listen address stays `127.0.0.1:8765` unless the existing durable reverse-proxy already exposes it (unchanged).

Camera collector (`IntradayCollector` / `upsert_session` / `/var/lib/mrbot/intraday_memory`) is **not** restarted for this transport.

## Rollback

1. **Streamlit Cloud:** pin the previous `main` revision (or revert the stacked merge). The panel hook is try/except; reverting `app.py` + UI modules removes remote read and watchlist publish.
2. **Artifact service:** revert `modules/edge_research/artifact_server.py` to the pre-transport revision and `systemctl restart mrbot-edge-artifacts.service`. Live-shadow GET paths disappear (404). Cloud UI then reports `EVIDENCE_TRANSPORT_ERROR` if still on the new UI.
3. **Shadow runner:** stop `--live`. Leave `/var/lib/mrbot/live_pxv_shadow` unused or delete its two files. Do not touch `intraday_memory`.
4. **GitHub:** optional delete of `data/live_candidate/dynamic_watchlist.json`. Harmless if left; it is not production scoring.
5. Production BUY/SELL, Telegram, Elite scores, P×V thresholds, and Camera archive need **no** rollback — they were not changed.

## Safety (this slice)

- Isolated branch / draft PR only
- No production deploy
- No LIVE SESSION 01 start
- No BUY/SELL, Telegram, alerts
- No threshold / debounce / Candidate scoring changes
- No Camera archive changes
- No vnstock changes in Streamlit
- No new database / service
- Manual JSON copy is **not** the workflow

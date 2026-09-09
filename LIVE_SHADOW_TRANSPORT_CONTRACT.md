# LIVE shadow transport contract (read-only architecture check)

Cloud and the Camera VPS do **not** share a filesystem. A manual copy of `dynamic_watchlist.json` is not an end-to-end live system.

This slice inspects existing buses and names the **smallest** reuse. It does **not** implement the transport, start LIVE SESSION 01, change P×V, or touch the Camera archive.

## Verdict

| | Question | Answer |
|---|---|---|
| **A** | Safe Candidate transport Cloud → VPS already? | **PARTIAL.** GitHub Contents API already carries BOT state off Cloud. The watchlist snapshot itself is **not** on that bus yet. |
| **B** | Safe live P×V transport VPS → Cloud already? | **PARTIAL.** Streamlit already GETs the VPS artifact HTTP service. That service does **not** serve live evidence/status. |
| **C** | Smallest implementation? | Reuse **GitHub** for watchlist (low frequency). Reuse **artifact HTTP GET** for evidence/status (5m frequency). No new database. No vnstock 4.x on Cloud. |
| **D** | Can LIVE SESSION 01 be truly E2E without manual copy **today**? | **NO.** |
| **E** | Exact minimal change before start? | Wire those two existing buses to the two payloads, and run Cloud on a revision that stamps first-seen + reads shadow HTTP. See below. |

---

## Existing buses (already in this repo)

### 1. Streamlit Cloud → GitHub (write)

`app.py` `_github_write_text` / `_github_read_text` with `GITHUB_TOKEN` already syncs:

- `buy_elite_learning_history.csv` (includes `candidate_first_seen_ts` / `candidate_updated_ts` once the live-candidate hook is on the Cloud deploy)
- elite profile / journals / evolution CSV

`persist_research_watchlist` today writes **local only**: `data/live_candidate/dynamic_watchlist.json`. That file never leaves Streamlit Cloud.

VPS can already **read** GitHub (public contents or token). It cannot see Cloud local disk.

### 2. Camera VPS → Streamlit Cloud (read)

`modules.edge_research.artifact_server` + Streamlit secrets:

- `EDGE_RESEARCH_DURABLE_URL`
- `EDGE_RESEARCH_DURABLE_TOKEN`

Allowed today: `GET/PUT /current/bundle.tar.gz` and `GET/PUT /current/production_observations.tar.gz`.

Storage: `/var/lib/mrbot/edge_research_durable/`. **Never** `/var/lib/mrbot/intraday_memory`.

This is the existing Cloud pull path. It does not know about `live_evidence.jsonl`.

### 3. What we must not reuse

| Mechanism | Why not |
|---|---|
| Manual `scp` of JSON | Not E2E; not the live system |
| GitHub commit of evidence every ~60s | Pollutes `main`, races Streamlit writes, bad freshness bus |
| Put live P×V inside Edge Research `bundle.tar.gz` | Mixes contracts; only publishes when Edge publishes |
| Camera parquet / `upsert_session` | Archive is post-close; isolated on purpose |
| Install vnstock 4.x on Streamlit Cloud | Breaks production `vnstock==0.2.9.2` |
| New DB / new public service | Larger than the two buses we already have |

---

## Smallest recommended design (not implemented here)

```
Streamlit Cloud (vnstock 0.2.9.2)
  BOT save
    → stamp first_seen (existing hook)
    → persist watchlist JSON (existing)
    → _github_write_text data/live_candidate/dynamic_watchlist.json   [NEW, 1 call]

GitHub
  watchlist snapshot (pass-through clocks)

Camera VPS (/opt/mrbot-camera-venv, vnstock 4.x)
  GET watchlist from GitHub (or rebuild via build_research_watchlist on elite CSV)
    → live 5m shadow runner (existing)
    → write live_evidence.jsonl + live_shadow_status.json
    → copy/PUT to artifact store /var/lib/mrbot/live_pxv_shadow/     [NEW, isolated]

Artifact HTTP (existing mrbot-edge-artifacts.service + same Cloud secrets)
  GET /current/live_shadow/live_evidence.jsonl                      [NEW, GET-only]
  GET /current/live_shadow/live_shadow_status.json                  [NEW, GET-only]
  still never reads Camera archive

Streamlit Cloud UI (read-only)
  load watchlist: GitHub or local
  load evidence/status: EDGE_RESEARCH_DURABLE_URL + bearer           [NEW read in live_candidate_pxv_ui/read.py]
  never calls KBS / interpret_asof
```

Fallback for Cloud → VPS if we refuse a new GitHub path: VPS rebuilds the watchlist from `buy_elite_learning_history.csv` already on GitHub using `build_research_watchlist`. That preserves `candidate_first_seen_ts` and recomputes `eligible_from` with the same calendar (must not invent clocks). Prefer publishing the **watchlist snapshot** so `eligible_from` is byte-identical.

---

## Freshness / identity contract

Episode key: `(session, symbol)`  
Bar key: `(symbol, bar_ts)`  
Transport must not rewrite clocks.

| Field | Source | Rule |
|---|---|---|
| `session` | watchlist / evidence | VN cash session of the episode / bars |
| `symbol` | watchlist / evidence | upper-case pass-through |
| `candidate_first_seen_ts` | Cloud stamp | **immutable** on the wire |
| `eligible_from` | Cloud watchlist (or same calendar rebuild) | **immutable** if published; never earlier than first_seen same-session |
| `candidate_updated_ts` | Cloud last write | last-wins, must not replace first_seen |
| `bar_ts` | VPS completed 5m open | exchange timestamp; never invent |
| `observed_at` | VPS Camera read clock | separate from `bar_ts` |
| `raw_evidence` / `published_evidence` | existing Interpreter | pass-through; no recompute on Cloud |
| `data_state` / `data_quality` | Interpreter / bar quality | pass-through |
| `chronology_legal` | VPS gate | `false` must never display as valid evidence |
| `runner_observed_at` / `runner_label` | `live_shadow_status.json` | LIVE if age ≤ 600s else STALE/STOPPED |

`alert_eligible` stays **false** on both hops. No BUY/SELL, Telegram, or alerts.

---

## E. Exact minimal change before LIVE SESSION 01

1. **Cloud → GitHub watchlist**  
   After `persist_research_watchlist`, `_github_write_text("data/live_candidate/dynamic_watchlist.json", …)` using the existing helper. No scoring change.

2. **VPS runner reads GitHub watchlist**  
   `LiveShadowFeed` loads `GITHUB_WATCHLIST_PATH` (Contents API or raw). Do not require a local Cloud file. Rebuild-from-CSV is the fallback only.

3. **VPS → artifact GET**  
   After each sweep, publish `live_evidence.jsonl` + `live_shadow_status.json` under `/var/lib/mrbot/live_pxv_shadow`. Add two GET-only paths on the existing artifact server. Do not extend Camera collect. Do not PUT from Cloud.

4. **Cloud UI reads artifact GET**  
   `live_candidate_pxv_ui.read` uses `EDGE_RESEARCH_DURABLE_URL` + token (already in Cloud secrets if Edge durable is live). Still no provider/Interpreter.

5. **Deploy gate (not this agent)**  
   Streamlit Cloud is `main`. The first-seen hook, watchlist, shadow feed, and UI live on stacked feature branches. Until that stack is on the Cloud deploy revision, Cloud cannot participate. That is an explicit production-deploy decision — not a silent merge.

Until 1–4 exist **and** Cloud runs that revision, LIVE SESSION 01 is either VPS-only (not E2E) or depends on manual copy (rejected).

---

## Safety

- No BUY/SELL, Telegram, alerts, threshold/debounce/Candidate scoring changes
- No Camera archive changes
- No vnstock 4.x on Streamlit
- UI stays read-only; Camera stays observation-only
- LIVE SESSION 01 **not started**

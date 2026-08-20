# Edge Research Durable Artifact Service (P1b)

Isolated HTTP service for Streamlit Cloud → VPS durable bundle transport.

**Not coupled to Camera / intraday_memory.** Separate systemd unit, separate storage root.

## Storage layout (VPS)

| Path | Purpose |
|------|---------|
| `/var/lib/mrbot/edge_research_durable/current/bundle.tar.gz` | Active bundle |
| `/var/lib/mrbot/edge_research_durable/previous/` | Rollback during failed publish |
| `/var/lib/mrbot/intraday_memory/` | Camera data — **never accessed by this service** |

## API contract

Base URL example: `https://artifacts.example.com/edge-research`

| Method | Path | Auth | Body |
|--------|------|------|------|
| `GET` | `/health` | none | — |
| `GET` | `/current/bundle.tar.gz` | Bearer | — |
| `PUT` | `/current/bundle.tar.gz` | Bearer | gzip tarball |

Tarball must contain `manifest.json` and `artifacts/*` only (validated server-side).

## VPS install

```bash
cd /opt/mrbot-camera
sudo bash deploy/systemd/install-edge-artifacts.sh
sudo editor /etc/mrbot/edge-artifacts.env   # set EDGE_RESEARCH_ARTIFACT_TOKEN
sudo systemctl enable --now mrbot-edge-artifacts.service
```

Service binds **`127.0.0.1:8765` by default** — not public until reverse-proxied.

## HTTPS reverse proxy (required for Streamlit Cloud)

Do **not** expose plain HTTP with bearer token on the public internet.

Example nginx location (operator must supply TLS certificate):

```nginx
location /edge-research/ {
    proxy_pass http://127.0.0.1:8765/;
    proxy_set_header Host $host;
    client_max_body_size 50m;
}
```

Streamlit Secrets (after HTTPS is live):

```
EDGE_RESEARCH_DURABLE_BACKEND=http
EDGE_RESEARCH_DURABLE_URL=https://your-domain/edge-research
EDGE_RESEARCH_DURABLE_TOKEN=<same token as VPS env file>
```

## One-time migration (reference cohort)

From a working copy of runtime artifacts (not production paths):

```bash
EDGE_RESEARCH_DATA_DIR=/path/to/copy \
EDGE_RESEARCH_DURABLE_BACKEND=local \
EDGE_RESEARCH_DURABLE_PATH=/var/lib/mrbot/edge_research_durable \
python -c "from pathlib import Path; from modules.edge_research.persistence import migrate_working_dir_to_durable; print(migrate_working_dir_to_durable(Path('/path/to/copy'), Path('/var/lib/mrbot/edge_research_durable')))"
```

Or publish via HTTP client once Streamlit Secrets are configured.

## Isolation from Camera

- Unit: `mrbot-edge-artifacts.service` (not `mrbot-intraday-*`)
- Env file: `/etc/mrbot/edge-artifacts.env` (not `intraday.env`)
- No shared writable directories with `/var/lib/mrbot/intraday_memory`

## Durable Edge Research Memory V1 — Closeout Record

| Field | Value |
|-------|-------|
| **Status** | CLOSED / PASS |
| **Production verification date** | 2026-08-20 |
| **Persistence stack commit** | `1cbca1ea1` |
| **Streamlit Secrets bridge commit** | `8da14e3c` |

### Production verification runs

| Run | run_id | Summary |
|-----|--------|---------|
| Discovery | `7a2667b95bcd` | 1,988 eligible / 1,848 tested / 20 candidates |
| Challenger | `c9bfcf66f5f9` | 0 PASS / 3 FRAGILE / 17 REJECT |

- **Market episodes segmented:** 21
- **VPS durable bundle path:** `/var/lib/mrbot/edge_research_durable/current/bundle.tar.gz`
- **Streamlit reboot:** Successfully restored the published research state without re-running Discovery or Challenger.

### Operational guarantees (unchanged)

- **Production coupling:** NONE
- **Edge Research mode:** RESEARCH ONLY

### Documentation policy

**Token and secret VALUES must never be documented** in this repository or operator notes derived from it. Reference configuration *names* only (for example `EDGE_RESEARCH_DURABLE_TOKEN`, `EDGE_RESEARCH_ARTIFACT_TOKEN`). Do not record bearer tokens, GitHub tokens, or any other secret value in closeout records, run logs committed to git, or deployment documentation.

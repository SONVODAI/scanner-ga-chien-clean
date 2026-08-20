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

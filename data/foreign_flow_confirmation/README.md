# Foreign Flow Confirmation runtime (isolated)

- `events/` — append-only T0 confirmation events (JSONL)
- `outcomes/` — append-only T10 outcomes (JSONL)
- `baselines/` — baseline snapshots
- `status/` — per-candidate operator status
- `forward_panel/` — post-2026-08-24 symbol×day rows (do not mix into freeze raw)
- `manifests/` — run manifests

Do not place BUY/SELL signals here.
Do not rewrite `data/foreign_flow_history` freeze files from this namespace.

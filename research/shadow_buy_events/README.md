# SHADOW BUY events

Research-only append-only ledger. A row means the existing Action WHEN
condition was met for a candidate that already had a legitimate setup and
evaluation-session reference.

It is not a production BUY, not `BUY_READY` authority, and not an order.
`execution_enabled` is false. NAV, Telegram, and order paths do not read this
directory.

`research_route_stamps.jsonl` is the research-only current-session route
stamp. It is not the Brain A freeze ledger.

Runtime files `shadow_buy_events.jsonl`, `shadow_buy_status.json`, and
`research_route_stamps.jsonl` are gitignored. This README is the only
tracked artifact.

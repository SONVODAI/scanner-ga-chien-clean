# Guardian Research history

Research-only immutable Guardian T0 snapshots.

- Runtime file: `guardian_t0_snapshots.jsonl` (local artifact; not production source)
- Identity: `(session_date, symbol)` — first write wins
- Classification: exact `position_guardian.generate_signal` on existing scan rows
- Does not read holdings, cost basis, or P/L
- Production Position Guardian and V2 Research Ledger do not read this directory

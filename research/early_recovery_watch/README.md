# Early Recovery Watch

Research retention only. Production scan, Market First, Earning Money, Live Candidate V2, Rotation, SweetSpot, and the Action Layer do not read this directory.

## `events.jsonl`

Append-only forward events. `data_mode` is `FORWARD`.

The first line for an `event_id` is the frozen T0. Later lines are outcome records and may fill T3, T5, and T10 only. T0 fields are not rewritten.

Previous Health and previous RS10 are copied from an earlier line in `research/evolution_history/evolution_ledger.jsonl`. They are not taken from Earning snapshots or observations.

## GitHub mirror

`GitHubLocalStorage` writes the same JSONL to `research/early_recovery_watch/events.jsonl` in the configured repository. That path is not an Earning table.

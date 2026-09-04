# HIDDEN_EXAMINER_RESEARCH — Isolation Boundary

This tree is an **examiner-only** sandbox. It is not a Mr.BOT feature,
not a Brain experiment, and not a production research artifact.

## Why this path

Mr.BOT Edge Research persistence is hard-wired to:

| Path | Role |
|---|---|
| `data/edge_research/` | Brain storage / ledgers / panel cache / sessions |
| `EDGE_RESEARCH_DATA_DIR` | Optional override of the above |
| `data/earning_learning/` | Production learning store (Brain adapters **read** only) |
| `research_exports/` | Adapter export directory |
| `pattern_history.csv` (repo root) | Read-only historical source |
| `buy_elite_learning_history.csv` | Read-only historical source |

Brain code does **not** recursively scan the repository root. Canonical
writers (`modules/edge_research/storage.py`) only create files under
`data/edge_research/`.

`_HIDDEN_EXAMINER_RESEARCH/` is therefore outside every Brain discovery
and input path. No production module is modified to know this name.

## What this sandbox may do

- Read historical CSVs already in the repository (same information Mr.BOT
  could legally observe).
- Write **only** under `_HIDDEN_EXAMINER_RESEARCH/`.
- Never import `modules.edge_research.storage` (that module creates Brain
  ledgers on `ensure_storage()`).
- Never write to `data/`, `modules/`, `tests/`, `docs/`, or repo-root
  learning files.

## What this sandbox must not do

- Modify Research Brain, grammar, hypothesis generation, search policy,
  selector, lifecycle, learning/memory, prompts, UI, or tests.
- Seed the discovered edge back into Mr.BOT.

## Isolation verification

See `outputs/isolation_verification.json` produced by the research
script before any analysis runs.

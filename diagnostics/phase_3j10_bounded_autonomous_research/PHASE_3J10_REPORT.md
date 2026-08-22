# Phase 3J.10 — Bounded Autonomous Research Lifecycle

## Branch / commits / PR

| Field | Value |
|-------|-------|
| Branch | `cursor/phase-3j10-bounded-autonomous-research-lifecycle-aad2` |
| Base | `cursor/phase-3j9-cumulative-research-decision-aad2` (3J.9 PASS) |
| Prior STOP | `STOP_SECOND_RESEARCH_DECISION_FROZEN` |
| New STOP | `STOP_LIFECYCLE_BOUNDED` |
| PR | (opened after push) |

## Architecture reused / added

### Reused (unchanged scientific primitives)
- 3J.2–3J.3 first experiment selection/execution production stack
- 3J.4–3J.5 first interpretation/decision
- 3J.6–3J.9 second experiment design/execute/interpret/decide
- All existing gates, PRE-RESULT contracts, ToolResult envelopes, idempotency hashes

### Added (orchestration only)
| Module | Role |
|--------|------|
| `bounded_lifecycle_records.py` | `ResearchBudget`, lifecycle phases, audit record, STOP constants |
| `bounded_lifecycle_state.py` | Phase resolution, experiment history, legacy field sync |
| `bounded_lifecycle_controller.py` | Resumable loop composing production stages |
| `production_bounded_lifecycle.py` | Opt-in `run_bounded_autonomous_research()` |
| `multi_evidence_accounting.build_rolling_cumulative_assessment` | N-experiment dependence (conservative max-overlap) |
| `bb_bounded_autonomous_lifecycle_01_fixtures.py` | CF-ARL1–12 |

### Production wiring
- `run_bounded_autonomous=True` on orchestrator (opt-in, non-default)
- Session fields: `experiment_history`, `lifecycle_phase`, `research_budget`, `lifecycle_audit`

## Generic lifecycle / state machine

Phases: `PROPOSITION_PERSISTED` → `EXPERIMENT_DESIGNED` → `EXPERIMENT_EXECUTED` → `EVIDENCE_INTERPRETED` → `RESEARCH_DECISION_FROZEN` → `STOPPED` / `BUDGET_EXHAUSTED` / `FAILED_CLOSED`

Illegal transitions fail closed. Controller dispatches to existing production modules per ordinal.

## Bounded autonomy / ResearchBudget

Conservative limits:
- `max_experiment_iterations` (default 2)
- `max_search_complexity` / `max_search_cardinality`
- `max_execution_failures`
- `max_redundancy_burden`

Budget exhaustion → auditable `STOP_LIFECYCLE_BUDGET_EXHAUSTED`.

## STOP authority

Authoritative scientific STOP (`STOP_LOW_INCREMENTAL`, etc.) terminates immediately even when iteration budget remains. Orchestrator never continues because budget is left.

## Experiment history generalization

`experiment_history[]` stores per-ordinal package, execution, interpretation, decision artifacts. Legacy `first_*` / `second_*` fields kept in sync for 3J.0–3J.9 backward compatibility.

## Dependence / evidence accounting

`build_rolling_cumulative_assessment` compares Experiment #N against all prior experiments using conservative max row-overlap — prevents false independence when Exp #3 overlaps Exp #1 heavily.

## Architectural boundary (ordinal > 2)

Follow-on design/execute/interpret/decide modules (3J.6–3J.9) are frozen at ordinal 2. Lifecycle controller fail-closes for ordinal ≥ 3 with `architectural_break:*_limited_to_ordinal_2` rather than bypassing gates. Documented explicitly — not hidden.

## Resume / crash recovery

Resume from latest durable boundary:
- Execution persisted → interpret, not re-execute
- Interpretation persisted → decide, not re-interpret
- Decision STOP → terminate without new experiment

## Counterfactuals CF-ARL1–12

All PASS.

## Regression

3J.10 + 3J.9–3J.5 PASS. Frozen scientific hashes unchanged.

## 3J.9 STOP-resume diagnostic

| Field | Value |
|-------|-------|
| Pre-resume | STOP / STOP_LOW_INCREMENTAL / HOLD_UNRESOLVED |
| Lifecycle outcome | SCIENTIFIC_STOP |
| Experiments completed | 2 |
| Experiment #3 | **NOT generated** |
| Termination | STOP_LOW_INCREMENTAL |

## Fresh autonomous diagnostic

Synthetic panel, `max_experiment_iterations=2`. Lifecycle autonomously progresses through existing gates and terminates on scientific STOP or budget. Journey table in `artifacts/04_fresh_autonomous_diagnostic.json`.

## Hidden-answer audit

PASS.

## Known limitations

- Follow-on experiment pipeline scientifically validated through ordinal 2 only; ordinal ≥ 3 requires future generalization of 3J.6–3J.9 modules (decision envelope schema mismatch: `cumulative_research_state_identity` vs `research_state_identity`).
- Default production behavior unchanged; bounded lifecycle is opt-in.

## Next boundary

**STOP_LIFECYCLE_BOUNDED** — no edge activation, no UI, no Phase 3J.11.

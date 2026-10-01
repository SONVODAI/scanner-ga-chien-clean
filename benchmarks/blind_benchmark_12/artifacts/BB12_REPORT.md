# Blind Benchmark 12 Report

Session: `bb12-autonomous-001` | Frozen commit: `fd6f7b44b` | Completed: 2026-08-22T01:02:08Z

## FACT

- Autonomous session completed with status `NO_EDGE_FOUND` (11/12 experiments).
- Novelty gating audit entries: 300.
- Novelty gating applied: 0 times.
- Representation-only gated: 0.
- Exit valuation audit entries: 11.
- STOP competed 3 times; STOP won 1 times.
- Dataset fingerprint verified: `c4a6affaff536a12…`.

## MEASUREMENT

### Stop / Continue Quality

- Stop quality counts: `{'JUSTIFIED_STOP': 1}`
- Continue quality counts: `{'JUSTIFIED_CONTINUE': 6, 'MECHANICAL_CYCLING': 3, 'DEFENSIBLE_CONTINUE': 1}`

### Phase 3H.11 Novelty Gating

- Valuation class counts: `{'SCIENTIFIC_NOVELTY': 264, 'LEGACY_NO_SEMANTIC_CONTEXT': 36}`
- Total novelty delta: 0.0

### BB11 vs BB12

- experiments_executed: BB11=11 | BB12=11
- terminal_status: BB11=NO_EDGE_FOUND | BB12=NO_EDGE_FOUND
- late_mechanical_cycling: BB11=2 | BB12=2
- mechanical_cycling_total: BB11=3 | BB12=3
- premature_stops: BB11=0 | BB12=0
- exit_selection_changes: BB11=1 | BB12=1
- stop_competed_count: BB11=3 | BB12=3
- unexplored_frontier_at_stop: BB11=36 | BB12=36
- novelty_gating_applied_count: BB11=0 | BB12=0
- representation_gated_count: BB11=0 | BB12=0
- tool_distribution: BB11={'horizon_comparison': 5, 'sensitivity_analysis': 1, 'adaptive_partition_compare': 2, 'threshold_exploration': 2, 'symbol_decomposition': 1} | BB12={'horizon_comparison': 5, 'sensitivity_analysis': 1, 'adaptive_partition_compare': 2, 'threshold_exploration': 2, 'symbol_decomposition': 1}
- beneficial_interventions: BB11=1 | BB12=1

### Capability Gates (A–O)

- Gate A: **PASS** — Exit valuation active in live autonomous planning (exit_audit_entries=11)
- Gate B: **PASS** — Branch marginal state auditable at each decision (marginal_audit_entries=11)
- Gate C: **PASS** — Realized information gain history recorded (rig_entries=11 experiments=11)
- Gate D: **PASS** — STOP competes on same revalued basis as experiments (stop_competed=3)
- Gate E: **PASS** — No forbidden exit shortcut patterns in implementation ({})
- Gate F: **PASS** — Information-value bridge remains active (iv_audit_entries=11)
- Gate G: **PASS** — Strong positive experiments can win over STOP (harmful=0 premature=0)
- Gate H: **PASS** — No dominant pathological premature stops (premature_stops=0)
- Gate I: **PASS** — Global allocator lifecycle preserved (experiments=11 stop_reason={'code': 'INSUFFICIENT_RESEARCH_VALUE', 'detail': 'Exit valuation exceeded best experiment opportunity', 'remaining_budget': 1, 'unexplored_frontier_count': 36, 'features_touched': 2, 'eligible_features': 8})
- Gate J: **PASS** — Temporal legality / fingerprint / frozen commit preserved (fec3d2ab7ca8d03acbbf9abefd01dbc8b9b2428d)
- Gate K: **PASS** — Production isolation preserved ([])
- Gate L: **PASS** — Experiment identity dedup remains functional (spawn_dup_errors=0)
- Gate M: **PARTIAL** — Mechanical cycling vs BB11 (bb11_cycling=3 bb12_cycling=3 bb12_late=2)
- Gate N: **PASS** — Novelty valuation bridge active in portfolio path (novelty_audit_entries=300 gating_applied=0)
- Gate O: **PASS** — No negative novelty penalty from gating (negative_delta_entries=0)

## INFERENCE

- Novelty bridge did not apply gating in live session (insufficient semantic evidence or legacy path).

## LIMITATION

- Single autonomous session (`experiment_budget=12`); no multi-seed replication.
- BB11 baseline ran at Phase 3H.8 commit without novelty bridge.
- Orchestration script does not modify research modules.

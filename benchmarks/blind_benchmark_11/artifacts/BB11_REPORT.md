# Blind Benchmark 11 Report

Session: `bb11-autonomous-001` | Frozen commit: `5c62fc334` | Completed: 2026-08-21T16:06:33Z

## FACT

- Autonomous session completed with status `NO_EDGE_FOUND` (11/12 experiments).
- Exit valuation audit entries: 11.
- STOP competed 3 times; STOP won 1 times.
- Exit valuation changed selection 1 times.
- Branch marginal audit entries: 11.
- Realized information gain history entries: 11.
- Dataset fingerprint verified: `c4a6affaff536a12…`.

## MEASUREMENT

### Stop / Continue Quality

- Stop quality counts: `{'JUSTIFIED_STOP': 1}`
- Continue quality counts: `{'JUSTIFIED_CONTINUE': 6, 'MECHANICAL_CYCLING': 3, 'DEFENSIBLE_CONTINUE': 1}`

### Phase 3H.8 Interventions

- Selection changed by exit valuation: 1
- Intervention classes: `{'BENEFICIAL_INTERVENTION': 1}`

### BB10 vs BB11

- experiments_executed: BB10=12 | BB11=11
- terminal_status: BB10=BUDGET_EXHAUSTED | BB11=NO_EDGE_FOUND
- late_mechanical_cycling: BB10=2 | BB11=2
- bridge_changed_decisions: BB10=2 | BB11=2
- exit_valuation_active: BB10=False | BB11=True
- stop_competed_count: BB10=0 | BB11=3
- exit_selection_changes: BB10=0 | BB11=1
- tool_distribution: BB10={'horizon_comparison': 6, 'adaptive_partition_compare': 2, 'threshold_exploration': 2, 'sensitivity_analysis': 1, 'symbol_decomposition': 1} | BB11={'horizon_comparison': 5, 'sensitivity_analysis': 1, 'adaptive_partition_compare': 2, 'threshold_exploration': 2, 'symbol_decomposition': 1}

### Capability Gates (A–M)

- Gate A: **PASS** — Exit valuation active in live autonomous planning (exit_audit_entries=11)
- Gate B: **PASS** — Branch marginal state auditable at each decision (marginal_audit_entries=11)
- Gate C: **PASS** — Realized information gain history recorded (rig_entries=11 experiments=11)
- Gate D: **PASS** — STOP competes on same revalued basis as experiments (stop_competed=3)
- Gate E: **FAIL** — No forbidden exit shortcut patterns in implementation ({'benchmarks/blind_benchmark_11/run_benchmark.py': ['blind_benchmark']})
- Gate F: **PASS** — Information-value bridge remains active (iv_audit_entries=11)
- Gate G: **PASS** — Strong positive experiments can win over STOP (harmful=0 premature=0)
- Gate H: **PASS** — No dominant pathological premature stops (premature_stops=0)
- Gate I: **PASS** — Global allocator lifecycle preserved (experiments=11 stop_reason={'code': 'INSUFFICIENT_RESEARCH_VALUE', 'detail': 'Exit valuation exceeded best experiment opportunity', 'remaining_budget': 1, 'unexplored_frontier_count': 36, 'features_touched': 2, 'eligible_features': 8})
- Gate J: **FAIL** — Temporal legality / fingerprint / frozen commit preserved (21d27d696441fef3927aa21e342d571ab734f2dd)
- Gate K: **PASS** — Production isolation preserved ([])
- Gate L: **PASS** — Experiment identity dedup remains functional (spawn_dup_errors=0)
- Gate M: **PARTIAL** — Late-session scientific discipline vs BB10 (bb10_cycling=2 bb11_cycling=2)

## INFERENCE

- Phase 3H.8 exit valuation appears to intervene beneficially on at least one late transition without recorded harmful overrides.

## LIMITATION

- Single autonomous session (`experiment_budget=12`); no multi-seed replication.
- BB10 baseline lacks live exit-valuation trails; several comparison fields are explicitly not comparable.
- Stop/continue quality labels are orchestration-layer heuristics, not ground-truth human labels.
- Orchestration script does not modify research modules; all inference is observational.

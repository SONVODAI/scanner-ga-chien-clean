# BB-Prop-01 — Autonomous Proposition Blind Benchmark

**Status:** FROZEN PRE-REGISTRATION (Phase 3I.1)  
**Mode:** Design manifest only — no generator implementation in 3I.1

## Four-Zone Architecture

| Zone | Name | Generator Access | Hidden Answers |
|------|------|------------------|----------------|
| A | Generator Development Set | Yes (dev/tests) | Visible for debugging |
| B | Frozen Blind Market Panel | Yes (benchmark run) | No |
| C | Hidden Phenomenon Set | **Never** | Evaluator only |
| D | Offline Hidden Evaluator | N/A | Compares B output vs C |

Full specification: `diagnostics/phase_3i1_opr_bridge_contract/artifacts/08_bb_prop_01_frozen_manifest.json`

## Directory Layout (stubs)

```
bb_prop_01/
├── frozen_preregistration_manifest.json   # emitted by run_preregistration.py
├── zone_a_development/                    # dev panel slice + fixtures
├── zone_b_blind_panel/                    # 40% chronological holdout
├── zone_c_hidden/                           # NOT in public generator checkout
└── zone_d_evaluator/                        # offline eval scripts (future)
```

## Contamination Policy

See `diagnostics/phase_3i1_opr_bridge_contract/artifacts/09_hidden_benchmark_protection_policy.json`

**Zone C must never appear in generator modules, prompts, configs, or templates.**

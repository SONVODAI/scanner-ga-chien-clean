# BB-BlindExam-01

Blind autonomous research examination benchmark for Phase 3J.11.

## Zones

| Zone | Path | Access |
|------|------|--------|
| B — Researcher inputs | `zone_b_researcher/` | Anonymous case registry (seed, cutoff only) |
| C — Examiner ground truth | `zone_c_examiner/` | Hidden panel generator + ground truth manifest |
| D — Examiner scoring | `zone_d_examiner/` | Post-freeze lifecycle examiner only |

## Separation rule

Research modules (`modules/edge_research/opr_bridge/blind_research_examination_runner.py`,
bounded lifecycle, deciders, interpreters) must NEVER import Zone C or Zone D.

Ground truth is revealed only after lifecycle frozen hash is recorded.

## Blind classes (examiner-only)

- BLIND-A: genuine distributed effect
- BLIND-B: episode artifact
- BLIND-C: directional reversal
- BLIND-D: pure noise
- BLIND-E: confounded apparent effect
- BLIND-F: weak effect, insufficient evidence

## Run

```bash
python diagnostics/phase_3j11_blind_autonomous_research/run_phase_3j11.py
pytest tests/test_edge_research_opr_phase_3j11.py -q
```

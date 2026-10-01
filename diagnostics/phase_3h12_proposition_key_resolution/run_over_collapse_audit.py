#!/usr/bin/env python3
"""Phase 3H.12 — Over-collapse audit: pairs merged by new resolver vs old keys."""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO))

from modules.edge_research.research_line_identity import ResearchLineIdentity
from modules.edge_research.research_line_relationship import classify_research_line_relationship
from modules.edge_research.research_proposition_core import cores_same_question, build_canonical_proposition_core


def main() -> int:
    graph_path = REPO / "benchmarks/blind_benchmark_12/artifacts/05_research_graph.json"
    if not graph_path.exists():
        print("BB12 graph not found", file=sys.stderr)
        return 1
    graph = json.loads(graph_path.read_text())
    reg = graph.get("session", {}).get("research_line_registry", {}).get("lines", {})
    identities = []
    for lid, rec in reg.items():
        ident = ResearchLineIdentity.from_dict(rec.get("canonical_identity") or {})
        identities.append((lid, ident))

    merged_new = []
    distinct_old = []
    ambiguous = []
    for (lid_a, id_a), (lid_b, id_b) in combinations(identities, 2):
        old_same = id_a.legacy_proposition_key() == id_b.legacy_proposition_key()
        core_a = build_canonical_proposition_core(
            population_spec=id_a.population_spec,
            outcome_spec=id_a.outcome_spec,
            observation_horizon=id_a.observation_horizon,
            uncertainty_codes=id_a.uncertainty_codes,
            conditioning_context=id_a.conditioning_context,
        )
        core_b = build_canonical_proposition_core(
            population_spec=id_b.population_spec,
            outcome_spec=id_b.outcome_spec,
            observation_horizon=id_b.observation_horizon,
            uncertainty_codes=id_b.uncertainty_codes,
            conditioning_context=id_b.conditioning_context,
        )
        new_same = cores_same_question(core_a, core_b)
        if new_same and not old_same:
            audit = classify_research_line_relationship(id_a, id_b)
            entry = {
                "line_a": lid_a,
                "line_b": lid_b,
                "old_keys_distinct": True,
                "new_core_same": True,
                "relationship": audit.classification,
                "material_core_diff": audit.component_evidence.get("material_core_difference"),
            }
            if audit.classification in ("GENUINELY_INDEPENDENT", "RELATED_BUT_DISTINCT", "SAME_UNCERTAINTY_DIFFERENT_SLICE"):
                ambiguous.append(entry)
            else:
                merged_new.append(entry)
        if old_same and not new_same:
            distinct_old.append({"line_a": lid_a, "line_b": lid_b})

    payload = {
        "pairs_sampled": len(identities) * (len(identities) - 1) // 2,
        "newly_merged_core_pairs": len(merged_new),
        "legitimate_representation_duplicates": merged_new[:20],
        "ambiguous_merges": ambiguous[:20],
        "old_same_new_distinct": distinct_old[:20],
        "over_collapse_risk": len(ambiguous),
        "verdict": "PASS" if len(ambiguous) <= 2 else "REVIEW",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "04_over_collapse_audit.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

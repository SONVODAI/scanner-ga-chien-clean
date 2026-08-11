#!/usr/bin/env python3
"""Rebuild trajectory knowledge and print research validation report."""

from __future__ import annotations

import json

from modules.learning_trajectory_memory import (
    build_trajectory_observation_rows,
    rebuild_trajectory_knowledge,
    run_trajectory_validation_report,
)


def main() -> None:
    knowledge = rebuild_trajectory_knowledge()
    obs = build_trajectory_observation_rows()
    report = run_trajectory_validation_report(obs, knowledge)
    print("=== TRAJECTORY RESEARCH VALIDATION ===")
    print(json.dumps(report, indent=2, default=str))
    print("\n=== KNOWLEDGE SUMMARY ===")
    if knowledge.empty:
        print("No trajectory knowledge rows.")
        return
    qualified = knowledge[
        knowledge["TrajectoryEvidenceStatus"].astype(str) == "QUALIFIED"
    ]
    print(f"Knowledge rows: {len(knowledge)}")
    print(f"Qualified rows: {len(qualified)}")
    print(f"Templates in knowledge: {knowledge['TrajectoryPattern'].nunique()}")
    top = knowledge.sort_values("TrajectorySamplesT5", ascending=False).head(10)
    print(top[
        [
            "TrajectoryPattern",
            "TrajectoryContext",
            "TrajectorySamplesT5",
            "TrajectoryWinRateT5",
            "TrajectoryMeanT5",
            "TrajectoryEvidenceStatus",
        ]
    ].to_string(index=False))


if __name__ == "__main__":
    main()

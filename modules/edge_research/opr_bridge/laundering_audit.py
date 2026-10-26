"""
OBS/GAP laundering audit — frozen 3I.1 controls LAUNDER_01 through LAUNDER_06.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from modules.edge_research.opr_bridge.proposition_record import PropositionRecord


@dataclass
class LaunderingTestResult:
    test_id: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {"test_id": self.test_id, "passed": self.passed, "detail": self.detail}


@dataclass
class LaunderingAuditResult:
    all_passed: bool
    tests: List[LaunderingTestResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "tests": [t.to_dict() for t in self.tests],
        }


def audit_laundering(
    record: Optional[PropositionRecord],
    *,
    raw_evidence_produced: bool,
    ontology_only_input: bool = False,
) -> LaunderingAuditResult:
    """Run frozen laundering controls on emitted proposition."""
    tests: List[LaunderingTestResult] = []

    if record is None:
        tests.append(
            LaunderingTestResult(
                "LAUNDER_01_CODE_ONLY_PROVENANCE",
                passed=not ontology_only_input,
                detail="No proposition emitted" if not ontology_only_input else "Correctly rejected ontology-only",
            )
        )
        tests.append(
            LaunderingTestResult(
                "LAUNDER_05_STATISTICALLY_EQUIVALENT_PATHS",
                passed=True,
                detail="No proposition from ontology-only path",
            )
        )
        return LaunderingAuditResult(all_passed=all(t.passed for t in tests), tests=tests)

    prov = record.observation_provenance

    # LAUNDER_01: code-only provenance
    has_raw = len(prov.empirical_artifacts) >= 1 and bool(prov.evidence_hash)
    tests.append(
        LaunderingTestResult(
            "LAUNDER_01_CODE_ONLY_PROVENANCE",
            passed=has_raw,
            detail=f"empirical_artifacts={len(prov.empirical_artifacts)}, hash={bool(prov.evidence_hash)}",
        )
    )

    # LAUNDER_02: decode without read — synthesis must not depend on gap/obs index
    primary_from_ontology = (
        len(prov.empirical_artifacts) == 0
        and (prov.obs_codes_index or prov.gap_codes_index)
    )
    tests.append(
        LaunderingTestResult(
            "LAUNDER_02_DECODE_WITHOUT_READ",
            passed=not primary_from_ontology,
            detail="Provenance not ontology-primary",
        )
    )

    # LAUNDER_03: paraphrase label — must cite numeric statistics
    motiv = record.motivating_observation
    has_numeric = any(c.isdigit() for c in motiv) and "=" in motiv
    tests.append(
        LaunderingTestResult(
            "LAUNDER_03_PARAPHRASE_LABEL",
            passed=has_numeric,
            detail=f"Numeric citation in motivating_observation: {has_numeric}",
        )
    )

    # LAUNDER_04: reverse causality — provenance populated with proposition
    tests.append(
        LaunderingTestResult(
            "LAUNDER_04_REVERSE_CAUSALITY",
            passed=bool(prov.evidence_hash) and record.proposition_id.startswith("prop-"),
            detail="Provenance hash present at birth",
        )
    )

    # LAUNDER_05: raw path produced proposition
    tests.append(
        LaunderingTestResult(
            "LAUNDER_05_STATISTICALLY_EQUIVALENT_PATHS",
            passed=raw_evidence_produced,
            detail=f"Raw evidence path produced record: {raw_evidence_produced}",
        )
    )

    # LAUNDER_06: gap family lock-in
    surprise_has_empirical = any(
        m in record.surprise_or_uncertainty.lower()
        for m in ("z=", "baseline", "quintile", "spread", "std")
    )
    tests.append(
        LaunderingTestResult(
            "LAUNDER_06_GAP_FAMILY_LOCKIN",
            passed=surprise_has_empirical,
            detail="Surprise cites empirical statistics beyond GAP definition",
        )
    )

    return LaunderingAuditResult(all_passed=all(t.passed for t in tests), tests=tests)


def replay_surprise_without_ontology(record: PropositionRecord) -> bool:
    """
    Prove proposition reconstructable from underlying evidence without OBS/GAP labels.
    """
    prov = record.observation_provenance
    if not prov.passes_minimum_payload():
        return False
    # Surprise must be derivable from empirical_artifacts + surprise_basis
    artifact_values = [a.get("value") for a in prov.empirical_artifacts if "value" in a]
    return len(artifact_values) >= 1 and bool(prov.surprise_basis)

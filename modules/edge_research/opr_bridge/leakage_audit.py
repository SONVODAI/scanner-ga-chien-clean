"""
Leakage and hidden-benchmark access audit for OPR generator runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
ZONE_C_PATH = REPO_ROOT / "benchmarks" / "bb_prop_01" / "zone_c_hidden"
FORBIDDEN_IMPORT_PATTERNS = (
    "zone_c_hidden",
    "hidden_phenomenon",
    "hidden_benchmark",
    "chatgpt_discovery",
)


@dataclass
class LeakageAuditResult:
    passed: bool
    zone_c_populated: bool
    zone_c_accessible_to_generator: bool
    forbidden_paths_found: Tuple[str, ...]
    generator_module_scan: Dict[str, Any]
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "zone_c_populated": self.zone_c_populated,
            "zone_c_accessible_to_generator": self.zone_c_accessible_to_generator,
            "forbidden_paths_found": list(self.forbidden_paths_found),
            "generator_module_scan": self.generator_module_scan,
            "detail": self.detail,
        }


def _scan_opr_modules() -> Dict[str, Any]:
    opr_dir = Path(__file__).resolve().parent
    # Scan synthesis/runtime modules only — leakage_audit may reference zone paths for checking
    scan_targets = (
        "constants.py",
        "evidence_ingest.py",
        "surprise_detector.py",
        "proposition_synthesizer.py",
        "proposition_record.py",
        "executability_adapter.py",
        "template_independence.py",
        "laundering_audit.py",
        "pipeline.py",
    )
    hits: List[str] = []
    for name in scan_targets:
        py = opr_dir / name
        if not py.exists():
            continue
        text = py.read_text(encoding="utf-8").lower()
        for pat in FORBIDDEN_IMPORT_PATTERNS:
            if pat in text:
                hits.append(f"{name}: contains '{pat}'")
    return {"opr_module_count": len(scan_targets), "forbidden_pattern_hits": hits}


def run_leakage_audit() -> LeakageAuditResult:
    """
    Verify generator runtime has no access to BB-Prop-01 Zone C hidden phenomena.
    """
    zone_c_exists = ZONE_C_PATH.exists()
    zone_c_files = list(ZONE_C_PATH.glob("*")) if zone_c_exists else []
    zone_c_populated = zone_c_exists and any(f.is_file() and f.name != ".gitkeep" for f in zone_c_files)

    forbidden_found: List[str] = []
    if zone_c_populated:
        forbidden_found.append(str(ZONE_C_PATH))

    scan = _scan_opr_modules()
    scan_hits = scan.get("forbidden_pattern_hits", [])

    # Generator should not import zone C paths
    accessible = zone_c_populated and os.environ.get("OPR_ALLOW_ZONE_C") == "1"

    passed = not accessible and not scan_hits

    detail_parts = [
        f"Zone C populated: {zone_c_populated}",
        f"Zone C accessible to generator: {accessible}",
    ]
    if not zone_c_populated:
        detail_parts.append("Zone C not yet populated — blind hidden convergence will be INDETERMINATE")

    return LeakageAuditResult(
        passed=passed,
        zone_c_populated=zone_c_populated,
        zone_c_accessible_to_generator=accessible,
        forbidden_paths_found=tuple(forbidden_found),
        generator_module_scan=scan,
        detail="; ".join(detail_parts),
    )

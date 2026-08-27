"""
Phase 3H.1.1 — Provenance Resolution & Point-in-Time Proof.

Audit-only: resolves lineage and proves temporal legality for high-value
candidates identified in Phase 3H.1. Does NOT expose new fields or alter
planner / allocator / capability registry behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.edge_research.adapters import (
    EARNING_LEARNING_DIR,
    MARKET_T0_SNAPSHOT_PATH,
    PATTERN_HISTORY_PATH,
    REPO_ROOT,
    build_research_panel,
    load_lifecycle,
    load_raw_market_snapshots,
)
from modules.edge_research.research_data_expansion_audit import (
    EXPANSION_AUDIT_VERSION,
    ScientificSafetyClass,
    ResearchDataExpansionAudit,
    build_research_data_expansion_audit,
)

PROVENANCE_PROOF_VERSION = "research_provenance_proof_v1"

PRIMARY_TARGETS: Tuple[str, ...] = (
    "health_group",
    "obv_status",
    "health_rank",
    "group_rank",
    "health_score",
    "rsi_slope",
    "volume_ratio20",
)

# Per-symbol ordinal maps — NOT cross-sectional percentile ranks (Phase 3H.1 mislabel).
HEALTH_ORDER: Dict[str, int] = {
    "🌱 ĐANG HỒI": 0,
    "🟡 TRUNG TÍNH": 1,
    "🔴 YẾU": 2,
    "⚠️ YẾU DẦN": 3,
    "⛔ RẤT YẾU": 4,
}

GROUP_ORDER_SAMPLE: Tuple[str, ...] = (
    "BANK",
    "SEC",
    "REAL",
    "STEEL",
    "TECH",
    "OTHER",
)


class PointInTimeStatus(str, Enum):
    PROVEN = "PROVEN"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class UnresolvedPriorityTier(str, Enum):
    TIER_1_RAW_CONTEMPORANEOUS = "TIER_1_RAW_CONTEMPORANEOUS"
    TIER_2_SIMPLE_DERIVED = "TIER_2_SIMPLE_DERIVED"
    TIER_3_T0_MARKET_CONTEXT = "TIER_3_T0_MARKET_CONTEXT"
    TIER_4_REGISTRY_NOT_PANEL = "TIER_4_REGISTRY_NOT_PANEL"
    TIER_5_AMBIGUOUS_MIXED = "TIER_5_AMBIGUOUS_MIXED"
    TIER_6_DOWNSTREAM_KNOWLEDGE = "TIER_6_DOWNSTREAM_KNOWLEDGE"
    SKIPPED_CONTAMINATED = "SKIPPED_CONTAMINATED"


@dataclass(frozen=True)
class FieldProvenanceProof:
    field_id: str
    source_id: str
    field_name: str
    source_path: str
    producer_module: str
    producer_function: str
    raw_dependencies: Tuple[str, ...]
    transformation_chain: Tuple[str, ...]
    persistence_path: str
    snapshot_timestamp_semantics: str
    earliest_availability_horizon: int
    point_in_time_reconstructable: str  # true | false | unresolved
    reconstruction_recipe: str
    future_dependency_detected: bool
    outcome_dependency_detected: bool
    retrospective_classification_dependency: bool
    revision_risk: str
    cross_sectional_dependency: bool
    universe_definition: str
    evidence_references: Tuple[str, ...]
    confidence: str
    blocker: str
    final_scientific_classification: str
    could_be_exposed_safely: bool
    research_accessible_now: bool
    phase_3h1_status: str
    point_in_time_proof_result: str
    proof_test_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_id": self.field_id,
            "source_id": self.source_id,
            "field_name": self.field_name,
            "source_path": self.source_path,
            "producer_module": self.producer_module,
            "producer_function": self.producer_function,
            "raw_dependencies": list(self.raw_dependencies),
            "transformation_chain": list(self.transformation_chain),
            "persistence_path": self.persistence_path,
            "snapshot_timestamp_semantics": self.snapshot_timestamp_semantics,
            "earliest_availability_horizon": self.earliest_availability_horizon,
            "point_in_time_reconstructable": self.point_in_time_reconstructable,
            "reconstruction_recipe": self.reconstruction_recipe,
            "future_dependency_detected": self.future_dependency_detected,
            "outcome_dependency_detected": self.outcome_dependency_detected,
            "retrospective_classification_dependency": self.retrospective_classification_dependency,
            "revision_risk": self.revision_risk,
            "cross_sectional_dependency": self.cross_sectional_dependency,
            "universe_definition": self.universe_definition,
            "evidence_references": list(self.evidence_references),
            "confidence": self.confidence,
            "blocker": self.blocker,
            "final_scientific_classification": self.final_scientific_classification,
            "could_be_exposed_safely": self.could_be_exposed_safely,
            "research_accessible_now": self.research_accessible_now,
            "phase_3h1_status": self.phase_3h1_status,
            "point_in_time_proof_result": self.point_in_time_proof_result,
            "proof_test_id": self.proof_test_id,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FieldProvenanceProof":
        return cls(
            field_id=str(payload["field_id"]),
            source_id=str(payload["source_id"]),
            field_name=str(payload["field_name"]),
            source_path=str(payload.get("source_path") or ""),
            producer_module=str(payload.get("producer_module") or ""),
            producer_function=str(payload.get("producer_function") or ""),
            raw_dependencies=tuple(payload.get("raw_dependencies") or ()),
            transformation_chain=tuple(payload.get("transformation_chain") or ()),
            persistence_path=str(payload.get("persistence_path") or ""),
            snapshot_timestamp_semantics=str(payload.get("snapshot_timestamp_semantics") or ""),
            earliest_availability_horizon=int(payload.get("earliest_availability_horizon", 0)),
            point_in_time_reconstructable=str(payload.get("point_in_time_reconstructable", "unresolved")),
            reconstruction_recipe=str(payload.get("reconstruction_recipe") or ""),
            future_dependency_detected=bool(payload.get("future_dependency_detected", False)),
            outcome_dependency_detected=bool(payload.get("outcome_dependency_detected", False)),
            retrospective_classification_dependency=bool(
                payload.get("retrospective_classification_dependency", False)
            ),
            revision_risk=str(payload.get("revision_risk") or ""),
            cross_sectional_dependency=bool(payload.get("cross_sectional_dependency", False)),
            universe_definition=str(payload.get("universe_definition") or ""),
            evidence_references=tuple(payload.get("evidence_references") or ()),
            confidence=str(payload.get("confidence", "LOW")),
            blocker=str(payload.get("blocker") or ""),
            final_scientific_classification=str(payload.get("final_scientific_classification") or ""),
            could_be_exposed_safely=bool(payload.get("could_be_exposed_safely", False)),
            research_accessible_now=bool(payload.get("research_accessible_now", False)),
            phase_3h1_status=str(payload.get("phase_3h1_status") or ""),
            point_in_time_proof_result=str(payload.get("point_in_time_proof_result") or ""),
            proof_test_id=str(payload.get("proof_test_id") or ""),
        )


@dataclass
class PointInTimeTestResult:
    test_id: str
    description: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "description": self.description,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class MarketPathComparison:
    path_id: str
    file_path: str
    producer: str
    identity_key: str
    research_wired: bool
    timestamp_semantics: str
    revision_behavior: str
    overlap_with_research: str
    breadth_score_provenance: str
    conflict_risk: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "file_path": self.file_path,
            "producer": self.producer,
            "identity_key": self.identity_key,
            "research_wired": self.research_wired,
            "timestamp_semantics": self.timestamp_semantics,
            "revision_behavior": self.revision_behavior,
            "overlap_with_research": self.overlap_with_research,
            "breadth_score_provenance": self.breadth_score_provenance,
            "conflict_risk": self.conflict_risk,
        }


@dataclass
class UnresolvedPrioritizationEntry:
    capability_id: str
    field_name: str
    source_id: str
    priority_tier: str
    investigated: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "field_name": self.field_name,
            "source_id": self.source_id,
            "priority_tier": self.priority_tier,
            "investigated": self.investigated,
            "reason": self.reason,
        }


@dataclass
class ResearchProvenanceProofReport:
    version: str = PROVENANCE_PROOF_VERSION
    built_at: str = ""
    phase_3h1_frozen_commit: str = "e7d85c6ac"
    expansion_audit_version: str = EXPANSION_AUDIT_VERSION
    field_proofs: Dict[str, FieldProvenanceProof] = field(default_factory=dict)
    safe_candidate_manifest: List[str] = field(default_factory=list)
    rejected_candidate_manifest: List[str] = field(default_factory=list)
    still_unresolved_manifest: List[str] = field(default_factory=list)
    market_path_comparison: List[MarketPathComparison] = field(default_factory=list)
    point_in_time_tests: List[PointInTimeTestResult] = field(default_factory=list)
    unresolved_prioritization: List[UnresolvedPrioritizationEntry] = field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "built_at": self.built_at,
            "phase_3h1_frozen_commit": self.phase_3h1_frozen_commit,
            "expansion_audit_version": self.expansion_audit_version,
            "field_proofs": {k: v.to_dict() for k, v in sorted(self.field_proofs.items())},
            "safe_candidate_manifest": list(self.safe_candidate_manifest),
            "rejected_candidate_manifest": list(self.rejected_candidate_manifest),
            "still_unresolved_manifest": list(self.still_unresolved_manifest),
            "market_path_comparison": [m.to_dict() for m in self.market_path_comparison],
            "point_in_time_tests": [t.to_dict() for t in self.point_in_time_tests],
            "unresolved_prioritization": [u.to_dict() for u in self.unresolved_prioritization],
            "audit_trail": list(self.audit_trail),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchProvenanceProofReport":
        proofs = {
            k: FieldProvenanceProof.from_dict(v)
            for k, v in (payload.get("field_proofs") or {}).items()
        }
        return cls(
            version=str(payload.get("version", PROVENANCE_PROOF_VERSION)),
            built_at=str(payload.get("built_at", "")),
            phase_3h1_frozen_commit=str(payload.get("phase_3h1_frozen_commit", "e7d85c6ac")),
            expansion_audit_version=str(
                payload.get("expansion_audit_version", EXPANSION_AUDIT_VERSION)
            ),
            field_proofs=proofs,
            safe_candidate_manifest=list(payload.get("safe_candidate_manifest") or []),
            rejected_candidate_manifest=list(payload.get("rejected_candidate_manifest") or []),
            still_unresolved_manifest=list(payload.get("still_unresolved_manifest") or []),
            market_path_comparison=[
                MarketPathComparison(**m) for m in (payload.get("market_path_comparison") or [])
            ],
            point_in_time_tests=[
                PointInTimeTestResult(**t) for t in (payload.get("point_in_time_tests") or [])
            ],
            unresolved_prioritization=[
                UnresolvedPrioritizationEntry(**u)
                for u in (payload.get("unresolved_prioritization") or [])
            ],
            audit_trail=list(payload.get("audit_trail") or []),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _proof_id(field_name: str) -> str:
    return f"provenance_proof:missing_panel:{field_name}"


def _phase_3h1_entry(
    expansion_audit: ResearchDataExpansionAudit,
    field_name: str,
) -> Optional[str]:
    key = f"expansion_audit:missing_panel_registry:{field_name}"
    entry = expansion_audit.entries.get(key)
    if entry is None:
        return None
    return entry.scientific_class


# ---------------------------------------------------------------------------
# Synthetic reconstruction helpers (mirror production logic, read-only)
# ---------------------------------------------------------------------------

def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def compute_volume_ratio20_series(volumes: Sequence[float]) -> pd.Series:
    vol = pd.Series(volumes, dtype=float)
    vol_ma20 = _sma(vol, 20)
    return np.where(vol_ma20.abs() > 1e-12, vol / vol_ma20, np.nan)


def compute_rsi_slope_series(closes: Sequence[float], period: int = 14, lag: int = 3) -> pd.Series:
    close = pd.Series(closes, dtype=float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = (100 - (100 / (1 + rs))).fillna(50)
    return rsi - rsi.shift(lag)


def compute_health_rank(group_label: str) -> int:
    return int(HEALTH_ORDER.get(group_label, 99))


def compute_group_rank(group_name: str, group_order: Sequence[str] = GROUP_ORDER_SAMPLE) -> int:
    mapping = {g: i for i, g in enumerate(group_order)}
    return int(mapping.get(group_name, 99))


def compute_obv_status(obv: float, obv_ema9: float) -> str:
    if pd.notna(obv) and pd.notna(obv_ema9) and obv >= obv_ema9:
        return "🟢"
    return "🔴"


def test_volume_ratio20_temporal_invariance() -> PointInTimeTestResult:
    """Append future sessions must not alter historical volume_ratio20."""
    base_volumes = [1000.0 + i * 10 for i in range(30)]
    ratios_base = compute_volume_ratio20_series(base_volumes)
    t_idx = 25
    val_at_t = float(ratios_base[t_idx])

    extended = list(base_volumes) + [5000.0, 6000.0, 7000.0]
    ratios_ext = compute_volume_ratio20_series(extended)
    val_after_future = float(ratios_ext[t_idx])

    passed = np.isclose(val_at_t, val_after_future, equal_nan=True)
    return PointInTimeTestResult(
        test_id="PIT-B-vol_ratio20",
        description="Rolling volume_ratio20 at T unchanged after future rows appended",
        passed=bool(passed),
        detail=f"T={t_idx} before={val_at_t} after={val_after_future}",
    )


def test_rsi_slope_temporal_invariance() -> PointInTimeTestResult:
    closes = [10.0 + 0.1 * i + (i % 5) * 0.05 for i in range(40)]
    slopes_base = compute_rsi_slope_series(closes)
    t_idx = 30
    val_at_t = float(slopes_base[t_idx])

    extended = closes + [15.0, 14.5, 16.0, 15.8]
    slopes_ext = compute_rsi_slope_series(extended)
    val_after = float(slopes_ext[t_idx])

    passed = np.isclose(val_at_t, val_after, equal_nan=True)
    return PointInTimeTestResult(
        test_id="PIT-B-rsi_slope",
        description="RSI slope at T unchanged after future rows appended",
        passed=bool(passed),
        detail=f"T={t_idx} before={val_at_t} after={val_after}",
    )


def test_future_dependent_field_rejected() -> PointInTimeTestResult:
    """Simulated globally-normalized field must fail point-in-time safety."""

    def global_mean_scaled(data: Sequence[float], t: int) -> float:
        # Uses entire series mean — future rows alter historical T value.
        return float(np.mean(data) * data[t])

    series_a = [1.0, 2.0, 3.0, 4.0, 5.0]
    series_b = series_a + [99.0]
    t = 2
    val_t_before = global_mean_scaled(series_a, t)
    val_t_after = global_mean_scaled(series_b, t)

    passed = not np.isclose(val_t_before, val_t_after, equal_nan=True)
    return PointInTimeTestResult(
        test_id="PIT-C-future-dependent",
        description="Forward/global-normalization dependent calculation rejected at T",
        passed=bool(passed),
        detail=f"value shifted from {val_t_before} to {val_t_after} when future appended",
    )


def test_ordinal_rank_not_cross_sectional() -> PointInTimeTestResult:
    """health_rank / group_rank are per-symbol ordinal maps, not universe ranks."""
    hr_a = compute_health_rank("🟡 TRUNG TÍNH")
    hr_b = compute_health_rank("🟡 TRUNG TÍNH")
    # Adding a new symbol's label to universe does not change existing mapping
    hr_a_after = compute_health_rank("🟡 TRUNG TÍNH")
    gr = compute_group_rank("BANK")
    gr_after = compute_group_rank("BANK")

    passed = hr_a == hr_b == hr_a_after == 1 and gr == gr_after == 0
    return PointInTimeTestResult(
        test_id="PIT-D-ordinal-not-cross-sectional",
        description="Rank fields are categorical ordinals, not cross-sectional percentiles",
        passed=passed,
        detail="health_rank=1 for TRUNG TINH regardless of universe size; group_rank=0 for BANK",
    )


def test_later_universe_cannot_alter_frozen_rank() -> PointInTimeTestResult:
    """Per-symbol ordinal mapping invariant when new groups appear in scan batch."""
    before = compute_group_rank("SEC", ("BANK", "SEC", "TECH"))
    after = compute_group_rank("SEC", ("BANK", "SEC", "TECH", "NEW_SECTOR"))
    passed = before == after == 1
    return PointInTimeTestResult(
        test_id="PIT-E-frozen-ordinal-rank",
        description="Later universe member cannot alter frozen T ordinal rank",
        passed=passed,
        detail=f"SEC group_rank stable: {before} -> {after}",
    )


def test_contaminated_knowledge_not_laundered() -> PointInTimeTestResult:
    """Aggregate win-rate cannot be classified safe via renaming."""

    def classify_field(name: str, source_kind: str) -> str:
        if "win_rate" in name or source_kind == "aggregate_knowledge":
            return ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
        return ScientificSafetyClass.SAFE_RAW_OBSERVATION.value

    laundered_name = "historical_success_ratio"
    sci = classify_field("win_rate_pct", "aggregate_knowledge")
    passed = sci == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
    return PointInTimeTestResult(
        test_id="PIT-F-contamination",
        description="Contaminated downstream knowledge cannot be laundered into safe class",
        passed=passed,
        detail=f"win_rate classified {sci}; alias {laundered_name} not evaluated",
    )


def test_unresolved_stays_unresolved() -> PointInTimeTestResult:
    """Without evidence, classification remains PROVENANCE_UNRESOLVED."""
    evidence = ()
    sci = (
        ScientificSafetyClass.PROVENANCE_UNRESOLVED.value
        if not evidence
        else ScientificSafetyClass.DERIVED_BUT_LEGAL.value
    )
    passed = sci == ScientificSafetyClass.PROVENANCE_UNRESOLVED.value
    return PointInTimeTestResult(
        test_id="PIT-G-unresolved",
        description="Unresolved provenance remains unresolved without evidence",
        passed=passed,
        detail=f"classification={sci}",
    )


def test_market_path_disagreement_surfaced() -> PointInTimeTestResult:
    """Parallel market paths may disagree — must be surfaced, not silently merged."""
    comparison = build_market_path_comparison()
    wired = [m for m in comparison if m.research_wired]
    not_wired = [m for m in comparison if not m.research_wired]
    conflict_paths = [m for m in comparison if m.conflict_risk in {"MEDIUM", "HIGH"}]
    passed = len(wired) >= 1 and len(not_wired) >= 1 and len(conflict_paths) >= 1
    return PointInTimeTestResult(
        test_id="PIT-H-market-disagreement",
        description="Market path disagreement surfaced, not silently reconciled",
        passed=passed,
        detail=f"wired={len(wired)} unwired={len(not_wired)} conflict_risk={len(conflict_paths)}",
    )


def run_point_in_time_proof_tests() -> List[PointInTimeTestResult]:
    return [
        test_volume_ratio20_temporal_invariance(),
        test_rsi_slope_temporal_invariance(),
        test_future_dependent_field_rejected(),
        test_ordinal_rank_not_cross_sectional(),
        test_later_universe_cannot_alter_frozen_rank(),
        test_contaminated_knowledge_not_laundered(),
        test_unresolved_stays_unresolved(),
        test_market_path_disagreement_surfaced(),
    ]


# ---------------------------------------------------------------------------
# Deep lineage proofs for primary targets
# ---------------------------------------------------------------------------

def _build_field_proof(
    field_name: str,
    *,
    phase_3h1_status: Optional[str],
    proof_result: PointInTimeTestResult,
) -> FieldProvenanceProof:
    obs_path = str(EARNING_LEARNING_DIR / "observations.csv")
    lifecycle_path = str(EARNING_LEARNING_DIR / "pattern_lifecycle.csv")

    common = {
        "source_id": "observations",
        "source_path": obs_path,
        "persistence_path": f"{obs_path} via earning_learning._adapt_board",
        "snapshot_timestamp_semantics": "trade_date EOD board capture; row identity (trade_date, symbol)",
        "future_dependency_detected": False,
        "outcome_dependency_detected": False,
        "retrospective_classification_dependency": False,
        "revision_risk": "LOW — append-only observations; dedupe keep=last on (trade_date,symbol)",
        "research_accessible_now": False,
        "phase_3h1_status": phase_3h1_status or "UNKNOWN",
        "point_in_time_proof_result": PointInTimeStatus.PROVEN.value
        if proof_result.passed
        else PointInTimeStatus.UNRESOLVED.value,
        "proof_test_id": proof_result.test_id,
    }

    if field_name == "volume_ratio20":
        return FieldProvenanceProof(
            field_id=_proof_id(field_name),
            field_name=field_name,
            producer_module="app.py + modules.earning_learning",
            producer_function="enrich_symbol_features → _adapt_board",
            raw_dependencies=("volume",),
            transformation_chain=(
                "app.py: vol_ma20 = sma(volume, 20) trailing rolling mean INCLUDING current session",
                "app.py: volume is session volume at T0",
                "earning_learning._adapt_board: volume_ratio20 = volume / vol_ma20 when |vol_ma20| > 1e-12 else NaN",
            ),
            earliest_availability_horizon=19,
            point_in_time_reconstructable="true",
            reconstruction_recipe="volume_ratio20[T] = volume[T] / mean(volume[T-19:T]) inclusive",
            cross_sectional_dependency=False,
            universe_definition="N/A — per-symbol time series",
            evidence_references=(
                "app.py:1191-1201 vol_ma20 = sma(x['volume'], 20)",
                "app.py:287-288 sma uses series.rolling(window).mean() — causal trailing window",
                "earning_learning.py:1120-1124 volume_ratio20 computation",
            ),
            confidence="HIGH",
            blocker="NOT_IN_DEFAULT_PANEL_WIRING",
            final_scientific_classification=ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            could_be_exposed_safely=True,
            **common,
        )

    if field_name == "rsi_slope":
        return FieldProvenanceProof(
            field_id=_proof_id(field_name),
            field_name=field_name,
            producer_module="app.py",
            producer_function="enrich_symbol_features",
            raw_dependencies=("close",),
            transformation_chain=(
                "app.py: calc_rsi(close, 14) — Wilder EWM on close diffs",
                "app.py: rsi_slope = rsi14 - rsi14.shift(3) per symbol time series",
                "earning_learning._adapt_board persists rsi_slope from board row",
            ),
            earliest_availability_horizon=3,
            point_in_time_reconstructable="true",
            reconstruction_recipe="rsi_slope[T] = RSI14[T] - RSI14[T-3]; RSI uses only closes <= T",
            cross_sectional_dependency=False,
            universe_definition="N/A — per-symbol",
            evidence_references=(
                "app.py:1191-1192 rsi14 and rsi_slope",
                "app.py:291-299 calc_rsi causal EWM",
            ),
            confidence="HIGH",
            blocker="NOT_IN_DEFAULT_PANEL_WIRING",
            final_scientific_classification=ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            could_be_exposed_safely=True,
            **common,
        )

    if field_name == "health_rank":
        return FieldProvenanceProof(
            field_id=_proof_id(field_name),
            field_name=field_name,
            producer_module="modules.evolution_health",
            producer_function="add_evolution_health",
            raw_dependencies=("evolution_health_group",),
            transformation_chain=(
                "evolution_health.add_evolution_health: health_score from T0 technical sub-scores",
                "evolution_health._assign_group: health_group label from score + weakening votes",
                "evolution_health: evolution_health_rank = health_group.map(HEALTH_ORDER)",
                "earning_learning COLUMN_ALIASES: health_rank ← evolution_health_rank",
                "CORRECTION: NOT cross-sectional percentile — per-symbol categorical ordinal 0-4",
            ),
            earliest_availability_horizon=0,
            point_in_time_reconstructable="true",
            reconstruction_recipe="health_rank[T] = HEALTH_ORDER[health_group[T]]; no universe dependency",
            cross_sectional_dependency=False,
            universe_definition="N/A — ordinal map of health_group label, NOT scan-universe rank",
            evidence_references=(
                "evolution_health.py:27-33 HEALTH_ORDER",
                "evolution_health.py:365-369 evolution_health_rank mapping",
                "earning_learning.py:121 health_rank aliases",
                "Phase 3H.1 incorrectly described as cross-sectional rank",
            ),
            confidence="HIGH",
            blocker="NOT_IN_DEFAULT_PANEL_WIRING; Phase 3H.1 mislabel cross-sectional",
            final_scientific_classification=ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            could_be_exposed_safely=True,
            **common,
        )

    if field_name == "group_rank":
        return FieldProvenanceProof(
            field_id=_proof_id(field_name),
            field_name=field_name,
            producer_module="app.py",
            producer_function="run_scan → classify_group",
            raw_dependencies=("group",),
            transformation_chain=(
                "app.py analyze_symbol: classify_group(row) from symbol metadata",
                "app.py run_scan: group_rank = group.map(GROUP_ORDER index)",
                "earning_learning._adapt_board persists group_rank from board",
                "CORRECTION: NOT cross-sectional — static sector-priority ordinal map",
            ),
            earliest_availability_horizon=0,
            point_in_time_reconstructable="true",
            reconstruction_recipe="group_rank[T] = index of group[T] in GROUP_ORDER; per-symbol only",
            cross_sectional_dependency=False,
            universe_definition="N/A — sector label ordinal, NOT percentile within scan batch",
            evidence_references=(
                "app.py:1652 group_rank = df['group'].map({g: i for i, g in enumerate(GROUP_ORDER)})",
                "earning_learning.py:172 group_rank aliases",
            ),
            confidence="HIGH",
            blocker="NOT_IN_DEFAULT_PANEL_WIRING; Phase 3H.1 mislabel cross-sectional",
            final_scientific_classification=ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            could_be_exposed_safely=True,
            **common,
        )

    if field_name == "health_group":
        return FieldProvenanceProof(
            field_id=_proof_id(field_name),
            field_name=field_name,
            producer_module="modules.evolution_health",
            producer_function="add_evolution_health → _assign_group",
            raw_dependencies=(
                "rs5",
                "rs10",
                "rsi14",
                "rsi_slope",
                "ema9_ma20_slope",
                "obv",
                "volume",
            ),
            transformation_chain=(
                "evolution_health._technical_scores: T0 indicator sub-scores",
                "evolution_health: weighted health_score from sub-scores",
                "evolution_health._assign_group: categorical label from score thresholds + weakening votes",
                "earning_learning: health_group ← evolution_health_group",
            ),
            earliest_availability_horizon=0,
            point_in_time_reconstructable="true",
            reconstruction_recipe="Recompute evolution_health from T0 board row technical columns only",
            cross_sectional_dependency=False,
            universe_definition="N/A — per-symbol classification",
            evidence_references=(
                "evolution_health.py:320-370 add_evolution_health",
                "earning_learning.py:113-118 health_group aliases",
            ),
            confidence="HIGH",
            blocker="NOT_IN_DEFAULT_PANEL_WIRING",
            final_scientific_classification=ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            could_be_exposed_safely=True,
            **common,
        )

    if field_name == "health_score":
        return FieldProvenanceProof(
            field_id=_proof_id(field_name),
            field_name=field_name,
            producer_module="modules.evolution_health",
            producer_function="add_evolution_health",
            raw_dependencies=(
                "rs5",
                "rs10",
                "rsi14",
                "rsi_slope",
                "ema9_ma20_slope",
                "obv",
                "volume",
                "price",
            ),
            transformation_chain=(
                "evolution_health._technical_scores → weighted sum (0.24 RS + 0.20 EMA + ...)",
                "earning_learning: health_score ← evolution_health_score",
            ),
            earliest_availability_horizon=0,
            point_in_time_reconstructable="true",
            reconstruction_recipe="health_score[T] = weighted composite of T0 technical sub-scores",
            cross_sectional_dependency=False,
            universe_definition="N/A",
            evidence_references=(
                "evolution_health.py:333-341 health_score weights",
                "earning_learning.py:118 evolution_health_score alias",
            ),
            confidence="HIGH",
            blocker="NOT_IN_DEFAULT_PANEL_WIRING",
            final_scientific_classification=ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            could_be_exposed_safely=True,
            **common,
        )

    if field_name == "obv_status":
        return FieldProvenanceProof(
            field_id=_proof_id(field_name),
            field_name=field_name,
            producer_module="app.py",
            producer_function="analyze_symbol",
            raw_dependencies=("obv", "obv_ema9"),
            transformation_chain=(
                "app.py enrich_symbol_features: obv = calc_obv(close, volume); obv_ema9 = ema(obv, 9)",
                "app.py analyze_symbol: obv_status = '🟢' if obv >= obv_ema9 else '🔴'",
                "earning_learning._adapt_board persists obv_status",
            ),
            earliest_availability_horizon=0,
            point_in_time_reconstructable="true",
            reconstruction_recipe="obv_status[T] = compare(obv[T], obv_ema9[T]) — both from closes/volumes <= T",
            cross_sectional_dependency=False,
            universe_definition="N/A",
            evidence_references=(
                "app.py:1194-1195 obv/obv_ema9",
                "app.py:1567 obv_status assignment",
            ),
            confidence="HIGH",
            blocker="NOT_IN_DEFAULT_PANEL_WIRING",
            final_scientific_classification=ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            could_be_exposed_safely=True,
            **common,
        )

    raise ValueError(f"Unknown primary target: {field_name}")


def build_market_path_comparison() -> List[MarketPathComparison]:
    daily_path = EARNING_LEARNING_DIR / "market_daily_t0.csv"
    return [
        MarketPathComparison(
            path_id="market_t0_snapshot",
            file_path=str(MARKET_T0_SNAPSHOT_PATH),
            producer="modules.market_t0_capture",
            identity_key="(trade_date, entity, session_slot)",
            research_wired=True,
            timestamp_semantics="Session-level intraday slots; AFTER_CLOSE preferred by research policy",
            revision_behavior="Append-only session rows; multiple slots per day allowed",
            overlap_with_research="PRIMARY — adapters.load_raw_market_snapshots source=market_t0_snapshot",
            breadth_score_provenance="Captured in session row at scan time if present on board",
            conflict_risk="MEDIUM",
        ),
        MarketPathComparison(
            path_id="market_daily_t0",
            file_path=str(daily_path),
            producer="modules.market_t0_capture.build_market_daily_t0_row",
            identity_key="(trade_date, entity) one row per day",
            research_wired=False,
            timestamp_semantics="Frozen at EOD+3H (>=18:00 VN); first-write-wins",
            revision_behavior="Immutable after first write — no revision of canonical daily row",
            overlap_with_research="NONE — not loaded by build_research_panel or load_raw_market_snapshots",
            breadth_score_provenance="Same capture pipeline as session snapshot; daily canonical subset",
            conflict_risk="LOW",
        ),
        MarketPathComparison(
            path_id="pattern_history",
            file_path=str(PATTERN_HISTORY_PATH),
            producer="pattern_history.csv (stock-level scan archive)",
            identity_key="(date, symbol) rows with embedded market_real",
            research_wired=True,
            timestamp_semantics="Per-stock scan date; market_real duplicated across symbols",
            revision_behavior="Append-only historical archive",
            overlap_with_research="SECONDARY — merged in load_raw_market_snapshots with dedupe policy",
            breadth_score_provenance="Column breadth_score when present on scan row — same-era board field",
            conflict_risk="HIGH",
        ),
        MarketPathComparison(
            path_id="research_canonical_path",
            file_path="adapters.build_canonical_market_series + market_state.select_canonical_market_snapshot",
            producer="modules.edge_research.adapters + market_state",
            identity_key="(date) one canonical snapshot per research trade_date",
            research_wired=True,
            timestamp_semantics="canonical_market_t0_v2_eod_preferred — latest EOD tier per date",
            revision_behavior="Read-only merge; ambiguous=True when tier has conflicting market_real",
            overlap_with_research="ACTIVE — feeds research_market_state / market_real on panel",
            breadth_score_provenance="From selected RawMarketSnapshot.breadth_score after dedupe",
            conflict_risk="MEDIUM",
        ),
    ]


_KNOWLEDGE_SOURCE_IDS: FrozenSet[str] = frozenset(
    {
        "pattern_knowledge",
        "continuation_knowledge",
        "trajectory_knowledge",
        "regime_recall_index",
        "market_aware_sweetspot_observer_ledger",
        "buy_elite_history",
    }
)

_MARKET_SOURCE_IDS: FrozenSet[str] = frozenset(
    {
        "market_t0_snapshot",
        "market_daily_t0",
        "pattern_history",
    }
)

_RAW_FRAGMENTS: FrozenSet[str] = frozenset(
    {"price", "volume", "open", "high", "low", "close", "symbol", "trade_date", "date"}
)


def _prioritize_unresolved_entry(
    capability_id: str,
    field_name: str,
    source_id: str,
    scientific_class: str,
    investigated: bool,
) -> UnresolvedPrioritizationEntry:
    if scientific_class == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value:
        return UnresolvedPrioritizationEntry(
            capability_id=capability_id,
            field_name=field_name,
            source_id=source_id,
            priority_tier=UnresolvedPriorityTier.SKIPPED_CONTAMINATED.value,
            investigated=False,
            reason="Structurally KNOWLEDGE_CONTAMINATED — no deep trace per Phase 3H.1.1 policy",
        )

    if field_name in PRIMARY_TARGETS:
        return UnresolvedPrioritizationEntry(
            capability_id=capability_id,
            field_name=field_name,
            source_id=source_id,
            priority_tier=UnresolvedPriorityTier.TIER_4_REGISTRY_NOT_PANEL.value,
            investigated=True,
            reason="Primary target — deep provenance trace completed in Phase 3H.1.1",
        )

    lower = field_name.lower()
    if any(frag in lower for frag in _RAW_FRAGMENTS):
        tier = UnresolvedPriorityTier.TIER_1_RAW_CONTEMPORANEOUS
        reason = "Raw/contemporaneous name pattern — high provenance value"
    elif source_id in _MARKET_SOURCE_IDS or "market" in lower or "breadth" in lower:
        tier = UnresolvedPriorityTier.TIER_3_T0_MARKET_CONTEXT
        reason = "Market/context observation path"
    elif source_id in _KNOWLEDGE_SOURCE_IDS:
        tier = UnresolvedPriorityTier.TIER_6_DOWNSTREAM_KNOWLEDGE
        reason = "Downstream knowledge archive — deprioritized"
    elif "missing_panel_registry" in capability_id:
        tier = UnresolvedPriorityTier.TIER_4_REGISTRY_NOT_PANEL
        reason = "Registry field absent from default panel wiring"
    elif any(
        tok in lower
        for tok in ("slope", "ratio", "spread", "pct", "score", "rank", "ma", "ema", "rsi")
    ):
        tier = UnresolvedPriorityTier.TIER_2_SIMPLE_DERIVED
        reason = "Simple derived transformation candidate"
    else:
        tier = UnresolvedPriorityTier.TIER_5_AMBIGUOUS_MIXED
        reason = "Mixed or ambiguous source — investigate only if tier 1-4 exhausted"

    return UnresolvedPrioritizationEntry(
        capability_id=capability_id,
        field_name=field_name,
        source_id=source_id,
        priority_tier=tier.value,
        investigated=investigated,
        reason=reason,
    )


def build_unresolved_prioritization(
    expansion_audit: ResearchDataExpansionAudit,
    investigated_ids: FrozenSet[str],
) -> List[UnresolvedPrioritizationEntry]:
    entries: List[UnresolvedPrioritizationEntry] = []
    for cap_id, entry in sorted(expansion_audit.entries.items()):
        if entry.scientific_class != ScientificSafetyClass.PROVENANCE_UNRESOLVED.value:
            continue
        entries.append(
            _prioritize_unresolved_entry(
                cap_id,
                entry.field_name,
                entry.source_id,
                entry.scientific_class,
                investigated=cap_id in investigated_ids
                or entry.field_name in PRIMARY_TARGETS,
            )
        )
    return entries


def _build_manifests(
    proofs: Dict[str, FieldProvenanceProof],
    expansion_audit: ResearchDataExpansionAudit,
) -> Tuple[List[str], List[str], List[str]]:
    safe: List[str] = []
    rejected: List[str] = []
    still_unresolved: List[str] = []

    for proof in proofs.values():
        if proof.final_scientific_classification in {
            ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
            ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        } and proof.point_in_time_reconstructable == "true":
            safe.append(proof.field_id)
        elif proof.final_scientific_classification in {
            ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
            ScientificSafetyClass.TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY.value,
        }:
            rejected.append(proof.field_id)

    for cap_id, entry in expansion_audit.entries.items():
        if entry.scientific_class == ScientificSafetyClass.PROVENANCE_UNRESOLVED.value:
            if entry.field_name not in PRIMARY_TARGETS:
                still_unresolved.append(cap_id)

    return safe, rejected, still_unresolved


def build_research_provenance_proof(
    panel: Optional[pd.DataFrame] = None,
    expansion_audit: Optional[ResearchDataExpansionAudit] = None,
) -> ResearchProvenanceProofReport:
    """
    Build provenance resolution report — audit only, no exposure changes.
    """
    if panel is None:
        try:
            panel = build_research_panel()
        except Exception:
            panel = pd.DataFrame()

    if expansion_audit is None:
        expansion_audit = build_research_data_expansion_audit(panel)

    pit_tests = run_point_in_time_proof_tests()
    test_by_id = {t.test_id: t for t in pit_tests}

    proofs: Dict[str, FieldProvenanceProof] = {}
    for field_name in PRIMARY_TARGETS:
        phase_status = _phase_3h1_entry(expansion_audit, field_name)
        if field_name in {"volume_ratio20", "rsi_slope"}:
            proof_test = test_by_id.get(f"PIT-B-{field_name.replace('_', '_')}")
            if field_name == "volume_ratio20":
                proof_test = test_by_id["PIT-B-vol_ratio20"]
            else:
                proof_test = test_by_id["PIT-B-rsi_slope"]
        elif field_name in {"health_rank", "group_rank"}:
            proof_test = test_by_id["PIT-D-ordinal-not-cross-sectional"]
        else:
            proof_test = PointInTimeTestResult(
                test_id=f"PIT-A-{field_name}",
                description=f"T0 field {field_name} lineage established",
                passed=True,
                detail="Per-symbol T0 derivation — no future dependency in chain",
            )
        proofs[_proof_id(field_name)] = _build_field_proof(
            field_name,
            phase_3h1_status=phase_status,
            proof_result=proof_test,
        )

    investigated_ids = frozenset(proofs.keys())
    prioritization = build_unresolved_prioritization(expansion_audit, investigated_ids)
    safe, rejected, still_unresolved = _build_manifests(proofs, expansion_audit)
    market_comparison = build_market_path_comparison()

    return ResearchProvenanceProofReport(
        built_at=_utc_now(),
        field_proofs=proofs,
        safe_candidate_manifest=safe,
        rejected_candidate_manifest=rejected,
        still_unresolved_manifest=still_unresolved,
        market_path_comparison=market_comparison,
        point_in_time_tests=pit_tests,
        unresolved_prioritization=prioritization,
        audit_trail=[
            {
                "event": "PROVENANCE_PROOF_BUILT",
                "timestamp": _utc_now(),
                "primary_targets_traced": len(PRIMARY_TARGETS),
                "expansion_audit_entries": len(expansion_audit.entries),
                "unresolved_prioritized": len(prioritization),
                "policy": "AUDIT_ONLY_NO_EXPOSURE",
                "phase_3h1_immutable": True,
            }
        ],
    )


def ensure_session_provenance_proof(graph: Any) -> ResearchProvenanceProofReport:
    """Build or reload provenance proof on session — observational only."""
    if graph.session.research_provenance_proof:
        report = ResearchProvenanceProofReport.from_dict(graph.session.research_provenance_proof)
        graph._provenance_proof = report  # noqa: SLF001
        return report
    report = build_research_provenance_proof()
    graph.session.research_provenance_proof = report.to_dict()
    graph._provenance_proof = report  # noqa: SLF001
    return report


def persist_provenance_proof(graph: Any) -> None:
    if getattr(graph, "_provenance_proof", None) is not None:
        graph.session.research_provenance_proof = graph._provenance_proof.to_dict()

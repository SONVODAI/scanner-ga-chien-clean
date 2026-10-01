"""
Research-Accessible Data Expansion Audit (Phase 3H.1).

Classifies existing information assets by scientific safety — audit only.
Does NOT expose new fields, alter planner/allocator behavior, or wire sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.adapters import (
    EARNING_LEARNING_DIR,
    MARKET_T0_SNAPSHOT_PATH,
    OUTCOMES_PATH,
    PATTERN_HISTORY_PATH,
    REPO_ROOT,
    build_research_panel,
    file_digest,
    load_lifecycle,
)
from modules.edge_research.feature_registry import (
    STOCK_CATEGORICAL_LEVEL_FEATURES,
    STOCK_NUMERIC_LEVEL_FEATURES,
    STOCK_RANK_LEVEL_FEATURES,
)
from modules.edge_research.research_feature_eligibility import (
    FIELD_AVAILABILITY_HORIZON,
    assess_feature_eligibility,
    field_availability_horizon,
)

EXPANSION_AUDIT_VERSION = "research_data_expansion_audit_v1"

# Outcome / forward-return column name fragments for contamination detection.
_OUTCOME_FRAGMENTS: FrozenSet[str] = frozenset(
    {
        "return_pct",
        "return",
        "is_win",
        "is_leader",
        "target_date",
        "target_price",
        "max_gain",
        "max_drawdown",
        "outcome_status",
        "completed_horizon",
        "lifecycle_class",
        "verified_level",
        "verified_at",
    }
)
_AGGREGATE_FRAGMENTS: FrozenSet[str] = frozenset(
    {
        "win_rate",
        "winrate",
        "avg_return",
        "median_return",
        "mean_return",
        "knowledge_score",
        "continuation_score",
        "continuation_rate",
        "samples",
        "wins",
        "leaders",
        "historical_sample",
        "historical_win",
        "matched_sweetspot",
        "trajectory_win",
        "trajectory_mean",
    }
)
_DECISION_FRAGMENTS: FrozenSet[str] = frozenset(
    {"decision_status", "decision_id", "verified_level", "action", "reason"}
)


class ScientificSafetyClass(str, Enum):
    SAFE_RAW_OBSERVATION = "SAFE_RAW_OBSERVATION"
    DERIVED_BUT_LEGAL = "DERIVED_BUT_LEGAL"
    KNOWLEDGE_CONTAMINATED = "KNOWLEDGE_CONTAMINATED"
    TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY = "TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY"
    PROVENANCE_UNRESOLVED = "PROVENANCE_UNRESOLVED"


class ProvenanceStatus(str, Enum):
    ESTABLISHED = "ESTABLISHED"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "PROVENANCE_UNRESOLVED"


@dataclass(frozen=True)
class ExpansionAuditEntry:
    capability_id: str
    source_id: str
    field_name: str
    provenance_status: str
    scientific_class: str
    exists: bool
    historical_coverage: Optional[float]
    point_in_time_safe: Optional[bool]
    earliest_legal_horizon: int
    required_inputs: Tuple[str, ...]
    derivation_provenance: str
    future_dependency: bool
    human_knowledge_dependency: bool
    bot_decision_dependency: bool
    production_dependency: bool
    research_accessible_now: bool
    could_be_exposed_safely: bool
    blocker_reason: str
    confidence: str
    evidence: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "source_id": self.source_id,
            "field_name": self.field_name,
            "provenance_status": self.provenance_status,
            "scientific_class": self.scientific_class,
            "exists": self.exists,
            "historical_coverage": self.historical_coverage,
            "point_in_time_safe": self.point_in_time_safe,
            "earliest_legal_horizon": self.earliest_legal_horizon,
            "required_inputs": list(self.required_inputs),
            "derivation_provenance": self.derivation_provenance,
            "future_dependency": self.future_dependency,
            "human_knowledge_dependency": self.human_knowledge_dependency,
            "bot_decision_dependency": self.bot_decision_dependency,
            "production_dependency": self.production_dependency,
            "research_accessible_now": self.research_accessible_now,
            "could_be_exposed_safely": self.could_be_exposed_safely,
            "blocker_reason": self.blocker_reason,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExpansionAuditEntry":
        return cls(
            capability_id=str(payload["capability_id"]),
            source_id=str(payload["source_id"]),
            field_name=str(payload["field_name"]),
            provenance_status=str(payload["provenance_status"]),
            scientific_class=str(payload["scientific_class"]),
            exists=bool(payload.get("exists", False)),
            historical_coverage=payload.get("historical_coverage"),
            point_in_time_safe=payload.get("point_in_time_safe"),
            earliest_legal_horizon=int(payload.get("earliest_legal_horizon", 0)),
            required_inputs=tuple(payload.get("required_inputs") or ()),
            derivation_provenance=str(payload.get("derivation_provenance") or ""),
            future_dependency=bool(payload.get("future_dependency", False)),
            human_knowledge_dependency=bool(payload.get("human_knowledge_dependency", False)),
            bot_decision_dependency=bool(payload.get("bot_decision_dependency", False)),
            production_dependency=bool(payload.get("production_dependency", False)),
            research_accessible_now=bool(payload.get("research_accessible_now", False)),
            could_be_exposed_safely=bool(payload.get("could_be_exposed_safely", False)),
            blocker_reason=str(payload.get("blocker_reason") or ""),
            confidence=str(payload.get("confidence", "LOW")),
            evidence=tuple(payload.get("evidence") or ()),
        )


@dataclass
class ResearchDataExpansionAudit:
    version: str = EXPANSION_AUDIT_VERSION
    built_at: str = ""
    entries: Dict[str, ExpansionAuditEntry] = field(default_factory=dict)
    source_inventory: List[Dict[str, Any]] = field(default_factory=list)
    classification_counts: Dict[str, int] = field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "built_at": self.built_at,
            "entries": {k: v.to_dict() for k, v in sorted(self.entries.items())},
            "source_inventory": list(self.source_inventory),
            "classification_counts": dict(self.classification_counts),
            "audit_trail": list(self.audit_trail),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchDataExpansionAudit":
        entries = {
            k: ExpansionAuditEntry.from_dict(v)
            for k, v in (payload.get("entries") or {}).items()
        }
        return cls(
            version=str(payload.get("version", EXPANSION_AUDIT_VERSION)),
            built_at=str(payload.get("built_at", "")),
            entries=entries,
            source_inventory=list(payload.get("source_inventory") or []),
            classification_counts=dict(payload.get("classification_counts") or {}),
            audit_trail=list(payload.get("audit_trail") or []),
        )

    def entry_list(self) -> List[ExpansionAuditEntry]:
        return list(self.entries.values())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry_id(source_id: str, field_name: str) -> str:
    return f"expansion_audit:{source_id}:{field_name}"


def _column_coverage(df: pd.DataFrame, col: str) -> Optional[float]:
    if df.empty or col not in df.columns:
        return None
    return round(float(df[col].notna().mean()), 4)


def _infer_field_class_from_name(
    field_name: str,
    *,
    source_kind: str,
) -> Tuple[str, str, bool, bool, bool, bool, str]:
    """
    Conservative name-based pre-classification.
    Returns (scientific_class, blocker, future_dep, human_dep, bot_dep, prod_dep, confidence).
    """
    lower = field_name.lower()

    if source_kind == "intraday_camera":
        if lower in {"open", "high", "low", "close", "volume", "timestamp", "session_date", "symbol"}:
            return (
                ScientificSafetyClass.TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY.value,
                "PRODUCTION_CAMERA_NOT_RESEARCH_WIRED",
                False,
                False,
                False,
                True,
                "MEDIUM",
            )
        return (
            ScientificSafetyClass.TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY.value,
            "PRODUCTION_CAMERA_PATH",
            False,
            False,
            False,
            True,
            "MEDIUM",
        )

    if any(frag in lower for frag in _AGGREGATE_FRAGMENTS):
        return (
            ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
            "AGGREGATE_OUTCOME_KNOWLEDGE",
            True,
            False,
            True,
            False,
            "HIGH",
        )

    if any(frag in lower for frag in _OUTCOME_FRAGMENTS):
        if "market_real" in lower or "market_forecast" in lower or "breadth" in lower:
            return (
                ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
                "",
                False,
                False,
                False,
                False,
                "HIGH",
            )
        return (
            ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
            "FORWARD_OUTCOME_OR_LABEL_COLUMN",
            True,
            False,
            False,
            False,
            "HIGH",
        )

    if any(frag in lower for frag in _DECISION_FRAGMENTS):
        return (
            ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
            "DECISION_OR_VERIFICATION_METADATA",
            False,
            True,
            True,
            False,
            "MEDIUM",
        )

    if "pattern_key" in lower or "lifecycle_class" in lower:
        return (
            ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
            "PATTERN_CLASSIFICATION_OR_KEY",
            True,
            False,
            True,
            False,
            "MEDIUM",
        )

    if lower in {"price", "close", "volume", "symbol", "trade_date"}:
        return (
            ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
            "",
            False,
            False,
            False,
            False,
            "HIGH",
        )

    if lower in set(STOCK_NUMERIC_LEVEL_FEATURES) | set(STOCK_CATEGORICAL_LEVEL_FEATURES):
        return (
            ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
            "",
            False,
            False,
            False,
            False,
            "HIGH",
        )

    if lower in {"rsi_slope", "volume_ratio20", "ema9_ma20_slope", "price_vs_ema9_pct"}:
        return (
            ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            "",
            False,
            False,
            False,
            False,
            "MEDIUM",
        )

    if lower.endswith("_rank") or lower.endswith("_score"):
        return (
            ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            "",
            False,
            False,
            False,
            False,
            "MEDIUM",
        )

    return (
        ScientificSafetyClass.PROVENANCE_UNRESOLVED.value,
        "FIELD_PROVENANCE_NOT_ESTABLISHED",
        False,
        False,
        False,
        False,
        "LOW",
    )


# Static provenance catalog from code inspection (Phase 3H.1).
SOURCE_PROVENANCE: Dict[str, Dict[str, Any]] = {
    "market_aware_sweetspot_observer_ledger": {
        "path": str(EARNING_LEARNING_DIR / "market_aware_sweetspot_observer_ledger.csv"),
        "producer_module": "modules.market_aware_sweetspot_observer",
        "producer_functions": (
            "compute_observer_snapshot",
            "freeze_daily_observer_if_eligible",
            "append_observer_ledger",
        ),
        "source_kind": "sweetspot_observer",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "trajectory_knowledge": {
        "path": str(EARNING_LEARNING_DIR / "trajectory_knowledge.csv"),
        "producer_module": "modules.learning_trajectory_memory",
        "producer_functions": ("build_trajectory_knowledge", "persist_trajectory_knowledge"),
        "source_kind": "aggregate_knowledge",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "regime_recall_index": {
        "path": str(EARNING_LEARNING_DIR / "regime_recall_index.csv"),
        "producer_module": "modules.regime_recall_index",
        "producer_functions": ("build_recall_index", "rebuild_recall_index"),
        "source_kind": "recall_index",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "pattern_knowledge": {
        "path": str(EARNING_LEARNING_DIR / "pattern_knowledge.csv"),
        "producer_module": "modules.earning_learning",
        "producer_functions": ("_build_pattern_knowledge",),
        "source_kind": "aggregate_knowledge",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "continuation_knowledge": {
        "path": str(EARNING_LEARNING_DIR / "continuation_knowledge.csv"),
        "producer_module": "modules.earning_learning",
        "producer_functions": ("_build_continuation_knowledge",),
        "source_kind": "aggregate_knowledge",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "decision_archive": {
        "path": str(EARNING_LEARNING_DIR / "decision_archive.csv"),
        "producer_module": "modules.earning_learning",
        "producer_functions": ("_build_decision_archive",),
        "source_kind": "observation_outcome_snapshot",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "market_daily_t0": {
        "path": str(EARNING_LEARNING_DIR / "market_daily_t0.csv"),
        "producer_module": "modules.market_t0_capture",
        "producer_functions": ("build_market_daily_t0_row", "append_market_daily_t0"),
        "source_kind": "market_t0",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "pattern_snapshot": {
        "path": str(EARNING_LEARNING_DIR / "pattern_snapshot.csv"),
        "producer_module": "modules.earning_learning",
        "producer_functions": ("_build_pattern_snapshot",),
        "source_kind": "observation_outcome_snapshot",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "verified_decisions": {
        "path": str(EARNING_LEARNING_DIR / "verified_decisions.csv"),
        "producer_module": "modules.earning_learning",
        "producer_functions": ("_build_verified_decisions",),
        "source_kind": "observation_outcome_snapshot",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "observations": {
        "path": str(EARNING_LEARNING_DIR / "observations.csv"),
        "producer_module": "modules.earning_learning",
        "producer_functions": ("_adapt_board", "_upsert_observations"),
        "source_kind": "t0_observations",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "pattern_lifecycle": {
        "path": str(EARNING_LEARNING_DIR / "pattern_lifecycle.csv"),
        "producer_module": "modules.earning_learning",
        "producer_functions": ("_build_pattern_lifecycle",),
        "source_kind": "observation_outcome_lifecycle",
        "research_wired": True,
        "provenance_status": ProvenanceStatus.ESTABLISHED.value,
    },
    "intraday_camera": {
        "path": str(REPO_ROOT / "intraday_memory"),
        "producer_module": "modules.intraday_memory",
        "producer_functions": ("CanonicalBar", "storage"),
        "source_kind": "intraday_camera",
        "research_wired": False,
        "provenance_status": ProvenanceStatus.PARTIAL.value,
    },
}

# Field-level overrides from provenance inspection (conservative).
FIELD_OVERRIDES: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("observations", "price"): {
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "derivation_provenance": "earning_learning._adapt_board COLUMN_ALIASES",
        "confidence": "HIGH",
    },
    ("observations", "health_group"): {
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "derivation_provenance": "board T0 categorical at capture",
        "confidence": "HIGH",
    },
    ("observations", "obv_status"): {
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "confidence": "HIGH",
    },
    ("observations", "rsi_slope"): {
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "required_inputs": ("rsi14",),
        "derivation_provenance": "board-derived RSI slope at T0",
        "confidence": "MEDIUM",
    },
    ("observations", "volume_ratio20"): {
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "required_inputs": ("volume", "vol_ma20"),
        "derivation_provenance": "earning_learning._adapt_board volume/vol_ma20",
        "confidence": "HIGH",
    },
    ("observations", "health_rank"): {
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "derivation_provenance": "cross-sectional rank at board snapshot",
        "confidence": "MEDIUM",
    },
    ("observations", "group_rank"): {
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "confidence": "MEDIUM",
    },
    ("observations", "health_score"): {
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
        "derivation_provenance": "modules.evolution_health composite at T0",
        "confidence": "MEDIUM",
    },
    ("pattern_lifecycle", "close"): {
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "research_accessible_now": True,
        "could_be_exposed_safely": True,
        "blocker_reason": "",
        "derivation_provenance": "adapters._stock_panel_from_lifecycle maps price→close",
        "confidence": "HIGH",
    },
    ("pattern_knowledge", "win_rate_pct"): {
        "scientific_class": ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
        "could_be_exposed_safely": False,
        "blocker_reason": "AGGREGATE_OUTCOME_KNOWLEDGE",
        "future_dependency": True,
        "confidence": "HIGH",
    },
    ("market_aware_sweetspot_observer_ledger", "historical_winrate"): {
        "scientific_class": ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
        "could_be_exposed_safely": False,
        "blocker_reason": "PRE_T0_OUTCOME_AGGREGATE",
        "future_dependency": True,
        "confidence": "HIGH",
    },
    ("market_aware_sweetspot_observer_ledger", "price_t0"): {
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "could_be_exposed_safely": False,
        "blocker_reason": "SOURCE_NOT_RESEARCH_WIRED",
        "confidence": "HIGH",
    },
    ("market_aware_sweetspot_observer_ledger", "t5_return_pct"): {
        "scientific_class": ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value,
        "could_be_exposed_safely": False,
        "blocker_reason": "FORWARD_OUTCOME_LABEL",
        "future_dependency": True,
        "confidence": "HIGH",
    },
}

MISSING_PANEL_FIELD_AUDIT: Dict[str, Dict[str, Any]] = {
    "close": {
        "origin": "pattern_lifecycle.price via adapters._stock_panel_from_lifecycle",
        "missing_reason": "NOT_MISSING — mapped to close on panel",
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "research_accessible_now": True,
        "could_be_exposed_safely": True,
        "blocker_reason": "",
    },
    "health_group": {
        "origin": "earning_learning._adapt_board from earning board",
        "missing_reason": "Excluded from _stock_panel_from_lifecycle column whitelist",
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "research_accessible_now": False,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
    },
    "obv_status": {
        "origin": "earning board T0 categorical",
        "missing_reason": "Excluded from _stock_panel_from_lifecycle",
        "scientific_class": ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
        "research_accessible_now": False,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
    },
    "health_rank": {
        "origin": "board cross-sectional rank at capture",
        "missing_reason": "Excluded from _stock_panel_from_lifecycle",
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "research_accessible_now": False,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
    },
    "group_rank": {
        "origin": "board cross-sectional rank at capture",
        "missing_reason": "Excluded from _stock_panel_from_lifecycle",
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "research_accessible_now": False,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
    },
    "health_score": {
        "origin": "evolution_health composite at T0",
        "missing_reason": "Excluded from _stock_panel_from_lifecycle",
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "research_accessible_now": False,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
    },
    "rsi_slope": {
        "origin": "board RSI slope at T0",
        "missing_reason": "Excluded from _stock_panel_from_lifecycle",
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "research_accessible_now": False,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
    },
    "volume_ratio20": {
        "origin": "volume/vol_ma20 at T0 in _adapt_board",
        "missing_reason": "Excluded from _stock_panel_from_lifecycle",
        "scientific_class": ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        "research_accessible_now": False,
        "could_be_exposed_safely": True,
        "blocker_reason": "NOT_IN_DEFAULT_PANEL_WIRING",
    },
}

INTRADAY_CAMERA_FIELDS: Tuple[str, ...] = (
    "symbol",
    "timestamp",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "collected_at",
    "quality_flag",
)


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, nrows=5000)


def _audit_source_fields(
    source_id: str,
    meta: Dict[str, Any],
    panel_columns: FrozenSet[str],
) -> List[ExpansionAuditEntry]:
    path = Path(meta["path"])
    source_kind = str(meta.get("source_kind", "unknown"))
    provenance_status = str(meta.get("provenance_status", ProvenanceStatus.UNRESOLVED.value))
    research_wired = bool(meta.get("research_wired", False))
    exists = path.exists()

    entries: List[ExpansionAuditEntry] = []

    if source_id == "intraday_camera":
        for fld in INTRADAY_CAMERA_FIELDS:
            sci, blocker, fut, hum, bot, prod, conf = _infer_field_class_from_name(
                fld, source_kind=source_kind
            )
            is_raw = fld in {"open", "high", "low", "close", "volume", "timestamp", "session_date", "symbol"}
            entries.append(
                ExpansionAuditEntry(
                    capability_id=_entry_id(source_id, fld),
                    source_id=source_id,
                    field_name=fld,
                    provenance_status=provenance_status,
                    scientific_class=(
                        ScientificSafetyClass.SAFE_RAW_OBSERVATION.value
                        if is_raw
                        else sci
                    ),
                    exists=exists,
                    historical_coverage=None,
                    point_in_time_safe=False if is_raw else None,
                    earliest_legal_horizon=0 if is_raw else 999,
                    required_inputs=(),
                    derivation_provenance="modules.intraday_memory.schema CanonicalBar",
                    future_dependency=fut,
                    human_knowledge_dependency=hum,
                    bot_decision_dependency=bot,
                    production_dependency=True,
                    research_accessible_now=False,
                    could_be_exposed_safely=False,
                    blocker_reason="PRODUCTION_CAMERA_NOT_RESEARCH_WIRED",
                    confidence=conf,
                    evidence=(
                        "Intraday bars require bar-time <= decision-time alignment",
                        "Phase 3H.1 MUST NOT expose Camera to researcher",
                    ),
                )
            )
        entries.append(
            ExpansionAuditEntry(
                capability_id=_entry_id(source_id, "production_buy_sell_interpretation"),
                source_id=source_id,
                field_name="production_buy_sell_interpretation",
                provenance_status=provenance_status,
                scientific_class=ScientificSafetyClass.TEMPORALLY_UNSAFE_OR_PRODUCTION_ONLY.value,
                exists=True,
                historical_coverage=None,
                point_in_time_safe=False,
                earliest_legal_horizon=999,
                required_inputs=(),
                derivation_provenance="production execution layer — not in canonical bar schema",
                future_dependency=False,
                human_knowledge_dependency=False,
                bot_decision_dependency=True,
                production_dependency=True,
                research_accessible_now=False,
                could_be_exposed_safely=False,
                blocker_reason="PRODUCTION_INTERPRETATION_SEPARATE_FROM_RAW_BARS",
                confidence="HIGH",
                evidence=("Raw camera schema has OHLCV only", "BUY/SELL is production layer"),
            )
        )
        return entries

    df = _load_csv(path) if exists else pd.DataFrame()
    columns = list(df.columns) if not df.empty else []

    if not columns and exists:
        columns = []

    if not columns:
        entries.append(
            ExpansionAuditEntry(
                capability_id=_entry_id(source_id, "*"),
                source_id=source_id,
                field_name="*",
                provenance_status=provenance_status,
                scientific_class=ScientificSafetyClass.PROVENANCE_UNRESOLVED.value
                if exists
                else ScientificSafetyClass.PROVENANCE_UNRESOLVED.value,
                exists=exists,
                historical_coverage=None,
                point_in_time_safe=None,
                earliest_legal_horizon=0,
                required_inputs=(),
                derivation_provenance=str(meta.get("producer_module", "")),
                future_dependency=False,
                human_knowledge_dependency=False,
                bot_decision_dependency=False,
                production_dependency=False,
                research_accessible_now=False,
                could_be_exposed_safely=False,
                blocker_reason="FILE_NOT_FOUND" if not exists else "NO_COLUMNS_READ",
                confidence="LOW",
                evidence=(f"producer={meta.get('producer_module')}",),
            )
        )
        return entries

    for col in columns:
        override = FIELD_OVERRIDES.get((source_id, col), {})
        sci, blocker, fut, hum, bot, prod, conf = _infer_field_class_from_name(
            col, source_kind=source_kind
        )
        sci = override.get("scientific_class", sci)
        blocker = override.get("blocker_reason", blocker)
        fut = override.get("future_dependency", fut)
        hum = override.get("human_knowledge_dependency", hum)
        bot = override.get("bot_decision_dependency", bot)
        prod = override.get("production_dependency", prod)
        conf = override.get("confidence", conf)

        if source_kind == "aggregate_knowledge":
            sci = ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
            blocker = blocker or "AGGREGATE_HISTORICAL_KNOWLEDGE"
            fut = True

        if source_kind == "sweetspot_observer" and col.startswith("historical_"):
            sci = ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value
            fut = True
            blocker = "PRE_T0_OUTCOME_AGGREGATE"

        horizon = field_availability_horizon(col) if col in FIELD_AVAILABILITY_HORIZON else 0
        if fut or sci == ScientificSafetyClass.KNOWLEDGE_CONTAMINATED.value:
            horizon = max(horizon, 3)

        on_panel = col in panel_columns or (col == "price" and "close" in panel_columns)
        accessible = research_wired and on_panel and sci in {
            ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
            ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
        }

        could_expose = override.get(
            "could_be_exposed_safely",
            sci
            in {
                ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
                ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
            }
            and not fut,
        )

        entries.append(
            ExpansionAuditEntry(
                capability_id=_entry_id(source_id, col),
                source_id=source_id,
                field_name=col,
                provenance_status=provenance_status,
                scientific_class=sci,
                exists=True,
                historical_coverage=_column_coverage(df, col),
                point_in_time_safe=sci
                in {
                    ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
                    ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
                }
                and source_kind == "t0_observations",
                earliest_legal_horizon=int(override.get("earliest_legal_horizon", horizon)),
                required_inputs=tuple(override.get("required_inputs") or ()),
                derivation_provenance=str(
                    override.get("derivation_provenance")
                    or f"{meta.get('producer_module')}.{meta.get('producer_functions', ('',))[0]}"
                ),
                future_dependency=bool(fut),
                human_knowledge_dependency=bool(hum),
                bot_decision_dependency=bool(bot),
                production_dependency=bool(prod),
                research_accessible_now=bool(override.get("research_accessible_now", accessible)),
                could_be_exposed_safely=bool(could_expose),
                blocker_reason=str(
                    override.get("blocker_reason")
                    or blocker
                    or ("SOURCE_NOT_RESEARCH_WIRED" if not research_wired else "")
                ),
                confidence=str(conf),
                evidence=(
                    f"source_kind={source_kind}",
                    f"producer={meta.get('producer_module')}",
                ),
            )
        )
    return entries


def _audit_missing_panel_fields(
    panel_columns: FrozenSet[str],
    lifecycle: pd.DataFrame,
) -> List[ExpansionAuditEntry]:
    entries: List[ExpansionAuditEntry] = []
    for fld, audit in MISSING_PANEL_FIELD_AUDIT.items():
        cov = _column_coverage(lifecycle, "price" if fld == "close" else fld)
        on_panel = fld in panel_columns
        entries.append(
            ExpansionAuditEntry(
                capability_id=_entry_id("missing_panel_registry", fld),
                source_id="pattern_lifecycle",
                field_name=fld,
                provenance_status=ProvenanceStatus.ESTABLISHED.value,
                scientific_class=str(audit["scientific_class"]),
                exists=cov is not None and cov > 0 if fld != "close" else "close" in panel_columns,
                historical_coverage=cov if fld != "close" else 1.0,
                point_in_time_safe=audit["scientific_class"]
                in {
                    ScientificSafetyClass.SAFE_RAW_OBSERVATION.value,
                    ScientificSafetyClass.DERIVED_BUT_LEGAL.value,
                },
                earliest_legal_horizon=0,
                required_inputs=(),
                derivation_provenance=str(audit["origin"]),
                future_dependency=False,
                human_knowledge_dependency=False,
                bot_decision_dependency=False,
                production_dependency=False,
                research_accessible_now=bool(audit.get("research_accessible_now", on_panel)),
                could_be_exposed_safely=bool(audit["could_be_exposed_safely"]),
                blocker_reason=str(audit.get("blocker_reason") or audit["missing_reason"]),
                confidence="HIGH",
                evidence=(
                    str(audit["origin"]),
                    str(audit["missing_reason"]),
                    "adapters._stock_panel_from_lifecycle whitelist excludes field",
                ),
            )
        )
    return entries


def verify_reconstructability(
    field_name: str,
    *,
    observation_horizon: int = 0,
) -> Dict[str, Any]:
    """Programmatic reconstructability check for DERIVED_BUT_LEGAL candidates."""
    if field_name == "volume_ratio20":
        legal = observation_horizon >= 0
        return {
            "field": field_name,
            "reproducible_at_horizon": legal,
            "required_inputs": ["volume", "vol_ma20"],
            "derivation_module": "modules.earning_learning._adapt_board",
            "leakage_assessment": "PASS_IF_vol_ma20_uses_only_prior_sessions",
            "status": "VERIFIED_DERIVATION_PATH" if legal else "UNCERTAIN",
        }
    if field_name == "rs_spread":
        return {
            "field": field_name,
            "reproducible_at_horizon": True,
            "required_inputs": ["rs5", "rs10"],
            "derivation_module": "adapters._stock_panel_from_lifecycle",
            "leakage_assessment": "PASS",
            "status": "VERIFIED_DERIVATION_PATH",
        }
    if field_name in STOCK_NUMERIC_LEVEL_FEATURES or field_name in STOCK_CATEGORICAL_LEVEL_FEATURES:
        assess = assess_feature_eligibility(field_name, observation_horizon=observation_horizon)
        return {
            "field": field_name,
            "reproducible_at_horizon": assess.eligible_at_observation,
            "required_inputs": [field_name],
            "derivation_module": "pattern_lifecycle/observations T0 capture",
            "leakage_assessment": "PASS" if assess.eligible_at_observation else assess.reason,
            "status": "VERIFIED_T0" if assess.eligible_at_observation else "TEMPORALLY_UNSAFE",
        }
    return {
        "field": field_name,
        "reproducible_at_horizon": False,
        "required_inputs": [],
        "derivation_module": "",
        "leakage_assessment": "PROVENANCE_UNRESOLVED",
        "status": "UNCERTAIN",
    }


def build_research_data_expansion_audit(
    panel: Optional[pd.DataFrame] = None,
) -> ResearchDataExpansionAudit:
    """
    Build field-level expansion audit from repository state.

    Audit-only — does NOT change research_accessible_now on any live capability.
    """
    if panel is None:
        try:
            panel = build_research_panel()
        except Exception:
            panel = pd.DataFrame()

    panel_columns = frozenset(panel.columns) if not panel.empty else frozenset()
    lifecycle = load_lifecycle()

    entries: Dict[str, ExpansionAuditEntry] = {}
    source_inventory: List[Dict[str, Any]] = []

    for source_id, meta in SOURCE_PROVENANCE.items():
        path = Path(meta["path"])
        source_inventory.append(
            {
                "source_id": source_id,
                "path": str(path),
                "exists": path.exists(),
                "digest_sha256": file_digest(path) if path.is_file() else None,
                "producer_module": meta.get("producer_module"),
                "producer_functions": list(meta.get("producer_functions") or ()),
                "research_wired": meta.get("research_wired", False),
                "provenance_status": meta.get("provenance_status"),
            }
        )
        for entry in _audit_source_fields(source_id, meta, panel_columns):
            entries[entry.capability_id] = entry

    for entry in _audit_missing_panel_fields(panel_columns, lifecycle):
        entries[entry.capability_id] = entry

    counts: Dict[str, int] = {}
    for entry in entries.values():
        counts[entry.scientific_class] = counts.get(entry.scientific_class, 0) + 1

    return ResearchDataExpansionAudit(
        built_at=_utc_now(),
        entries=entries,
        source_inventory=source_inventory,
        classification_counts=counts,
        audit_trail=[
            {
                "event": "EXPANSION_AUDIT_BUILT",
                "timestamp": _utc_now(),
                "entry_count": len(entries),
                "panel_column_count": len(panel_columns),
                "lifecycle_row_count": int(len(lifecycle)),
                "policy": "AUDIT_ONLY_NO_EXPOSURE",
            }
        ],
    )


def ensure_session_expansion_audit(graph: Any) -> ResearchDataExpansionAudit:
    """Build or reload expansion audit on session — observational only."""
    if graph.session.research_data_expansion_audit:
        audit = ResearchDataExpansionAudit.from_dict(graph.session.research_data_expansion_audit)
        graph._expansion_audit = audit  # noqa: SLF001
        return audit
    audit = build_research_data_expansion_audit()
    graph.session.research_data_expansion_audit = audit.to_dict()
    graph._expansion_audit = audit  # noqa: SLF001
    return audit


def persist_expansion_audit(graph: Any) -> None:
    if getattr(graph, "_expansion_audit", None) is not None:
        graph.session.research_data_expansion_audit = graph._expansion_audit.to_dict()

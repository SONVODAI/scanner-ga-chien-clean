"""
Panel exposure wiring — Phase 3H.2A design, Phase 3H.2B first controlled exposure.

Governance-approved optional columns are merged with CORE_STOCK_PANEL_FIELDS
when building the research panel. Only fields in the active wired manifest
are extracted from lifecycle persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

PANEL_EXPOSURE_DESIGN_VERSION = "research_panel_exposure_v2"

# Hard-coded core stock fields in adapters._stock_panel_from_lifecycle.
CORE_STOCK_PANEL_FIELDS: FrozenSet[str] = frozenset(
    {"close", "rs5", "rs10", "rsi14", "rs_spread"}
)

# Phase 3H.2A: empty manifest (door built, not opened).
DEFAULT_APPROVED_EXPOSURE_MANIFEST: FrozenSet[str] = frozenset()

# Phase 3H.2B: first and only controlled exposure field.
PHASE_3H2B_FIRST_CONTROLLED_FIELD = "rsi_slope"

# Optional columns requiring governance manifest wiring before panel inclusion.
GOVERNED_OPTIONAL_PANEL_COLUMNS: FrozenSet[str] = frozenset({PHASE_3H2B_FIRST_CONTROLLED_FIELD})


@dataclass(frozen=True)
class PanelExposureManifest:
    """Approved optional stock-level columns for panel wiring."""

    version: str = PANEL_EXPOSURE_DESIGN_VERSION
    approved_field_names: FrozenSet[str] = DEFAULT_APPROVED_EXPOSURE_MANIFEST
    wired_field_names: FrozenSet[str] = DEFAULT_APPROVED_EXPOSURE_MANIFEST

    def validate(self) -> Tuple[bool, str]:
        if not self.version:
            return False, "MISSING_MANIFEST_VERSION"
        invalid = self.wired_field_names - self.approved_field_names
        if invalid:
            return False, f"WIRED_NOT_APPROVED:{sorted(invalid)}"
        non_core_wired = self.wired_field_names - CORE_STOCK_PANEL_FIELDS
        for fld in non_core_wired:
            if not isinstance(fld, str) or not fld.strip():
                return False, "MALFORMED_FIELD_NAME"
        return True, ""

    def effective_stock_columns(self) -> FrozenSet[str]:
        ok, reason = self.validate()
        if not ok:
            raise ValueError(f"PanelExposureManifest invalid: {reason}")
        wired_optional = self.wired_field_names - CORE_STOCK_PANEL_FIELDS
        return CORE_STOCK_PANEL_FIELDS | wired_optional


def build_phase_3h2b_panel_manifest() -> PanelExposureManifest:
    """Explicit Phase 3H.2B manifest — rsi_slope only."""
    field = PHASE_3H2B_FIRST_CONTROLLED_FIELD
    names = frozenset({field})
    return PanelExposureManifest(
        version=PANEL_EXPOSURE_DESIGN_VERSION,
        approved_field_names=names,
        wired_field_names=names,
    )


def build_empty_panel_manifest() -> PanelExposureManifest:
    """Phase 3H.2A door-closed manifest for infrastructure tests."""
    return PanelExposureManifest()


def get_active_panel_exposure_manifest() -> PanelExposureManifest:
    """Active production manifest — Phase 3H.2B first controlled exposure."""
    return build_phase_3h2b_panel_manifest()


def resolve_effective_stock_columns(
    manifest: Optional[PanelExposureManifest] = None,
) -> FrozenSet[str]:
    m = manifest if manifest is not None else get_active_panel_exposure_manifest()
    return m.effective_stock_columns()


def columns_would_change_panel(
    manifest: PanelExposureManifest,
    baseline: Optional[FrozenSet[str]] = None,
) -> bool:
    base = baseline or CORE_STOCK_PANEL_FIELDS
    return resolve_effective_stock_columns(manifest) != base


def parse_panel_exposure_manifest(payload: Optional[dict]) -> PanelExposureManifest:
    if payload is None:
        return PanelExposureManifest()
    if not isinstance(payload, dict):
        raise ValueError("MALFORMED_EXPOSURE_MANIFEST: not a dict")
    version = str(payload.get("version") or PANEL_EXPOSURE_DESIGN_VERSION)
    approved = frozenset(str(x) for x in (payload.get("approved_field_names") or ()))
    wired = frozenset(str(x) for x in (payload.get("wired_field_names") or ()))
    manifest = PanelExposureManifest(
        version=version,
        approved_field_names=approved,
        wired_field_names=wired,
    )
    ok, reason = manifest.validate()
    if not ok:
        raise ValueError(f"MALFORMED_EXPOSURE_MANIFEST: {reason}")
    return manifest


def governed_wired_stock_columns(
    manifest: Optional[PanelExposureManifest] = None,
    *,
    contract_wired: Optional[FrozenSet[str]] = None,
) -> FrozenSet[str]:
    """
    Fail-closed resolver: optional columns must appear in both manifest and
    (when provided) live exposure contract wired set.
    """
    m = manifest if manifest is not None else get_active_panel_exposure_manifest()
    ok, reason = m.validate()
    if not ok:
        raise ValueError(f"MALFORMED_EXPOSURE_MANIFEST: {reason}")
    optional = m.wired_field_names - CORE_STOCK_PANEL_FIELDS
    if contract_wired is not None:
        optional = optional & contract_wired
    return CORE_STOCK_PANEL_FIELDS | optional

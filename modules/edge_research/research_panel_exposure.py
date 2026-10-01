"""
Phase 3H.2A — Panel exposure wiring design (door not opened).

Defines canonical core panel fields and the approved-exposure manifest
mechanism. In 3H.2A the manifest is always empty — build_research_panel()
output must remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Optional, Sequence, Tuple

PANEL_EXPOSURE_DESIGN_VERSION = "research_panel_exposure_v1"

# Hard-coded core stock fields currently extracted in adapters._stock_panel_from_lifecycle.
CORE_STOCK_PANEL_FIELDS: FrozenSet[str] = frozenset(
    {"close", "rs5", "rs10", "rsi14", "rs_spread"}
)

# Phase 3H.2A: intentionally empty — no approved+wired optional columns.
DEFAULT_APPROVED_EXPOSURE_MANIFEST: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class PanelExposureManifest:
    """Approved optional stock-level columns for panel wiring (3H.2B+)."""

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
        """
        Resolve stock-level columns for panel builder.

        Phase 3H.2A: returns CORE only because wired manifest is empty.
        """
        ok, reason = self.validate()
        if not ok:
            raise ValueError(f"PanelExposureManifest invalid: {reason}")
        wired_optional = self.wired_field_names - CORE_STOCK_PANEL_FIELDS
        return CORE_STOCK_PANEL_FIELDS | wired_optional


def resolve_effective_stock_columns(
    manifest: Optional[PanelExposureManifest] = None,
) -> FrozenSet[str]:
    """Future-safe resolver — 3H.2A output equals CORE_STOCK_PANEL_FIELDS only."""
    m = manifest or PanelExposureManifest()
    return m.effective_stock_columns()


def columns_would_change_panel(
    manifest: PanelExposureManifest,
    baseline: Optional[FrozenSet[str]] = None,
) -> bool:
    """True if manifest would alter stock column set vs baseline core."""
    base = baseline or CORE_STOCK_PANEL_FIELDS
    return resolve_effective_stock_columns(manifest) != base


def parse_panel_exposure_manifest(payload: Optional[dict]) -> PanelExposureManifest:
    """Parse manifest from session dict — fail-closed on malformed input."""
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

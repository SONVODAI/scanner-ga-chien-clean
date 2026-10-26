"""
Phase 3I.3 — Build and pre-register expanded real historical panel.

Deterministic assembly from read-only sources. No synthetic values.
Does NOT modify the OPR generator.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
JUNE_OOS = REPO / "research_exports" / "edge_oos_20260601_20260630.csv"
PANEL_OUT = REPO / "benchmarks" / "bb_prop_01" / "zone_b_blind_panel" / "expanded_panel_v3i3.csv"
SPEC_OUT = REPO / "diagnostics" / "phase_3i3_real_evidence_expansion" / "artifacts" / "01_expanded_panel_specification.json"

# OPR-required fields (frozen 3I.2 detector semantics)
OPR_REQUIRED_COLUMNS = ("trade_date", "symbol", "rs_spread", "t5_return")
MIN_SYMBOLS_PER_DATE = 15
PANEL_CUTOFF = "2026-08-17"  # frozen before generator run — no future leakage


@dataclass(frozen=True)
class PanelBuildResult:
    panel: pd.DataFrame
    specification: Dict[str, Any]
    fingerprint: str


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_df(df: pd.DataFrame, columns: Tuple[str, ...]) -> str:
    subset = df[list(columns)].copy()
    subset = subset.sort_values(list(columns)).reset_index(drop=True)
    payload = subset.to_csv(index=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _load_june_oos() -> pd.DataFrame:
    """Normalize June 2026 OOS export to OPR-compatible schema."""
    if not JUNE_OOS.exists():
        return pd.DataFrame()
    raw = pd.read_csv(JUNE_OOS)
    if raw.empty:
        return pd.DataFrame()
    df = pd.DataFrame()
    df["trade_date"] = raw["date"].astype(str)
    df["symbol"] = raw["symbol"].astype(str)
    df["rs5"] = pd.to_numeric(raw["rs5"], errors="coerce")
    df["rs10"] = pd.to_numeric(raw["rs10"], errors="coerce")
    df["rsi14"] = pd.to_numeric(raw.get("rsi14"), errors="coerce")
    df["close"] = pd.to_numeric(raw.get("close"), errors="coerce")
    df["rs_spread"] = df["rs5"] - df["rs10"]
    df["t3_return"] = pd.to_numeric(raw.get("t3_return"), errors="coerce")
    df["t5_return"] = pd.to_numeric(raw.get("t5_return"), errors="coerce")
    df["t10_return"] = pd.to_numeric(raw.get("t10_return"), errors="coerce")
    df["outcome_source"] = "research_exports_edge_oos"
    df["outcome_missing_reason"] = np.where(df["t5_return"].isna(), "missing_in_source", "")
    return df


def _load_july_aug_panel() -> pd.DataFrame:
    """Rebuild Jul-Aug panel from canonical adapters (read-only)."""
    from modules.edge_research.adapters import build_research_panel

    panel = build_research_panel(end=PANEL_CUTOFF)
    panel["trade_date"] = panel["trade_date"].astype(str)
    return panel


def _missingness_audit(df: pd.DataFrame) -> Dict[str, Any]:
    n = len(df)
    audit = {"row_count": n, "fields": {}}
    for col in OPR_REQUIRED_COLUMNS:
        non_null = int(df[col].notna().sum()) if col in df.columns else 0
        audit["fields"][col] = {
            "non_null": non_null,
            "coverage": round(non_null / n, 4) if n else 0.0,
        }
    for col in ("t3_return", "t10_return"):
        if col in df.columns:
            non_null = int(df[col].notna().sum())
            audit["fields"][col] = {
                "non_null": non_null,
                "coverage": round(non_null / n, 4) if n else 0.0,
            }
    return audit


def _schema_consistency_audit(june: pd.DataFrame, july_aug: pd.DataFrame) -> Dict[str, Any]:
    issues: List[str] = []
    if not june.empty and not july_aug.empty:
        overlap = set(june["trade_date"].unique()) & set(july_aug["trade_date"].unique())
        if overlap:
            issues.append(f"overlap_dates_deduped: {sorted(overlap)}")
    return {
        "june_rows": len(june),
        "july_aug_rows": len(july_aug),
        "overlap_dates": sorted(set(june["trade_date"].unique()) & set(july_aug["trade_date"].unique()))
        if not june.empty and not july_aug.empty
        else [],
        "dedup_policy": "keep_last_on_trade_date_symbol",
        "issues": issues,
    }


def build_expanded_panel(*, write: bool = True) -> PanelBuildResult:
    """
    Assemble longest real comparable panel for OPR dispersion primitive.

    Sources (chronological):
    1. research_exports/edge_oos_20260601_20260630.csv (June 2026)
    2. build_research_panel(end=2026-08-17) (July-Aug 2026)
    """
    june = _load_june_oos()
    july_aug = _load_july_aug_panel()

    schema_audit = _schema_consistency_audit(june, july_aug)

    parts = []
    if not june.empty:
        parts.append(june)
    if not july_aug.empty:
        parts.append(july_aug)

    if not parts:
        raise RuntimeError("No real panel sources available")

    combined = pd.concat(parts, ignore_index=True)
    combined["trade_date"] = combined["trade_date"].astype(str)
    combined = combined[combined["trade_date"] <= PANEL_CUTOFF]

    # Dedupe — July-Aug canonical takes precedence on overlap
    combined = combined.sort_values(["trade_date", "symbol"]).drop_duplicates(
        subset=["trade_date", "symbol"], keep="last"
    )

    # Filter: OPR-required fields present
    combined = combined.dropna(subset=["rs_spread"])
    per_date = combined.groupby("trade_date")["symbol"].count()
    valid_dates = per_date[per_date >= MIN_SYMBOLS_PER_DATE].index
    combined = combined[combined["trade_date"].isin(valid_dates)]

    dates = sorted(combined["trade_date"].unique())
    missingness = _missingness_audit(combined)

    fingerprint = _sha256_df(combined, OPR_REQUIRED_COLUMNS)

    spec: Dict[str, Any] = {
        "phase": "3I.3",
        "panel_id": "expanded_panel_v3i3",
        "frozen_before_generator_run": True,
        "date_range": {"start": dates[0], "end": dates[-1]} if dates else {},
        "total_dates": len(dates),
        "total_rows": len(combined),
        "distinct_symbols": int(combined["symbol"].nunique()),
        "universe_rule": "symbols present in source CSVs with per-date cross-section >= 15",
        "required_columns": list(OPR_REQUIRED_COLUMNS),
        "cutoff_rule": f"trade_date <= {PANEL_CUTOFF}",
        "missingness_policy": "drop rows with null rs_spread; require >=15 symbols per date",
        "minimum_cross_sectional_sample": MIN_SYMBOLS_PER_DATE,
        "baseline_construction": "historical self-baseline from prior trade_dates cross-sectional std",
        "eligible_observation_definition": "date with >=15 symbols, non-zero rs_spread std, valid t5_return cohort",
        "sources": [
            {"path": str(JUNE_OOS.relative_to(REPO)), "rows": len(june)},
            {"path": "build_research_panel(end=2026-08-17)", "rows": len(july_aug)},
        ],
        "schema_consistency_audit": schema_audit,
        "missingness_audit": missingness,
        "panel_fingerprint_sha256": fingerprint,
        "no_synthetic_rows": True,
        "no_future_leakage": True,
    }

    if write:
        PANEL_OUT.parent.mkdir(parents=True, exist_ok=True)
        SPEC_OUT.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(PANEL_OUT, index=False)
        spec["panel_csv_path"] = str(PANEL_OUT.relative_to(REPO))
        spec["panel_csv_sha256"] = _sha256_file(PANEL_OUT)
        (SPEC_OUT).write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")

    return PanelBuildResult(panel=combined, specification=spec, fingerprint=fingerprint)


if __name__ == "__main__":
    result = build_expanded_panel()
    print(json.dumps(result.specification, indent=2))

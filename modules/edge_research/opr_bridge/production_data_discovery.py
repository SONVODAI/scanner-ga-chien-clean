"""
Phase 3K.5 — Production data source discovery (read-only audit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.edge_research.adapters import (
    BUY_ELITE_HISTORY_PATH,
    EARNING_LEARNING_DIR,
    MARKET_T0_SNAPSHOT_PATH,
    OUTCOMES_PATH,
    PATTERN_HISTORY_PATH,
    REPO_ROOT,
    build_research_panel,
    load_lifecycle,
)

PRODUCTION_DATA_DISCOVERY_VERSION = "production_data_discovery_v1_3k5"


def _file_audit(path: Path, *, producer: str, cadence: str, required_cols: List[str]) -> Dict[str, Any]:
    exists = path.exists()
    row: Dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "producer": producer,
        "expected_cadence": cadence,
        "required_columns": required_cols,
        "local": True,
    }
    if not exists:
        row["status"] = "MISSING"
        row["latest_trade_date"] = None
        row["row_count"] = 0
        return row
    try:
        df = pd.read_csv(path, low_memory=False, nrows=0)
        row["columns_present"] = list(df.columns)
        full = pd.read_csv(path, low_memory=False)
        row["row_count"] = len(full)
        date_col = None
        for c in ("trade_date", "date", "entry_date"):
            if c in full.columns:
                date_col = c
                break
        if date_col:
            row["latest_trade_date"] = str(pd.to_datetime(full[date_col]).max().date())
        else:
            row["latest_trade_date"] = None
        row["status"] = "AVAILABLE"
        missing_cols = [c for c in required_cols if c not in full.columns]
        if missing_cols:
            row["status"] = "INCOMPLETE_COLUMNS"
            row["missing_columns"] = missing_cols
    except Exception as exc:
        row["status"] = "READ_ERROR"
        row["error"] = str(exc)
    return row


def discover_production_data_sources(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Identify exact production data sources for 3K daily runner.
    FAIL READINESS if primary stock panel source is ambiguous or missing.
    """
    repo = repo_root or REPO_ROOT
    sources = {
        "pattern_lifecycle": _file_audit(
            EARNING_LEARNING_DIR / "pattern_lifecycle.csv",
            producer="earning_learning / lifecycle pipeline",
            cadence="daily post-EOD",
            required_cols=["trade_date", "symbol"],
        ),
        "market_t0_snapshot": _file_audit(
            MARKET_T0_SNAPSHOT_PATH,
            producer="market_t0_capture / earning pipeline",
            cadence="daily post-EOD >= 18:00 VN",
            required_cols=["trade_date", "market_real"],
        ),
        "outcomes": _file_audit(
            OUTCOMES_PATH,
            producer="earning_learning outcomes",
            cadence="daily",
            required_cols=["symbol", "horizon", "return_pct"],
        ),
        "pattern_history_fallback": _file_audit(
            PATTERN_HISTORY_PATH,
            producer="pattern_history (fallback market)",
            cadence="historical",
            required_cols=["date", "market_real"],
        ),
        "t0_observation_freeze": _file_audit(
            EARNING_LEARNING_DIR / "t0_observation_freeze.csv",
            producer="market_t0_capture freeze pipeline",
            cadence="daily post-18:00 VN",
            required_cols=["trade_date"],
        ),
        "buy_elite_history_fallback": _file_audit(
            BUY_ELITE_HISTORY_PATH,
            producer="buy_elite_learning_history (fallback market)",
            cadence="historical",
            required_cols=["date", "market_real"],
        ),
    }
    sources["t0_observation_freeze"]["wired_to_readiness_gate"] = False

    panel = build_research_panel()
    panel_info: Dict[str, Any] = {
        "builder": "modules.edge_research.adapters.build_research_panel",
        "primary_stock_source": "pattern_lifecycle.csv",
        "market_enrichment": "market_t0_snapshot.csv + fallbacks",
        "forward_labels": "outcomes.csv -> t3/t5/t10_return",
        "empty": panel.empty,
    }
    if not panel.empty:
        panel_info["latest_trade_date"] = str(pd.to_datetime(panel["trade_date"]).max().date())
        panel_info["earliest_trade_date"] = str(pd.to_datetime(panel["trade_date"]).min().date())
        panel_info["session_count"] = panel["trade_date"].nunique()
        panel_info["columns"] = list(panel.columns)

    lifecycle = load_lifecycle()
    ambiguous = panel.empty and lifecycle.empty
    primary_missing = sources["pattern_lifecycle"]["status"] in ("MISSING", "READ_ERROR")

    return {
        "version": PRODUCTION_DATA_DISCOVERY_VERSION,
        "repo_root": str(repo),
        "data_root": str(EARNING_LEARNING_DIR),
        "sources": sources,
        "panel": panel_info,
        "eod_session_complete_signal": {
            "documented": "source_max_trade_date >= target AND rows exist for target",
            "t0_freeze_wired": False,
            "post_eod_18h_vn_enforced": False,
            "note": "EOD completeness is row-presence based; 18:00 VN freeze not wired to readiness gate",
        },
        "readiness": {
            "sources_identified": not ambiguous,
            "primary_panel_available": not primary_missing and not panel.empty,
            "ambiguous_source": ambiguous,
            "fail_if_ambiguous": ambiguous or primary_missing,
        },
    }

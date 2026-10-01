"""
Phase 3I.3 observational accounting — diagnostics only.

Uses frozen 3I.2 detector functions without modification.
Reports opportunity vs synthesis failure distinction.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

import pandas as pd

from modules.edge_research.opr_bridge.constants import MIN_DATES_FOR_BASELINE
from modules.edge_research.opr_bridge.evidence_ingest import (
    find_eligible_focal_dates,
    ingest_dispersion_evidence,
)
from modules.edge_research.opr_bridge.surprise_detector import assess_dispersion_surprise


def compute_observational_accounting(
    panel: pd.DataFrame,
    *,
    data_cutoff_date: str,
) -> Dict[str, Any]:
    """
    Pre-register observational stats before proposition audit / hidden eval.
    """
    dates = sorted(panel["trade_date"].astype(str).unique())
    cutoff = str(data_cutoff_date)
    panel_dates = [d for d in dates if d <= cutoff]

    eligible = find_eligible_focal_dates(panel, data_cutoff_date=cutoff)
    baseline_ready: List[str] = []
    anomaly_triggers: List[str] = []
    trigger_types: Counter = Counter()
    silences_by_reason: Counter = Counter()
    evidence_failures = 0

    for focal in eligible:
        evidence = ingest_dispersion_evidence(panel, focal_date=focal, data_cutoff_date=cutoff)
        if evidence is None:
            evidence_failures += 1
            silences_by_reason["INSUFFICIENT_GROUNDING"] += 1
            continue

        hist_len = len(evidence.historical_dispersion_series)
        if hist_len >= MIN_DATES_FOR_BASELINE:
            baseline_ready.append(focal)

        surprise = assess_dispersion_surprise(evidence)
        if not surprise.is_surprising:
            silences_by_reason[surprise.reason_code] += 1
        else:
            anomaly_triggers.append(focal)
            trigger_types[surprise.reason_code] += 1

    return {
        "total_dates_in_panel": len(panel_dates),
        "eligible_dates": len(eligible),
        "baseline_ready_dates": len(baseline_ready),
        "baseline_ready_date_list": baseline_ready,
        "anomaly_trigger_dates": len(anomaly_triggers),
        "anomaly_trigger_date_list": anomaly_triggers,
        "trigger_type_distribution": dict(trigger_types),
        "silence_reason_distribution": dict(silences_by_reason),
        "evidence_quality_failures": evidence_failures,
        "min_dates_for_baseline": MIN_DATES_FOR_BASELINE,
    }

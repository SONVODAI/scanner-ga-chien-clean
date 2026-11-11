"""Display formatting for Guardian Research forward returns.

Stored returns are percentage points. These tests only check the display
strings and that the source numbers and files stay as they were.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from research.guardian_research.outcomes import HORIZON_LABELS
from research.guardian_research.panel import (
    _forward_table,
    _outcome_comparison,
    _outcome_quality,
    _outcome_symbols,
    format_forward_return,
)

ROOT = Path(__file__).resolve().parents[1]
MISSING = "—"


def test_forward_return_display_uses_two_decimals_without_rescaling():
    assert format_forward_return(0.7371) == "+0.74%"
    assert format_forward_return(0.737101) == "+0.74%"
    assert format_forward_return(-1.7021) == "-1.70%"
    assert format_forward_return(-1.702128) == "-1.70%"
    assert format_forward_return(0) == "0.00%"
    assert format_forward_return(0.0) == "0.00%"
    assert format_forward_return(-0.0) == "0.00%"
    assert format_forward_return(0.004) == "0.00%"
    assert format_forward_return(-0.004) == "0.00%"
    assert format_forward_return(10) == "+10.00%"
    assert format_forward_return(0.1) == "+0.10%"
    assert format_forward_return(None) == MISSING
    assert format_forward_return(float("nan")) == MISSING
    assert format_forward_return(float("inf")) == MISSING
    assert format_forward_return(True) == MISSING
    assert format_forward_return("0.7371") == MISSING


def test_tables_format_every_horizon_and_leave_counts_and_numbers_alone():
    values = {
        "T+1": 0.7371,
        "T+3": -1.7021,
        "T+5": 0.0,
        "T+10": None,
        "T+15": 10,
        "T+20": 0.004,
    }
    expected = {
        "T+1": "+0.74%",
        "T+3": "-1.70%",
        "T+5": "0.00%",
        "T+10": MISSING,
        "T+15": "+10.00%",
        "T+20": "0.00%",
    }
    view = _view(values)
    original = copy.deepcopy(view)

    symbols = _outcome_symbols(view)
    comparison = _outcome_comparison(view)
    forward = _forward_table(view)
    quality = _outcome_quality(view)

    assert view == original
    shown = symbols.iloc[0]
    blank = symbols.iloc[1]
    assert list(HORIZON_LABELS) == ["T+1", "T+3", "T+5", "T+10", "T+15", "T+20"]
    for label in HORIZON_LABELS:
        assert shown[label] == expected[label]
        assert shown[f"{label} status"] == ("APPROX_AVAILABLE" if values[label] is not None else "NOT_YET_OBSERVED")
        assert blank[label] == MISSING
        assert view["rows"][0]["horizons"][label]["return_pct"] == values[label]
    assert shown["T+10"] != "0.00%"
    assert shown["Classification"] == "HOLD"
    assert math.isclose(view["rows"][0]["horizons"]["T+1"]["return_pct"], 0.7371)

    hold = comparison[(comparison["Classification"] == "HOLD") & (comparison["Horizon"] == "T+1")].iloc[0]
    assert hold["Average"] == "+0.74%"
    assert hold["Median"] == "-1.70%"
    assert hold["Evidence"] == "MEASURED"
    assert hold["Sample"] == 2
    assert hold["Positive"] == "50.0%"
    assert hold["Close-path avg"] == "-0.50%"
    missing = comparison[(comparison["Classification"] == "HOLD") & (comparison["Horizon"] == "T+10")].iloc[0]
    assert missing["Average"] == MISSING
    assert missing["Median"] == MISSING
    assert missing["Sample"] == 0
    assert missing["Evidence"] == "INSUFFICIENT_EVIDENCE"

    forward_row = forward[(forward["Classification"] == "HOLD") & (forward["Horizon"] == "T+5")].iloc[0]
    assert forward_row["Average"] == "0.00%"
    assert forward_row["Median"] == "+10.00%"
    assert forward_row["Downside p10"] == "-1.70%"
    assert forward_row["Sample"] == 2
    assert forward_row["Rise >3%"] == "50.0%"
    assert forward_row["Loss rate"] == "0.0%"
    tiny = forward[(forward["Classification"] == "HOLD") & (forward["Horizon"] == "T+20")].iloc[0]
    assert tiny["Average"] == "0.00%"
    assert tiny["Median"] == MISSING
    assert tiny["Downside p10"] == MISSING
    assert tiny["Sample"] == 2
    absent = forward[(forward["Classification"] == "HOLD") & (forward["Horizon"] == "T+10")].iloc[0]
    assert absent["Average"] == MISSING
    assert absent["Median"] == MISSING
    assert absent["Downside p10"] == MISSING
    assert absent["Sample"] == 0
    rally = forward[forward["Classification"] == "SELL missed rally"].iloc[0]
    assert rally["Average"] == MISSING
    assert rally["Sample"] == 1

    mature = quality[(quality["Classification"] == "HOLD") & (quality["Horizon"] == "T+1")].iloc[0]
    assert mature["Mature sample"] == 2
    assert mature["Not yet"] == 0
    assert mature["Evidence"] == "MEASURED"


def test_shipped_forward_files_keep_their_numbers_when_displayed():
    targets = [
        ROOT / "research/guardian_research/outcomes.json",
        ROOT / "research/guardian_research/performance_view.json",
        ROOT / "data/guardian_research/sessions/2026-11-06.json",
    ]
    before = {path: path.read_bytes() for path in targets}
    outcomes = json.loads(before[targets[0]])
    performance = json.loads(before[targets[1]])
    snapshot = json.loads(before[targets[2]])
    outcomes_copy = copy.deepcopy(outcomes)
    performance_copy = copy.deepcopy(performance)

    symbols = _outcome_symbols(outcomes)
    comparison = _outcome_comparison(outcomes)
    forward = _forward_table(performance)

    assert outcomes == outcomes_copy
    assert performance == performance_copy
    acb = _symbol(symbols, "ACB")
    agr = _symbol(symbols, "AGR")
    bvh = _symbol(symbols, "BVH")
    assert acb["T+1"] == "+0.74%"
    assert acb["T+1 status"] == "APPROX_AVAILABLE"
    assert acb["T+3"] == MISSING
    assert agr["T+1"] == "-1.70%"
    assert bvh["T+1"] == "0.00%"
    assert _stored(outcomes, "ACB") == 0.737101
    assert _stored(outcomes, "AGR") == -1.702128
    assert _stored(outcomes, "BVH") == 0.0

    hold_t1 = comparison[(comparison["Classification"] == "HOLD") & (comparison["Horizon"] == "T+1")].iloc[0]
    hold_t10 = comparison[(comparison["Classification"] == "HOLD") & (comparison["Horizon"] == "T+10")].iloc[0]
    assert hold_t1["Average"] == "-0.76%"
    assert hold_t1["Median"] == "-0.80%"
    assert hold_t1["Sample"] == 57
    assert hold_t1["Evidence"] == "MEASURED"
    assert hold_t10["Average"] == MISSING
    assert hold_t10["Sample"] == 0
    assert hold_t10["Evidence"] == "INSUFFICIENT_EVIDENCE"

    forward_t1 = forward[(forward["Classification"] == "HOLD") & (forward["Horizon"] == "T+1")].iloc[0]
    forward_t3 = forward[(forward["Classification"] == "HOLD") & (forward["Horizon"] == "T+3")].iloc[0]
    forward_t10 = forward[(forward["Classification"] == "HOLD") & (forward["Horizon"] == "T+10")].iloc[0]
    assert forward_t1["Average"] == "-1.12%"
    assert forward_t1["Median"] == "-0.70%"
    assert forward_t1["Downside p10"] == "-4.71%"
    assert forward_t1["Sample"] == 16
    assert forward_t3["Average"] == "+1.57%"
    assert forward_t3["Median"] == "+1.00%"
    assert forward_t3["Downside p10"] == "-2.10%"
    assert forward_t10["Average"] == MISSING
    assert forward_t10["Sample"] == 0
    sealed = snapshot["rows"][0]["forward"]["horizons"]["T+1"]
    assert sealed["return_pct"] is None
    assert sealed["status"] == "PENDING"
    assert snapshot["session"] == "2026-11-06"
    for path, raw in before.items():
        assert path.read_bytes() == raw


def _view(values: dict) -> dict:
    horizons = {}
    for label in HORIZON_LABELS:
        value = values[label]
        horizons[label] = {
            "status": "APPROX_AVAILABLE" if value is not None else "NOT_YET_OBSERVED",
            "return_pct": value,
            "included_in_primary": value is not None,
        }
    summary = {}
    for label in HORIZON_LABELS:
        value = values[label]
        summary[label] = {
            "evidence": "MEASURED" if value is not None else "INSUFFICIENT_EVIDENCE",
            "primary": 2 if value is not None else 0,
            "observations": 2,
            "immature": 0 if value is not None else 2,
            "missing": 0,
            "unmeasured": 0,
            "truncated": 0,
            "discontinuity": 0,
            "adverse_sample": 2 if value is not None else 0,
            "average_return_pct": value,
            "median_return_pct": values["T+3"] if label == "T+1" else (values["T+15"] if label == "T+5" else None),
            "downside_p10_pct": values["T+3"] if label == "T+5" else None,
            "positive_return_rate": 0.5 if value is not None else None,
            "win_rate_above_3pct": 0.5 if value is not None else None,
            "win_rate_above_5pct": None,
            "loss_rate": 0.0 if value is not None else None,
            "loss_rate_below_minus_3pct": None,
            "loss_rate_below_minus_5pct": None,
            "adverse_close_path_average_pct": -0.5 if value is not None else None,
            "adverse_close_path_worst_pct": None,
        }
    blank = {
        label: {"status": "NOT_MEASURED", "return_pct": None, "included_in_primary": False}
        for label in HORIZON_LABELS
    }
    return {
        "classifications": {"HOLD": {"horizons": summary}},
        "missed_rally": {"horizons": {"T+1": {"sample": 1, "above_3pct": None, "above_5pct": None}}},
        "rows": [
            {
                "session": "2026-11-06",
                "symbol": "HPG",
                "classification": "HOLD",
                "tenure": "PERSISTENT",
                "live_adjusted_input": False,
                "horizons": horizons,
            },
            {
                "session": "2026-11-06",
                "symbol": "F88",
                "classification": "UNAVAILABLE",
                "tenure": "UNCLASSIFIED_TENURE",
                "live_adjusted_input": False,
                "horizons": blank,
            },
        ],
    }


def _symbol(frame, symbol: str):
    chosen = frame[(frame["Session"] == "2026-11-06") & (frame["Symbol"] == symbol)]
    assert len(chosen) == 1
    return chosen.iloc[0]


def _stored(outcomes: dict, symbol: str):
    row = next(item for item in outcomes["rows"] if item["symbol"] == symbol and item["session"] == "2026-11-06")
    return row["horizons"]["T+1"]["return_pct"]

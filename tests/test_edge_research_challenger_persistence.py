"""Regression tests for Challenger persistence dtype/schema safety."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.edge_research.challenger import CandidateRobustnessResult
from modules.edge_research.contracts import EDGE_HYPOTHESIS_LEDGER_COLUMNS
from modules.edge_research.storage import (
    append_robustness_history,
    normalize_hypothesis_ledger_dtypes,
    read_ledger,
    read_challenger_run,
    update_ledger_robustness,
    write_discovery_run,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_EDGE_DATA = REPO_ROOT / "data" / "edge_research"


@pytest.fixture
def edge_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "edge_research"
    d.mkdir()
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(d))
    return d


def _discovery_shaped_ledger_row(edge_id: str = "EDGE-000001") -> dict:
    row = {col: "" for col in EDGE_HYPOTHESIS_LEDGER_COLUMNS}
    row.update(
        {
            "edge_id": edge_id,
            "created_at": "2026-08-19T13:01:32Z",
            "discovery_run_id": "disc001",
            "research_version": "3.0.0-challenger",
            "market_state": "STRESS",
            "market_transition": "STRESS -> STRESS",
            "baseline_type": "SAME_TRANSITION",
            "condition_text": "RS10<=-10",
            "feature_1": "rs10",
            "operator_1": "<=",
            "threshold_1": -10.0,
            "feature_2": "",
            "operator_2": "",
            "threshold_2": "",
            "candidate_n": 30,
            "baseline_n": 284,
            "best_horizon": "T10",
            "incremental_median": 4.46,
            "status": "CANDIDATE",
            "discovery_start_date": "2026-07-23",
            "discovery_end_date": "2026-08-14",
            "oos_status": "NOT_TESTED",
            "notes": "",
        }
    )
    return row


def _write_discovery_shaped_csv(path: Path, n: int = 1) -> None:
    rows = [_discovery_shaped_ledger_row(f"EDGE-{i:06d}") for i in range(1, n + 1)]
    pd.DataFrame(rows).to_csv(path, index=False)


def _robustness_result(
    edge_id: str,
    *,
    status: str,
    main_flag: str = "",
    reasons: list[str] | None = None,
    flags: list[str] | None = None,
) -> CandidateRobustnessResult:
    return CandidateRobustnessResult(
        edge_id=edge_id,
        condition_text="RS10<=-10",
        market_transition="STRESS -> STRESS",
        best_horizon="T10",
        candidate_n=30,
        robustness_status=status,
        fragility_flags=flags or [],
        rejection_reasons=reasons or [],
        main_fragility_flag=main_flag,
        observed_episodes=1,
        positive_episodes=1,
        negative_episodes=0,
        mixed_episodes=0,
        date_count=2,
        unique_symbol_count=22,
        tests={},
        episode_summary={},
    )


def test_pre_fix_float64_inference_blocks_raw_reject_assignment():
    """Reproduce live failure class: empty CSV columns reload as float64."""
    ledger = pd.read_csv(pd.io.common.StringIO(
        "edge_id,robustness_status,main_fragility_flag\nEDGE-000001,,\n"
    ))
    assert ledger["robustness_status"].dtype == np.dtype("float64")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            ledger.loc[ledger["edge_id"] == "EDGE-000001", "robustness_status"] = "REJECT"
            raised = None
        except (TypeError, ValueError) as exc:
            raised = exc

    assert raised is not None or any(
        issubclass(w.category, FutureWarning)
        and "incompatible dtype" in str(w.message)
        for w in caught
    ), "Expected float64/string assignment failure or FutureWarning"


def test_csv_float64_inference_normalized_before_persistence(edge_data_dir):
    """Persistence path must normalize float64-inferred columns before assignment."""
    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert str(ledger["robustness_status"].dtype) == "string"

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        update_ledger_robustness(
            [_robustness_result("EDGE-000001", status="REJECT", main_flag="DATE_CONCENTRATED",
                                reasons=["sample_below_minimum"], flags=["DATE_CONCENTRATED"])],
            "run_reject_001",
            edge_data_dir,
        )

    reloaded = pd.read_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    row = reloaded.iloc[0]
    assert row["robustness_status"] == "REJECT"
    assert row["main_fragility_flag"] == "DATE_CONCENTRATED"
    assert "sample_below_minimum" in str(row["rejection_reasons"])
    assert row["robustness_run_id"] == "run_reject_001"
    assert int(row["observed_episodes"]) == 1


@pytest.mark.parametrize("status,main_flag,flags,reasons", [
    ("REJECT", "SAMPLE_BELOW_MINIMUM_AFTER_ROBUSTNESS_REMOVAL", ["DATE_CONCENTRATED"], ["sample_below_minimum"]),
    ("FRAGILE", "DATE_CONCENTRATED", ["DATE_CONCENTRATED", "ONE_EPISODE_ONLY"], []),
    ("PASS", "", [], []),
])
def test_all_robustness_statuses_persist(status, main_flag, flags, reasons, edge_data_dir):
    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    update_ledger_robustness(
        [_robustness_result("EDGE-000001", status=status, main_flag=main_flag, flags=flags, reasons=reasons)],
        f"run_{status.lower()}",
        edge_data_dir,
    )
    row = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir).iloc[0]
    assert row["robustness_status"] == status
    if main_flag:
        assert row["main_fragility_flag"] == main_flag
    else:
        assert pd.isna(row["main_fragility_flag"]) or row["main_fragility_flag"] == ""
    assert int(row["observed_episodes"]) == 1


def test_missing_robustness_values_load_safely_before_challenger(edge_data_dir):
    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv", n=3)
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert ledger["robustness_status"].isna().all()
    assert str(ledger["main_fragility_flag"].dtype) == "string"
    assert str(ledger["observed_episodes"].dtype) == "Int64"


def test_existing_float64_csv_normalized_on_read(edge_data_dir):
    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    raw = pd.read_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    assert raw["robustness_status"].dtype == np.dtype("float64")

    normalized = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert str(normalized["robustness_status"].dtype) == "string"
    assert str(normalized["main_fragility_flag"].dtype) == "string"


def test_fragility_flags_and_reason_text_persist(edge_data_dir):
    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    update_ledger_robustness(
        [_robustness_result(
            "EDGE-000001",
            status="FRAGILE",
            main_flag="DATE_CONCENTRATED",
            flags=["DATE_CONCENTRATED", "ONE_EPISODE_ONLY", "OUTLIER_FRAGILE"],
            reasons=["incremental_median_gone_after_best_date_removal"],
        )],
        "run_fragile",
        edge_data_dir,
    )
    row = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir).iloc[0]
    assert "DATE_CONCENTRATED" in str(row["fragility_flags"])
    assert "ONE_EPISODE_ONLY" in str(row["fragility_flags"])
    assert "incremental_median" in str(row["rejection_reasons"])


def test_discovery_fields_unchanged_after_challenger_persistence(edge_data_dir):
    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    before = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir).iloc[0].copy()
    update_ledger_robustness(
        [_robustness_result("EDGE-000001", status="REJECT", main_flag="DATE_CONCENTRATED")],
        "run_preserve",
        edge_data_dir,
    )
    after = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir).iloc[0]
    for col in (
        "edge_id", "discovery_run_id", "condition_text", "candidate_n", "incremental_median",
        "status", "discovery_start_date", "discovery_end_date",
    ):
        assert after[col] == before[col]


def test_write_reload_engine_read_survives(edge_data_dir):
    from modules.edge_research.engine import EdgeResearchEngine

    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    write_discovery_run(
        {
            "run_id": "disc001",
            "promoted_candidates": 1,
            "candidates": [{"condition_key": "STRESS -> STRESS|rs10:rs10_le_-10"}],
        },
        data_dir=edge_data_dir,
    )
    update_ledger_robustness(
        [_robustness_result("EDGE-000001", status="FRAGILE", main_flag="DATE_CONCENTRATED")],
        "run_reload",
        edge_data_dir,
    )
    engine = EdgeResearchEngine(data_dir=edge_data_dir)
    top = engine.get_top_candidates(limit=1)[0]
    assert top["robustness_status"] == "FRAGILE"
    assert top["main_fragility_flag"] == "DATE_CONCENTRATED"
    assert int(top["observed_episodes"]) == 1


def test_second_challenger_run_no_dtype_corruption(edge_data_dir):
    _write_discovery_shaped_csv(edge_data_dir / "edge_hypothesis_ledger.csv")
    update_ledger_robustness(
        [_robustness_result("EDGE-000001", status="REJECT", main_flag="FLAG_A")],
        "run_one",
        edge_data_dir,
    )
    update_ledger_robustness(
        [_robustness_result("EDGE-000001", status="FRAGILE", main_flag="DATE_CONCENTRATED")],
        "run_two",
        edge_data_dir,
    )
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    assert str(ledger["robustness_status"].dtype) == "string"
    assert ledger.iloc[0]["robustness_status"] == "FRAGILE"
    assert ledger.iloc[0]["robustness_run_id"] == "run_two"


def test_superseded_cohort_rows_untouched(edge_data_dir):
    legacy = _discovery_shaped_ledger_row("EDGE-LEGACY")
    legacy["discovery_run_id"] = "disc_old"
    current = _discovery_shaped_ledger_row("EDGE-000001")
    pd.DataFrame([legacy, current]).to_csv(edge_data_dir / "edge_hypothesis_ledger.csv", index=False)

    update_ledger_robustness(
        [_robustness_result("EDGE-000001", status="PASS")],
        "run_current",
        edge_data_dir,
    )
    ledger = read_ledger("edge_hypothesis_ledger.csv", edge_data_dir)
    legacy_row = ledger[ledger["edge_id"] == "EDGE-LEGACY"].iloc[0]
    current_row = ledger[ledger["edge_id"] == "EDGE-000001"].iloc[0]
    assert pd.isna(legacy_row["robustness_status"]) or legacy_row["robustness_status"] is pd.NA
    assert current_row["robustness_status"] == "PASS"


def test_robustness_history_string_fields_persist(edge_data_dir):
    append_robustness_history(
        "run_hist",
        "EDGE-000001",
        "2026-08-19T13:00:00Z",
        [{"test_name": "leave_best_date_out", "result": "FAIL", "reason": "DATE_CONCENTRATED"}],
        edge_data_dir,
    )
    hist = read_ledger("edge_robustness_history.csv", edge_data_dir)
    assert hist.iloc[0]["result"] == "FAIL"
    assert hist.iloc[0]["reason"] == "DATE_CONCENTRATED"
    assert str(hist["result"].dtype) == "string"


def test_normalize_hypothesis_ledger_dtypes_is_idempotent():
    df = pd.DataFrame({"edge_id": ["E1"], "robustness_status": [pd.NA], "observed_episodes": [pd.NA]})
    once = normalize_hypothesis_ledger_dtypes(df)
    twice = normalize_hypothesis_ledger_dtypes(once)
    assert str(once["robustness_status"].dtype) == "string"
    assert str(twice["robustness_status"].dtype) == "string"


@pytest.mark.skipif(not REAL_EDGE_DATA.exists(), reason="local edge research data unavailable")
def test_end_to_end_challenger_on_real_cohort_copy(tmp_path, monkeypatch):
    """Run full engine challenger against copied real research cohort."""
    data_dir = tmp_path / "edge_research"
    shutil.copytree(REAL_EDGE_DATA, data_dir)
    monkeypatch.setenv("EDGE_RESEARCH_DATA_DIR", str(data_dir))

    from modules.edge_research.engine import EdgeResearchEngine

    engine = EdgeResearchEngine(data_dir=data_dir)
    engine.initialize()
    cohort = engine.has_valid_discovery_cohort()
    assert cohort is True

    result = engine.run_challenger(force=True)
    assert result.run_id != "skipped"
    assert result.candidates_entering >= 1

    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir)
    cohort_rows = ledger[ledger["discovery_run_id"].astype(str).str.len() > 0]
    populated = cohort_rows[cohort_rows["robustness_status"].notna()]
    assert len(populated) >= 1
    assert populated["robustness_status"].isin(["PASS", "FRAGILE", "REJECT"]).all()

    challenger = read_challenger_run(data_dir)
    assert challenger.get("run_id") == result.run_id
    assert challenger.get("robustness_pass") == result.robustness_pass
    assert challenger.get("robustness_fragile") == result.robustness_fragile
    assert challenger.get("robustness_reject") == result.robustness_reject

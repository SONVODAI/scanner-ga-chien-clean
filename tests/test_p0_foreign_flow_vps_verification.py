"""Tests for P0 foreign-flow VPS verification helpers (offline / fail-safe)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.forecast_research.p0_foreign_vps_verify import (
    alternative_source_feasibility_audit,
    analyze_ssi_heatmap_dataframe,
    detect_runtime,
    is_production_vps_host,
    run_verification,
)
from modules.forecast_research.p0_providers import SsiHoseForeignFlowProvider


def test_not_production_vps_in_cloud_agent():
    assert is_production_vps_host() is False


def test_runtime_detects_python():
    rt = detect_runtime()
    assert rt["is_production_vps"] is False
    assert rt["python_executable"]
    assert "vnstock_version" in rt


def test_heatmap_analysis_net_and_scope():
    df = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "foreignBuyValue": [100.0, 50.0],
            "foreignSellValue": [40.0, 10.0],
            "foreignBuyVolume": [1.0, 2.0],
            "foreignSellVolume": [0.5, 0.5],
        }
    )
    out = analyze_ssi_heatmap_dataframe(df, trade_date="2026-08-22")
    assert out["ok"] is True
    assert out["foreign_flow_scope"] == "HOSE"
    assert out["values"]["foreign_buy_value"] == 150.0
    assert out["values"]["foreign_sell_value"] == 50.0
    assert out["values"]["foreign_net_value"] == 100.0
    assert out["net_equals_buy_minus_sell"] is True
    assert out["units"] == "PROVIDER_NATIVE_UNPROVEN"
    assert out["historical_semantics"] == "UNSUPPORTED_NO_DATE_PARAM"


def test_missing_columns_not_zero():
    df = pd.DataFrame({"symbol": ["AAA"], "price": [1.0]})
    out = analyze_ssi_heatmap_dataframe(df, trade_date="2026-08-22")
    assert out["ok"] is False
    assert out["values"]["foreign_buy_value"] is None
    assert out["values"]["foreign_net_value"] is None


def test_alternative_audit_table_present():
    rows = alternative_source_feasibility_audit()
    assert len(rows) >= 4
    assert all("source" in r and "pit_suitable" in r for r in rows)
    assert all(r.get("implement_now") is False for r in rows)


def test_run_verification_blocked_off_vps(tmp_path: Path):
    out = tmp_path / "probe.json"
    report = run_verification(trade_date="2026-08-22", persist_json=out)
    assert report["verdict"] == "P0_PRODUCTION_VERIFICATION_BLOCKED"
    assert report["production_result"]["vps_tested"] == "NO"
    assert report["historical_capability"] == "UNRESOLVED"
    assert out.exists()


def test_provider_meta_includes_foreign_flow_scope():
    meta = SsiHoseForeignFlowProvider()._meta()
    assert meta["foreign_flow_scope"] == "HOSE"
    assert meta["historical_supported"] is False
    assert meta["forward_only"] is True
    assert meta["units"] == "PROVIDER_NATIVE_UNPROVEN"

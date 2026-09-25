"""Streamlit still installs legacy vnstock, not the quarantined PyPI pin or 4.x."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_COMMIT = "e8339514ad7cd757259d3f1b797bca379f93606a"


def test_production_requirements_pin_legacy_git_commit():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    req_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert "vnstock==0.2.9.2" not in req_lines
    assert f"vnstock @ git+https://github.com/thinh-vu/vnstock.git@{LEGACY_COMMIT}" in req_lines
    assert not any(line.startswith("vnstock>=") or line.startswith("vnstock==") for line in req_lines)


def test_collector_requirements_stay_on_vnstock_4():
    text = (ROOT / "requirements-collector.txt").read_text(encoding="utf-8")
    assert "vnstock>=4.0.5,<5" in text
    assert LEGACY_COMMIT not in text


def test_legacy_stock_historical_data_import_when_installed():
    """Import smoke for the production pin. Skips in environments without it."""
    pytest.importorskip("vnstock")
    import importlib.metadata as metadata

    version = metadata.version("vnstock")
    if not version.startswith("0.2."):
        pytest.skip(f"installed vnstock {version} is not the Streamlit legacy pin")
    from vnstock import stock_historical_data

    params = inspect.signature(stock_historical_data).parameters
    for name in ("symbol", "start_date", "end_date", "resolution", "type", "beautify"):
        assert name in params
    assert version.startswith("0.2.9.2")

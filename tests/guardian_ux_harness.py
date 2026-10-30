"""Isolated Guardian UI harness. Not the production app.

Full-script executions append FULL to GUARDIAN_UX_LOG. A fragment rerun does
not. Holdings paths come from MRBOT_USER_HOLDINGS_* so this never touches the
repo ledger. Do not set GITHUB_TOKEN.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

import modules.user_holdings as user_holdings
from position_guardian import render_guardian, render_holdings_editor

# Test process only. Never call the production GitHub contents API.
user_holdings._github_token = lambda: None
user_holdings._github_read = lambda *_a, **_k: None
user_holdings._github_write = lambda *_a, **_k: "LOCAL_ONLY"

_log = os.environ.get("GUARDIAN_UX_LOG", "")
if _log:
    with open(_log, "a", encoding="utf-8") as handle:
        handle.write("FULL\n")

if "full_runs" not in st.session_state:
    st.session_state["full_runs"] = 0
st.session_state["full_runs"] += 1
st.markdown(f"FULL_RUNS={st.session_state['full_runs']}")

if "scan_price" not in st.session_state:
    st.session_state["scan_price"] = 15.0
if "scan_mode" not in st.session_state:
    st.session_state["scan_mode"] = "data"
if st.button("Full scan"):
    st.session_state["scan_price"] = 21.0
    st.session_state["scan_mode"] = "data"
if st.button("Empty scan"):
    st.session_state["scan_mode"] = "empty"
price = float(st.session_state["scan_price"])
mode = st.session_state["scan_mode"]
st.markdown(f"SCAN_MODE={mode}")
st.markdown(f"SCAN_PRICE={price}")

scan_df = pd.DataFrame(
    [
        {
            "symbol": "SSI",
            "price": price,
            "ema9": 10.0,
            "ma20": 9.0,
            "obv": 100,
            "obv_ema9": 50,
        },
        {
            "symbol": "HPG",
            "price": 8.0,
            "ema9": 10.0,
            "ma20": 12.0,
            "obv": 10,
            "obv_ema9": 20,
        },
    ]
)
if mode == "empty":
    # Same call as app.py when scan_df.empty: editor outside the fragment.
    render_holdings_editor()
else:
    render_guardian(scan_df)

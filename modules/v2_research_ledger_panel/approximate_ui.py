"""Approximate performance section. It reads a finished view and does not score rows."""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.approximate_returns.view import BUNDLED_VIEW, read_view
from research.v2_research_ledger.remote_delivery import fetch_approximate_performance, resolve_remote_config

PANEL_TITLE = "APPROXIMATE PERFORMANCE RESEARCH"
HORIZONS = ("T+1", "T+3", "T+5", "T+10", "T+15", "T+20")
COHORTS = (
    ("brain_a", "Brain A"),
    ("sweetspot", "Sweetspot"),
    ("overlap", "Overlap"),
    ("unattributed", "Unattributed"),
)
BANDS = (
    ("market_real_below_5", "Below 5"),
    ("market_real_5_to_below_7", "5 to below 7"),
    ("market_real_7_or_higher", "7 or higher"),
)


def render_approximate_performance_panel(st_module: Any = None, *, view: dict | None = None, remote: bool = True) -> None:
    """Expandable board under the Research Ledger. Missing data stays blank."""
    st = st_module
    if st is None:
        import streamlit as st  # type: ignore
    origin = "supplied"
    if view is None:
        view, origin = load_performance_view(remote=remote)
    with st.expander(PANEL_TITLE, expanded=False):
        st.caption(
            "Research measurement only. These returns use the last 5-minute close on both ends. "
            "They are not execution P&L. WAIT and NO_OBSERVATION are not executed buys. "
            "No statistical significance is claimed."
        )
        if view is None:
            st.warning("Approximate performance view is not available.")
            return
        if origin == "bundled":
            st.caption("Showing the research build shipped with this app.")
        elif origin == "remote":
            st.caption("Showing the research build served beside the Research Ledger.")
        _summary(st, view)
        st.markdown("**Source comparison**")
        st.caption(
            f"Frozen rows={view.get('records')}. "
            f"Deduplicated symbol sessions={view.get('deduped_observations')}. "
            "Cohort statistics count each symbol and T0 date once. "
            "Row coverage below counts every frozen row."
        )
        st.dataframe(_cohort_table(view), use_container_width=True, hide_index=True)
        st.markdown("**Market Real**")
        st.caption("Frozen market_real with provenance. Bands are descriptive groups, not a regime model.")
        st.dataframe(_market_table(view), use_container_width=True, hide_index=True)
        st.markdown("**Data quality**")
        st.dataframe(_quality_table(view), use_container_width=True, hide_index=True)
        gaps = view.get("t0_gaps") if isinstance(view.get("t0_gaps"), dict) else {}
        st.caption(
            f"T0 reference gaps: both prices={gaps.get('rows_with_both_prices', 0)}, "
            f"at least 2%={gaps.get('abs_gap_at_least_2pct', 0)}, "
            f"at least 5%={gaps.get('abs_gap_at_least_5pct', 0)}. "
            "The nomination price is not used as the return denominator."
        )
        st.caption(
            f"Last confirmed trading session={view.get('as_of') or 'unknown'}. "
            f"Last successful research build={view.get('panel_sha256') or 'unknown'}."
        )
        names = ", ".join(
            f"{item.get('symbol')} {item.get('session')}" for item in view.get("discontinuities") or [] if isinstance(item, dict)
        )
        st.caption(f"Suspected discontinuities excluded from the statistics: {names or 'none'}.")


def load_performance_view(*, remote: bool = True) -> tuple[dict | None, str]:
    if remote:
        url, token = resolve_remote_config()
        fetched = fetch_approximate_performance(url, token)
        if fetched is not None:
            return fetched, "remote"
    bundled = read_view(BUNDLED_VIEW)
    if bundled is not None:
        return bundled, "bundled"
    return None, "absent"


def _summary(st, view: dict) -> None:
    overall = view.get("overall") if isinstance(view.get("overall"), dict) else {}
    horizon = (overall.get("horizons") or {}).get("T+5") or {}
    coverage = ((view.get("coverage") or {}).get("horizons") or {}).get("T+5") or {}
    st.caption(
        f"Total frozen rows={view.get('records')}. "
        f"Deduplicated observations={view.get('deduped_observations')}. "
        f"Valid T+5 deduplicated sample={horizon.get('primary')}. "
        f"Valid T+5 frozen rows={coverage.get('APPROX_AVAILABLE')}. "
        f"Average T+5 return={_number(horizon.get('average_return_pct'))}. "
        f"T+5 win rate above +3%={_rate(horizon.get('win_rate_above_3pct'))} "
        f"on {horizon.get('primary')} observations. "
        f"T+5 loss rate={_rate(horizon.get('loss_rate'))} "
        f"on {horizon.get('primary')} observations."
    )


def _cohort_table(view: dict) -> pd.DataFrame:
    cohorts = view.get("cohorts") if isinstance(view.get("cohorts"), dict) else {}
    records = []
    for key, label in COHORTS:
        horizons = ((cohorts.get(key) or {}).get("horizons") or {})
        for name in HORIZONS:
            item = horizons.get(name) or {}
            records.append({
                "Source": label,
                "Horizon": name,
                "Sample": item.get("primary"),
                "Average": _number(item.get("average_return_pct")),
                "Median": _number(item.get("median_return_pct")),
                "Win >3%": _rate(item.get("win_rate_above_3pct")),
                "Win >5%": _rate(item.get("win_rate_above_5pct")),
                "Loss rate": _rate(item.get("loss_rate")),
                "Downside p10": _number(item.get("downside_p10_pct")),
            })
    return pd.DataFrame(records)


def _market_table(view: dict) -> pd.DataFrame:
    bands = ((view.get("market_context") or {}).get("bands") or {})
    records = []
    for key, label in BANDS:
        band = bands.get(key) or {}
        item = ((band.get("horizons") or {}).get("T+5") or {})
        records.append({
            "Market Real": label,
            "Observations": band.get("observations"),
            "T+5 sample": item.get("primary"),
            "Average": _number(item.get("average_return_pct")),
            "Median": _number(item.get("median_return_pct")),
            "Win >3%": _rate(item.get("win_rate_above_3pct")),
            "Loss rate": _rate(item.get("loss_rate")),
            "Downside p10": _number(item.get("downside_p10_pct")),
        })
    return pd.DataFrame(records)


def _quality_table(view: dict) -> pd.DataFrame:
    horizons = ((view.get("coverage") or {}).get("horizons") or {})
    records = []
    for name in HORIZONS:
        item = horizons.get(name) or {}
        records.append({
            "Horizon": name,
            "Valid rows": item.get("APPROX_AVAILABLE"),
            "Immature": item.get("NOT_YET_OBSERVED"),
            "Truncated": item.get("TRUNCATED_SESSION"),
            "Discontinuity": item.get("DISCONTINUITY"),
            "Missing": (item.get("TARGET_MISSING") or 0) + (item.get("T0_REFERENCE_MISSING") or 0),
        })
    return pd.DataFrame(records)


def _number(value) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:.2f}%"


def _rate(value) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value * 100:.1f}%"

"""
Read-only Streamlit observation board: BOT Baseline vs BOT Experience Shadow.

Display / monitoring only — never writes ledger, outcomes, recall index,
observations, lifecycle, or production recommendation files.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from modules.regime_alpha import (
    RECALL_LEVEL_EXACT,
    RECALL_LEVEL_FAMILY,
    RECALL_LEVEL_GLOBAL,
    RECALL_LEVEL_NO_EVIDENCE,
)
from modules.regime_alpha_forward_eval import (
    DATA_DIR,
    EVAL_MODE_FORWARD_FROZEN,
    EVAL_MODE_RECONSTRUCTED_AUDIT,
    ForwardScorecard,
    REGIME_LABEL_GLOBAL,
    ScorecardSlice,
    classify_movement_class,
    load_forward_ledger,
    load_forward_outcomes,
)
from modules.regime_alpha_shadow import summarize_shadow_comparison
from leader_memory import load_shadow_recommendations

OBSERVATIONS_FILE = "observations.csv"

COMPARISON_COLUMNS: Sequence[str] = (
    "symbol",
    "BaselineRank",
    "ShadowExperienceRank",
    "RankDelta",
    "BaselineScore",
    "ShadowExperienceScore",
    "ScoreDelta",
    "movement_class",
    "RecallLevelDisplay",
    "RecallSamples",
    "RecallConfidence",
    "RecallAlpha",
    "stock_pattern_key",
    "market_context_key",
    "ActualT3Return",
    "ActualT5Return",
    "ActualT10Return",
    "outcome_status_t3",
    "outcome_status_t5",
    "outcome_status_t10",
)

MOVEMENT_EMOJI = {
    "ACTIVE_PROMOTED": "⬆️ ACTIVE_PROMOTED",
    "ACTIVE_DEMOTED": "⬇️ ACTIVE_DEMOTED",
    "PASSIVE_MOVED": "↕️ PASSIVE_MOVED",
    "UNCHANGED": "➖ UNCHANGED",
}


def _normalize_observation_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "nan", "none"}:
        return ""
    return text


def load_observation_session_lookup(
    observations: Optional[pd.DataFrame] = None,
) -> Dict[Tuple[str, str], str]:
    """
    Read-only (session_date, symbol) -> observation_id map from earning observations.
    Mirrors freeze_t0_ledger provenance — display layer only.
    """
    if observations is None:
        obs_path = DATA_DIR / OBSERVATIONS_FILE
        if not obs_path.exists():
            return {}
        observations = pd.read_csv(obs_path, encoding="utf-8-sig", low_memory=False)

    if observations.empty or "observation_id" not in observations.columns:
        return {}

    obs = observations.copy()
    obs["trade_date"] = pd.to_datetime(obs["trade_date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    obs["symbol"] = obs["symbol"].astype(str).str.strip().str.upper()
    lookup: Dict[Tuple[str, str], str] = {}
    for _, row in obs.iterrows():
        key = (str(row.get("trade_date", "")).strip(), str(row.get("symbol", "")).strip())
        oid = _normalize_observation_id(row.get("observation_id"))
        if key[0] and key[1] and oid:
            lookup[key] = oid
    return lookup


def has_forward_observation_provenance(
    row: Mapping[str, Any],
    observation_lookup: Optional[Mapping[Tuple[str, str], str]] = None,
) -> bool:
    """
    True when a FORWARD_FROZEN row is linked to earning-learning observations.
    Uses ledger observation_id or a deterministic observations.csv match.
    """
    oid = _normalize_observation_id(row.get("observation_id"))
    if oid:
        return True
    lookup = observation_lookup if observation_lookup is not None else load_observation_session_lookup()
    session_date = str(row.get("session_date", "")).strip()
    symbol = str(row.get("symbol", "")).strip().upper()
    return bool(session_date and symbol and (session_date, symbol) in lookup)


def filter_genuine_forward_ledger(
    ledger: pd.DataFrame,
    *,
    observation_lookup: Optional[Mapping[Tuple[str, str], str]] = None,
) -> pd.DataFrame:
    """
    Live scoreboard rows: evaluation_mode=FORWARD_FROZEN with observation provenance.
    Excludes RECONSTRUCTED_AUDIT and unlinked fixture rows without symbol/DNA heuristics.
    """
    if ledger is None or ledger.empty:
        return pd.DataFrame()
    out = ledger[
        ledger.get("evaluation_mode", pd.Series(dtype=str)).astype(str)
        == EVAL_MODE_FORWARD_FROZEN
    ].copy()
    if out.empty:
        return out
    lookup = (
        observation_lookup
        if observation_lookup is not None
        else load_observation_session_lookup()
    )
    mask = out.apply(
        lambda row: has_forward_observation_provenance(row, lookup),
        axis=1,
    )
    return out[mask].reset_index(drop=True)


def count_excluded_forward_rows(ledger: pd.DataFrame) -> Dict[str, int]:
    """Summarize rows omitted from the live forward scoreboard."""
    if ledger is None or ledger.empty:
        return {"reconstructed_audit": 0, "missing_provenance": 0}
    mode = ledger.get("evaluation_mode", pd.Series(dtype=str)).astype(str)
    reconstructed = int((mode == EVAL_MODE_RECONSTRUCTED_AUDIT).sum())
    forward = ledger[mode == EVAL_MODE_FORWARD_FROZEN]
    lookup = load_observation_session_lookup()
    missing = int(
        (~forward.apply(lambda row: has_forward_observation_provenance(row, lookup), axis=1)).sum()
    ) if not forward.empty else 0
    return {"reconstructed_audit": reconstructed, "missing_provenance": missing}


def load_genuine_forward_joined() -> pd.DataFrame:
    ledger = filter_genuine_forward_ledger(load_forward_ledger())
    outcomes = load_forward_outcomes()
    if ledger.empty:
        return pd.DataFrame()
    if outcomes.empty:
        return ledger.copy()
    return ledger.merge(
        outcomes, on=["session_date", "symbol", "snapshot_id"], how="left"
    )


def format_recall_level_display(level: Any) -> str:
    text = str(level or "").strip()
    if text == RECALL_LEVEL_GLOBAL:
        return f"GLOBAL_DNA ({REGIME_LABEL_GLOBAL})"
    if text == RECALL_LEVEL_EXACT:
        return "EXACT_CONTEXT"
    if text == RECALL_LEVEL_FAMILY:
        return "FAMILY_CONTEXT"
    if text in {"", "nan", "None", RECALL_LEVEL_NO_EVIDENCE}:
        return "NO_RECALL_EVIDENCE"
    return text


def _ensure_movement_class(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "movement_class" not in out.columns:
        out["movement_class"] = out.apply(classify_movement_class, axis=1)
    return out


def prepare_live_shadow_frame(shadow_df: pd.DataFrame) -> pd.DataFrame:
    """Augment live shadow snapshot for display; values unchanged."""
    if shadow_df is None or shadow_df.empty:
        return pd.DataFrame()
    out = _ensure_movement_class(shadow_df)
    out["RecallLevelDisplay"] = out["RecallLevel"].map(format_recall_level_display)
    for col in (
        "ActualT3Return",
        "ActualT5Return",
        "ActualT10Return",
        "outcome_status_t3",
        "outcome_status_t5",
        "outcome_status_t10",
    ):
        if col not in out.columns:
            if col.startswith("outcome_status"):
                out[col] = "PENDING"
            else:
                out[col] = pd.NA
    return out


def prepare_forward_session_frame(joined: pd.DataFrame, session_date: str) -> pd.DataFrame:
    if joined is None or joined.empty:
        return pd.DataFrame()
    sub = joined[joined["session_date"].astype(str) == str(session_date)].copy()
    sub = _ensure_movement_class(sub)
    sub["RecallLevelDisplay"] = sub["RecallLevel"].map(format_recall_level_display)
    for col in ("outcome_status_t3", "outcome_status_t5", "outcome_status_t10"):
        if col in sub.columns:
            sub[col] = sub[col].fillna("PENDING").astype(str)
        else:
            sub[col] = "PENDING"
    return sub


def movement_class_counts(df: pd.DataFrame) -> Dict[str, int]:
    if df is None or df.empty:
        return {
            "ACTIVE_PROMOTED": 0,
            "ACTIVE_DEMOTED": 0,
            "PASSIVE_MOVED": 0,
            "UNCHANGED": 0,
        }
    vc = df["movement_class"].value_counts()
    return {
        "ACTIVE_PROMOTED": int(vc.get("ACTIVE_PROMOTED", 0)),
        "ACTIVE_DEMOTED": int(vc.get("ACTIVE_DEMOTED", 0)),
        "PASSIVE_MOVED": int(vc.get("PASSIVE_MOVED", 0)),
        "UNCHANGED": int(vc.get("UNCHANGED", 0)),
    }


def _scorecard_from_joined(joined: pd.DataFrame) -> ForwardScorecard:
    """Read-only scorecard over a pre-filtered joined frame (display layer only)."""
    from modules.regime_alpha_forward_eval import _build_slice, _top_n_by_session

    if joined.empty:
        return ForwardScorecard(evaluation_mode=EVAL_MODE_FORWARD_FROZEN)

    baseline_slices: Dict[int, ScorecardSlice] = {}
    shadow_slices: Dict[int, ScorecardSlice] = {}
    for n in (5, 10, 20):
        baseline_slices[n] = _build_slice(
            f"baseline_top{n}",
            _top_n_by_session(joined, "BaselineRank", n),
            "BaselineRank",
        )
        shadow_slices[n] = _build_slice(
            f"shadow_top{n}",
            _top_n_by_session(joined, "ShadowExperienceRank", n),
            "ShadowExperienceRank",
        )

    cohorts = {
        "ACTIVE_PROMOTED": joined[joined["movement_class"] == "ACTIVE_PROMOTED"],
        "ACTIVE_DEMOTED": joined[joined["movement_class"] == "ACTIVE_DEMOTED"],
        "PASSIVE_MOVED": joined[joined["movement_class"] == "PASSIVE_MOVED"],
        "UNCHANGED": joined[joined["movement_class"] == "UNCHANGED"],
    }

    lift = None
    b10, s10 = baseline_slices.get(10), shadow_slices.get(10)
    if b10 and s10 and b10.mean_t3 is not None and s10.mean_t3 is not None:
        lift = s10.mean_t3 - b10.mean_t3

    return ForwardScorecard(
        evaluation_mode=EVAL_MODE_FORWARD_FROZEN,
        sessions=int(joined["session_date"].nunique()),
        candidates=len(joined),
        baseline_top5=baseline_slices[5],
        baseline_top10=baseline_slices[10],
        baseline_top20=baseline_slices[20],
        shadow_top5=shadow_slices[5],
        shadow_top10=shadow_slices[10],
        shadow_top20=shadow_slices[20],
        learning_lift_top10_mean_t3=lift,
        cohort_active_promoted=_build_slice(
            "ACTIVE_PROMOTED", cohorts["ACTIVE_PROMOTED"], "ShadowExperienceRank"
        ),
        cohort_active_demoted=_build_slice(
            "ACTIVE_DEMOTED", cohorts["ACTIVE_DEMOTED"], "ShadowExperienceRank"
        ),
        cohort_passive_moved=_build_slice(
            "PASSIVE_MOVED", cohorts["PASSIVE_MOVED"], "ShadowExperienceRank"
        ),
        cohort_unchanged=_build_slice(
            "UNCHANGED", cohorts["UNCHANGED"], "BaselineRank"
        ),
    )


def evaluate_genuine_forward_scorecard() -> ForwardScorecard:
    joined = load_genuine_forward_joined()
    if not joined.empty and "movement_class" not in joined.columns:
        joined = _ensure_movement_class(joined)
    return _scorecard_from_joined(joined)


def _fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _lift_text(baseline: Optional[float], shadow: Optional[float]) -> str:
    if baseline is None or shadow is None:
        return "—"
    return f"{shadow - baseline:+.2f}"


def _scorecard_horizon_table(
    label: str,
    baseline: ScorecardSlice,
    shadow: ScorecardSlice,
) -> pd.DataFrame:
    rows = []
    for horizon, b_win, b_mean, b_med, b_bad, b_worst, s_win, s_mean, s_med, s_bad, s_worst in (
        (
            "T3",
            baseline.win_rate_t3,
            baseline.mean_t3,
            baseline.median_t3,
            baseline.bad_pick_rate_t3,
            baseline.worst_return_t3,
            shadow.win_rate_t3,
            shadow.mean_t3,
            shadow.median_t3,
            shadow.bad_pick_rate_t3,
            shadow.worst_return_t3,
        ),
        (
            "T5",
            baseline.win_rate_t5,
            baseline.mean_t5,
            baseline.median_t5,
            None,
            None,
            shadow.win_rate_t5,
            shadow.mean_t5,
            shadow.median_t5,
            None,
            None,
        ),
        (
            "T10",
            baseline.win_rate_t10,
            baseline.mean_t10,
            baseline.median_t10,
            None,
            None,
            shadow.win_rate_t10,
            shadow.mean_t10,
            shadow.median_t10,
            None,
            None,
        ),
    ):
        rows.append(
            {
                "Horizon": horizon,
                "Baseline WinRate": _fmt_pct(b_win),
                "Shadow WinRate": _fmt_pct(s_win),
                "Baseline Mean": _fmt_num(b_mean),
                "Shadow Mean": _fmt_num(s_mean),
                "Baseline Median": _fmt_num(b_med),
                "Shadow Median": _fmt_num(s_med),
                "Baseline BadPick": _fmt_pct(b_bad) if b_bad is not None else "—",
                "Shadow BadPick": _fmt_pct(s_bad) if s_bad is not None else "—",
                "Baseline Worst": _fmt_num(b_worst) if b_worst is not None else "—",
                "Shadow Worst": _fmt_num(s_worst) if s_worst is not None else "—",
                "LEARNING LIFT (Mean)": _lift_text(b_mean, s_mean),
            }
        )
    return pd.DataFrame(rows)


def _style_comparison_table(display_df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    def _row_style(row: pd.Series) -> List[str]:
        mc = str(row.get("movement_class", ""))
        if mc == "ACTIVE_PROMOTED":
            bg = "background-color: #d4edda"
        elif mc == "ACTIVE_DEMOTED":
            bg = "background-color: #f8d7da"
        elif mc == "PASSIVE_MOVED":
            bg = "background-color: #fff3cd"
        else:
            bg = ""
        return [bg] * len(row)

    return display_df.style.apply(_row_style, axis=1)


def _render_top10_block(shadow_df: pd.DataFrame) -> None:
    import streamlit as st

    left, right = st.columns(2)
    baseline_top = shadow_df.nsmallest(10, "BaselineRank")
    shadow_top = shadow_df.nsmallest(10, "ShadowExperienceRank")

    with left:
        st.markdown("**BOT BASELINE — TOP 10**")
        if baseline_top.empty:
            st.caption("Chưa có dữ liệu.")
        else:
            st.dataframe(
                baseline_top[
                    ["symbol", "BaselineRank", "BaselineScore", "RecallLevelDisplay"]
                ].rename(
                    columns={
                        "BaselineRank": "Rank",
                        "BaselineScore": "Score",
                        "RecallLevelDisplay": "Recall",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("**BOT SHADOW — TOP 10**")
        if shadow_top.empty:
            st.caption("Chưa có dữ liệu.")
        else:
            show = shadow_top[
                [
                    "symbol",
                    "ShadowExperienceRank",
                    "ShadowExperienceScore",
                    "RecallLevelDisplay",
                    "RecallSamples",
                    "RecallAlpha",
                    "RankDelta",
                    "movement_class",
                ]
            ].rename(
                columns={
                    "ShadowExperienceRank": "Rank",
                    "ShadowExperienceScore": "Score",
                    "RecallLevelDisplay": "Recall",
                    "RecallSamples": "Samples",
                    "RecallAlpha": "Alpha",
                    "RankDelta": "ΔRank",
                    "movement_class": "Movement",
                }
            )
            st.dataframe(show, use_container_width=True, hide_index=True)


def _render_cohort_block(title: str, cohort: ScorecardSlice) -> None:
    import streamlit as st

    st.markdown(f"**{title}** (n={cohort.n})")
    if cohort.n == 0:
        st.caption("Chưa có outcome READY cho nhóm này.")
        return
    st.caption(
        f"T3 WinRate {_fmt_pct(cohort.win_rate_t3)} | Mean {_fmt_num(cohort.mean_t3)} | "
        f"Median {_fmt_num(cohort.median_t3)} | BadPick {_fmt_pct(cohort.bad_pick_rate_t3)} | "
        f"Worst {_fmt_num(cohort.worst_return_t3)}"
    )


def render_shadow_observation_board(*, expanded: bool = True) -> None:
    """Render read-only Baseline vs Shadow observation board in Streamlit."""
    import streamlit as st

    st.markdown("---")
    with st.expander("🤖 BOT Baseline vs BOT Shadow", expanded=expanded):
        st.markdown("### BOT BASELINE vs BOT SHADOW")
        st.caption(
            "Bảng quan sát chỉ đọc — so sánh xếp hạng Baseline (production) "
            "với Shadow Experience (học kinh nghiệm). "
            f"GLOBAL_DNA = {REGIME_LABEL_GLOBAL} — không phải bằng chứng "
            "'mùa nào thức ấy'."
        )

        live_raw = load_shadow_recommendations()
        live_df = prepare_live_shadow_frame(live_raw)
        genuine_joined = load_genuine_forward_joined()
        if not genuine_joined.empty and "movement_class" not in genuine_joined.columns:
            genuine_joined = _ensure_movement_class(genuine_joined)

        # --- Live / latest session summary ---
        if not live_df.empty:
            session_date = str(live_df.iloc[0].get("session_date", "—"))
            summary = summarize_shadow_comparison(live_raw)
            moves = movement_class_counts(live_df)
            st.markdown(f"**Phiên live shadow:** `{session_date}`")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Ứng viên", summary.candidates)
            c2.metric("Top-5 overlap", summary.top5_overlap)
            c3.metric("Top-10 overlap", summary.top10_overlap)
            c4.metric("Recall coverage", summary.with_recall_evidence)
            c5.metric(
                "GLOBAL (CONTEXT_FREE)",
                summary.global_count,
                help=f"GLOBAL_DNA = {REGIME_LABEL_GLOBAL}",
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("ACTIVE_PROMOTED", moves["ACTIVE_PROMOTED"])
            m2.metric("ACTIVE_DEMOTED", moves["ACTIVE_DEMOTED"])
            m3.metric("PASSIVE_MOVED", moves["PASSIVE_MOVED"])
            m4.metric("UNCHANGED", moves["UNCHANGED"])
            st.caption(
                f"EXACT {summary.exact_count} | FAMILY {summary.family_count} | "
                f"GLOBAL {summary.global_count} (CONTEXT_FREE_PRIOR)"
            )
            comparison_df = live_df
        elif not genuine_joined.empty:
            sessions = sorted(genuine_joined["session_date"].astype(str).unique())
            session_date = sessions[-1]
            comparison_df = prepare_forward_session_frame(genuine_joined, session_date)
            summary = summarize_shadow_comparison(comparison_df)
            moves = movement_class_counts(comparison_df)
            st.markdown(f"**Phiên FORWARD_FROZEN gần nhất:** `{session_date}`")
            st.info(
                "Chưa có live shadow snapshot hôm nay. "
                "Đang hiển thị phiên forward đã đóng băng gần nhất."
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Ứng viên", len(comparison_df))
            c2.metric("Recall coverage", summary.with_recall_evidence)
            c3.metric("Top-10 overlap", summary.top10_overlap)
        else:
            st.info(
                "Chưa có dữ liệu shadow live hoặc phiên FORWARD_FROZEN thật. "
                "Sau phiên giao dịch hợp lệ, BOT sẽ tự ghi snapshot shadow."
            )
            comparison_df = pd.DataFrame()

        # --- Main comparison table ---
        st.markdown("#### Bảng so sánh Baseline vs Shadow")
        if comparison_df.empty:
            st.caption("Không có bảng so sánh để hiển thị.")
        else:
            display_cols = [c for c in COMPARISON_COLUMNS if c in comparison_df.columns]
            display = comparison_df[display_cols].copy()
            display["movement_class"] = display["movement_class"].map(
                lambda x: MOVEMENT_EMOJI.get(str(x), str(x))
            )
            styled = _style_comparison_table(display)
            st.dataframe(styled, use_container_width=True, hide_index=True)
            _render_top10_block(comparison_df)

        # --- Forward scoreboard (genuine FORWARD_FROZEN only) ---
        st.markdown("#### Scoreboard Forward (FORWARD_FROZEN thật)")
        ledger_all = load_forward_ledger(evaluation_mode=None)
        excluded = count_excluded_forward_rows(ledger_all)
        if excluded["reconstructed_audit"] or excluded["missing_provenance"]:
            st.caption(
                "Scoreboard chỉ tính "
                f"{EVAL_MODE_FORWARD_FROZEN} có observation provenance "
                f"(observation_id hoặc khớp observations.csv). "
                f"Loại {excluded['reconstructed_audit']} dòng {EVAL_MODE_RECONSTRUCTED_AUDIT}, "
                f"{excluded['missing_provenance']} dòng thiếu provenance."
            )

        card = evaluate_genuine_forward_scorecard()
        if card.sessions == 0:
            st.info(
                "Chưa có phiên FORWARD_FROZEN thật nào đủ điều kiện scoreboard. "
                "Các dòng test hiện tại không được tính vào thành tích live."
            )
        else:
            st.caption(
                f"{card.sessions} phiên | {card.candidates} ứng viên | "
                f"Lift T3 Top10 mean: {_fmt_num(card.learning_lift_top10_mean_t3)}"
            )
            for top_n, b_slice, s_slice in (
                (5, card.baseline_top5, card.shadow_top5),
                (10, card.baseline_top10, card.shadow_top10),
                (20, card.baseline_top20, card.shadow_top20),
            ):
                st.markdown(f"**TOP {top_n}**")
                tbl = _scorecard_horizon_table(f"top{top_n}", b_slice, s_slice)
                st.dataframe(tbl, use_container_width=True, hide_index=True)

        # --- Movement cohort realized results ---
        st.markdown("#### Kết quả thực tế theo movement_class")
        if card.sessions == 0:
            st.caption("Chờ outcome T3/T5/T10 mature từ phiên forward thật.")
        else:
            _render_cohort_block("ACTIVE_PROMOTED", card.cohort_active_promoted)
            _render_cohort_block("ACTIVE_DEMOTED", card.cohort_active_demoted)
            _render_cohort_block("PASSIVE_MOVED", card.cohort_passive_moved)
            _render_cohort_block("UNCHANGED", card.cohort_unchanged)

        # --- Regime section ---
        st.markdown("#### Regime / Context")
        if genuine_joined.empty:
            st.info("Regime-specific evidence not mature yet.")
        else:
            exact_n = int((genuine_joined["RecallLevel"].astype(str) == RECALL_LEVEL_EXACT).sum())
            family_n = int((genuine_joined["RecallLevel"].astype(str) == RECALL_LEVEL_FAMILY).sum())
            global_n = int((genuine_joined["RecallLevel"].astype(str) == RECALL_LEVEL_GLOBAL).sum())
            if exact_n == 0 and family_n == 0:
                st.warning(
                    "Regime-specific evidence not mature yet. "
                    f"Chỉ có GLOBAL_DNA ({REGIME_LABEL_GLOBAL}) — "
                    "không chứng minh BOT thích ứng theo mùa thị trường."
                )
            else:
                contexts = (
                    genuine_joined["market_context_key"]
                    .astype(str)
                    .value_counts()
                    .head(5)
                    .index.tolist()
                )
                for ctx in contexts:
                    sub = genuine_joined[
                        genuine_joined["market_context_key"].astype(str) == str(ctx)
                    ]
                    levels = sub["RecallLevel"].astype(str).unique().tolist()
                    label = ctx
                    if levels == [RECALL_LEVEL_GLOBAL] or (
                        len(levels) == 1 and RECALL_LEVEL_GLOBAL in levels[0]
                    ):
                        label = f"{ctx}|{REGIME_LABEL_GLOBAL}"
                    st.caption(
                        f"Context `{label}` — "
                        f"{int(sub['session_date'].nunique())} phiên, {len(sub)} ứng viên"
                    )
            st.caption(
                f"EXACT {exact_n} | FAMILY {family_n} | "
                f"GLOBAL {global_n} ({REGIME_LABEL_GLOBAL})"
            )


__all__ = [
    "count_excluded_forward_rows",
    "evaluate_genuine_forward_scorecard",
    "filter_genuine_forward_ledger",
    "format_recall_level_display",
    "has_forward_observation_provenance",
    "load_genuine_forward_joined",
    "load_observation_session_lookup",
    "movement_class_counts",
    "prepare_live_shadow_frame",
    "render_shadow_observation_board",
]

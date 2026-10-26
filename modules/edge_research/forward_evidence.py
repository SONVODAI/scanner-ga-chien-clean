"""
Contemporaneous baseline, edge-level forward evidence, and health transitions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from modules.edge_research.contracts import (
    BASELINE_CALC_VERSION,
    BASELINE_TYPE_INSUFFICIENT,
    BASELINE_TYPE_SAME_STATE,
    BASELINE_TYPE_SAME_TRANSITION,
    EDGE_MEMORY_STATUS_ACTIVE,
    EDGE_MEMORY_STATUS_DECAYING,
    EDGE_MEMORY_STATUS_INVALIDATED,
    EDGE_VALIDATION_HISTORY_COLUMNS,
    HEALTH_FAILED,
    HEALTH_INSUFFICIENT_EVIDENCE,
    HEALTH_SUPPORTED,
    HEALTH_WEAKENED,
    HORIZON_STATUS_MATURE,
    VALIDATION_TYPE_FORWARD_HEALTH,
    VALIDATION_TYPE_STATE_TRANSITION,
)
from modules.edge_research.discovery import apply_condition
from modules.edge_research.episodes import segment_market_episodes
from modules.edge_research.forward_health_policy import DEFAULT_FORWARD_HEALTH_POLICY, ForwardHealthPolicy
from modules.edge_research.forward_maturity import HORIZON_N, lookup_horizon_outcome, resolve_session_calendar
from modules.edge_research.freeze import load_frozen_spec
from modules.edge_research.metrics import (
    RETURN_COLUMNS,
    compute_horizon_profile,
    compute_incremental_metrics,
    has_positive_incremental_evidence,
)
from modules.edge_research.oos_eval import clauses_from_frozen_spec
from modules.edge_research.storage import ensure_storage, read_ledger
from modules.edge_research.t0_universe import load_session_universe, load_t0_freeze


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _horizon_key(best_horizon: str) -> str:
    h = str(best_horizon or "T5").upper()
    return h if h in HORIZON_N else "T5"


def contemporaneous_baseline_for_birth(
    row: Mapping[str, Any],
    *,
    freeze_df: pd.DataFrame,
    sessions: Sequence[pd.Timestamp],
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
    outcomes_df: Optional[pd.DataFrame] = None,
    policy: ForwardHealthPolicy = DEFAULT_FORWARD_HEALTH_POLICY,
    spec=None,
) -> Dict[str, Any]:
    """
    Same-context contemporaneous universe at birth session F.

    SAME_TRANSITION does not fall back to SAME_STATE.
    Missing/too-small baseline is INSUFFICIENT, never a manufactured zero.
    """
    t0 = str(row.get("t0_trade_date") or row.get("t0_date") or "")[:10]
    horizon = _horizon_key(row.get("best_horizon") or (spec.best_horizon if spec is not None else "T5"))
    n = HORIZON_N[horizon]
    claimed = str(row.get("baseline_type") or (spec.baseline_type if spec is not None else "") or BASELINE_TYPE_SAME_TRANSITION)
    context_key = str(row.get("market_transition_t0") or (spec.market_transition if spec is not None else ""))
    empty = {
        "baseline_type": claimed,
        "baseline_context_key": context_key,
        "baseline_horizon": horizon,
        "baseline_n": 0,
        "baseline_median": None,
        "baseline_mean": None,
        "candidate_horizon_return": None,
        "incremental_return": None,
        "baseline_status": BASELINE_TYPE_INSUFFICIENT,
        "baseline_source": "contemporaneous_t0_universe",
        "baseline_calc_version": BASELINE_CALC_VERSION,
    }
    cand_ret = pd.to_numeric(row.get(f"{horizon.lower()}_return"), errors="coerce")
    if pd.isna(cand_ret):
        empty["baseline_status"] = "CANDIDATE_RETURN_PENDING"
        return empty
    empty["candidate_horizon_return"] = float(cand_ret)

    if claimed == BASELINE_TYPE_SAME_STATE:
        # Frozen claim is SAME_STATE only if the spec says so.
        pass
    elif claimed != BASELINE_TYPE_SAME_TRANSITION:
        claimed = BASELINE_TYPE_SAME_TRANSITION

    try:
        universe = load_session_universe(t0, freeze_df=freeze_df)
    except Exception:
        empty["baseline_status"] = "UNIVERSE_UNAVAILABLE"
        return empty

    frame = universe.frame.copy()
    if claimed == BASELINE_TYPE_SAME_TRANSITION:
        if "research_market_transition" in frame.columns:
            frame = frame[frame["research_market_transition"].astype(str) == context_key]
        # Births store current transition in market_transition_t0; freeze may lack the column
        # when injected. In that case the whole session F shares one market context.
    elif claimed == BASELINE_TYPE_SAME_STATE:
        state = str(row.get("market_state_t0") or "")
        if "research_market_state" in frame.columns and state:
            frame = frame[frame["research_market_state"].astype(str) == state]

    # Disjoint complement: stocks that do NOT satisfy the frozen clauses.
    if spec is not None:
        clauses = clauses_from_frozen_spec(spec)
        if clauses and not frame.empty:
            matched = apply_condition(frame, list(clauses))
            matched_syms = set(matched["symbol"].astype(str).str.upper()) if not matched.empty else set()
            frame = frame[~frame["symbol"].astype(str).str.upper().isin(matched_syms)]

    returns: List[float] = []
    for _, base_row in frame.iterrows():
        outcome = lookup_horizon_outcome(
            str(base_row.get("symbol") or ""),
            t0,
            n,
            sessions=sessions,
            ohlcv_by_symbol=ohlcv_by_symbol,
            outcomes_df=outcomes_df,
        )
        if outcome["status"] == HORIZON_STATUS_MATURE and outcome["return"] is not None:
            returns.append(float(outcome["return"]))

    if len(returns) < policy.min_baseline_n:
        empty["baseline_n"] = len(returns)
        empty["baseline_status"] = BASELINE_TYPE_INSUFFICIENT
        return empty

    series = pd.Series(returns, dtype=float)
    profile = compute_horizon_profile(series, horizon)
    inc = float(cand_ret) - float(profile.median_return)
    return {
        "baseline_type": claimed,
        "baseline_context_key": context_key,
        "baseline_horizon": horizon,
        "baseline_n": int(len(returns)),
        "baseline_median": float(profile.median_return) if profile.median_return is not None else None,
        "baseline_mean": float(profile.mean_return) if profile.mean_return is not None else None,
        "candidate_horizon_return": float(cand_ret),
        "incremental_return": inc,
        "baseline_status": "OK",
        "baseline_source": "contemporaneous_t0_universe",
        "baseline_calc_version": BASELINE_CALC_VERSION,
    }


def attach_baselines_to_matured_births(
    *,
    data_dir: Optional[Path] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    session_calendar: Optional[Sequence[str]] = None,
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
    outcomes_df: Optional[pd.DataFrame] = None,
    policy: ForwardHealthPolicy = DEFAULT_FORWARD_HEALTH_POLICY,
) -> Dict[str, Any]:
    from modules.edge_research.forward_ledger import persist_maturity_updates

    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_forward_ledger.csv", data_dir=root)
    if ledger.empty:
        return {"updated": 0}
    freeze = freeze_df
    if freeze is None:
        try:
            freeze = load_t0_freeze()
        except Exception:
            freeze = pd.DataFrame()
    sessions = resolve_session_calendar(
        session_calendar=session_calendar, freeze_df=freeze, ohlcv_by_symbol=ohlcv_by_symbol
    )
    updates: List[Dict[str, Any]] = []
    for _, row in ledger.iterrows():
        horizon = _horizon_key(row.get("best_horizon"))
        if str(row.get(f"{horizon.lower()}_status") or "") != HORIZON_STATUS_MATURE:
            continue
        if str(row.get("baseline_status") or "") == "OK" and str(row.get("incremental_return") or "") not in ("", "nan", "None"):
            continue
        spec = load_frozen_spec(str(row.get("hypothesis_id") or ""), root)
        baseline = contemporaneous_baseline_for_birth(
            row,
            freeze_df=freeze if freeze is not None else pd.DataFrame(),
            sessions=sessions,
            ohlcv_by_symbol=ohlcv_by_symbol,
            outcomes_df=outcomes_df,
            policy=policy,
            spec=spec,
        )
        patch = {"ledger_id": row.get("ledger_id")}
        patch.update(baseline)
        updates.append(patch)
    from modules.edge_research.forward_ledger import persist_maturity_updates as _persist

    _persist(updates, data_dir=root)
    return {"updated": len(updates)}


def _episode_id_for_date(dates_panel: pd.DataFrame, trade_date: str) -> str:
    if dates_panel.empty:
        return ""
    episodes = segment_market_episodes(dates_panel)
    target = str(trade_date)[:10]
    for ep in episodes:
        if target in set(ep.dates):
            return ep.episode_id
    return f"session:{target}"


def aggregate_forward_evidence(
    *,
    data_dir: Optional[Path] = None,
    freeze_df: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_forward_ledger.csv", data_dir=root)
    if ledger.empty:
        return []
    freeze = freeze_df
    if freeze is None:
        try:
            freeze = load_t0_freeze()
        except Exception:
            freeze = pd.DataFrame()

    summaries: List[Dict[str, Any]] = []
    for hid, group in ledger.groupby(ledger["hypothesis_id"].astype(str)):
        spec = load_frozen_spec(str(hid), root)
        best = _horizon_key(group.iloc[0].get("best_horizon") or (spec.best_horizon if spec else "T5"))
        prefix = best.lower()
        matured = group[group[f"{prefix}_status"].astype(str) == HORIZON_STATUS_MATURE]
        comparable = matured[matured["baseline_status"].astype(str) == "OK"] if "baseline_status" in matured.columns else matured.iloc[0:0]
        inc = pd.to_numeric(comparable.get("incremental_return"), errors="coerce").dropna() if not comparable.empty else pd.Series(dtype=float)
        cand = pd.to_numeric(matured.get(f"{prefix}_return"), errors="coerce").dropna()
        sessions = sorted({str(d)[:10] for d in matured.get("t0_trade_date", matured.get("t0_date", pd.Series(dtype=str))).astype(str)})
        symbols = sorted({str(s).upper() for s in matured.get("symbol", pd.Series(dtype=str)).astype(str) if s})
        date_counts = matured.groupby(matured["t0_trade_date"].astype(str).str[:10]).size() if not matured.empty else pd.Series(dtype=int)
        conc = float(date_counts.max() / len(matured)) if len(matured) else 0.0
        episode_ids = set()
        if freeze is not None and not freeze.empty and not matured.empty:
            mini = freeze.copy()
            if "research_market_transition" not in mini.columns:
                mini["research_market_transition"] = matured.iloc[0].get("market_transition_t0") or ""
            if "research_market_state" not in mini.columns:
                mini["research_market_state"] = matured.iloc[0].get("market_state_t0") or ""
            for d in sessions:
                episode_ids.add(_episode_id_for_date(mini, d))
        else:
            episode_ids = {f"session:{d}" for d in sessions}

        cand_profile = compute_horizon_profile(cand, best)
        # Baseline profile from per-row baseline medians is not the pooled baseline;
        # incremental is pooled from per-birth incremental_return.
        summaries.append(
            {
                "hypothesis_id": str(hid),
                "edge_id": str(group.iloc[0].get("edge_id") or (spec.edge_id if spec else "")),
                "best_horizon": best,
                "total_births": int(len(group)),
                "mature_t3": int((group.get("t3_status", pd.Series(dtype=str)).astype(str) == HORIZON_STATUS_MATURE).sum()) if "t3_status" in group.columns else 0,
                "mature_t5": int((group.get("t5_status", pd.Series(dtype=str)).astype(str) == HORIZON_STATUS_MATURE).sum()) if "t5_status" in group.columns else 0,
                "mature_t10": int((group.get("t10_status", pd.Series(dtype=str)).astype(str) == HORIZON_STATUS_MATURE).sum()) if "t10_status" in group.columns else 0,
                "mature_best_horizon": int(len(matured)),
                "comparable_n": int(len(comparable)),
                "forward_mean": cand_profile.mean_return,
                "forward_median": cand_profile.median_return,
                "forward_win_rate": cand_profile.win_rate_gt_0,
                "forward_incremental_median": float(inc.median()) if not inc.empty else None,
                "forward_incremental_mean": float(inc.mean()) if not inc.empty else None,
                "unique_symbols": len(symbols),
                "unique_sessions": len(sessions),
                "unique_episodes": len(episode_ids),
                "date_concentration": conc,
                "latest_birth_date": str(pd.Series(group["t0_trade_date"].astype(str)).max())[:10] if "t0_trade_date" in group.columns else "",
                "latest_mature_date": str(pd.Series(matured[f"{prefix}_matured_at"].astype(str)).max()) if not matured.empty else "",
                "sessions": sessions,
                "episode_ids": sorted(episode_ids),
            }
        )
    return summaries


def _append_validation_row(row: Dict[str, Any], data_dir: Path) -> bool:
    history = read_ledger("edge_validation_history.csv", data_dir=data_dir)
    vid = str(row.get("validation_id") or "")
    if not history.empty and "validation_id" in history.columns and vid:
        if (history["validation_id"].astype(str) == vid).any():
            return False
    aligned = {col: row.get(col, "") for col in EDGE_VALIDATION_HISTORY_COLUMNS}
    history = pd.concat([history, pd.DataFrame([aligned])], ignore_index=True)
    history.to_csv(data_dir / "edge_validation_history.csv", index=False)
    return True


def _fingerprint(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def decide_health_state(
    current_status: str,
    evidence: Mapping[str, Any],
    policy: ForwardHealthPolicy,
    *,
    new_unseen_evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Pure policy decision. Does not mutate memory."""
    n = int(evidence.get("comparable_n") or 0)
    sessions = int(evidence.get("unique_sessions") or 0)
    episodes = int(evidence.get("unique_episodes") or 0)
    conc = float(evidence.get("date_concentration") or 0.0)
    inc_med = evidence.get("forward_incremental_median")
    inc_mean = evidence.get("forward_incremental_mean")
    sufficient = (
        n >= policy.min_mature_best_horizon_n
        and sessions >= policy.min_independent_sessions
        and episodes >= policy.min_episodes
        and conc <= policy.max_date_concentration
    )
    current = str(current_status or EDGE_MEMORY_STATUS_ACTIVE).upper()

    if current == EDGE_MEMORY_STATUS_INVALIDATED:
        return {
            "status": EDGE_MEMORY_STATUS_INVALIDATED,
            "health_status": HEALTH_FAILED,
            "reason": "INVALIDATED identity remains dead; no automatic resurrection.",
            "sufficient": sufficient,
        }

    if not sufficient:
        return {
            "status": current if current in {EDGE_MEMORY_STATUS_ACTIVE, EDGE_MEMORY_STATUS_DECAYING} else EDGE_MEMORY_STATUS_ACTIVE,
            "health_status": HEALTH_INSUFFICIENT_EVIDENCE,
            "reason": (
                f"INSUFFICIENT_EVIDENCE under {policy.policy_id}: "
                f"comparable_n={n} sessions={sessions} episodes={episodes} concentration={conc:.2f}. "
                "Thin forward sample cannot invalidate an OOS-validated edge."
            ),
            "sufficient": False,
        }

    positive = (
        inc_med is not None
        and inc_mean is not None
        and float(inc_med) > 0
        and float(inc_mean) > 0
    )
    strongly_negative = (
        inc_med is not None
        and inc_mean is not None
        and float(inc_med) < 0
        and float(inc_mean) < 0
    )

    if current == EDGE_MEMORY_STATUS_DECAYING:
        if new_unseen_evidence:
            rec_n = int(new_unseen_evidence.get("comparable_n") or 0)
            rec_s = int(new_unseen_evidence.get("unique_sessions") or 0)
            rec_med = new_unseen_evidence.get("forward_incremental_median")
            rec_mean = new_unseen_evidence.get("forward_incremental_mean")
            if (
                rec_n >= policy.min_recovery_new_n
                and rec_s >= policy.min_recovery_sessions
                and rec_med is not None
                and rec_mean is not None
                and float(rec_med) > 0
                and float(rec_mean) > 0
            ):
                return {
                    "status": EDGE_MEMORY_STATUS_ACTIVE,
                    "health_status": HEALTH_SUPPORTED,
                    "reason": (
                        f"DECAYING recovered to ACTIVE from new unseen forward evidence "
                        f"(n={rec_n} sessions={rec_s} incremental median={float(rec_med):.3f}) "
                        f"under {policy.policy_id}."
                    ),
                    "sufficient": True,
                    "recovery": True,
                }
        if strongly_negative:
            return {
                "status": EDGE_MEMORY_STATUS_INVALIDATED,
                "health_status": HEALTH_FAILED,
                "reason": (
                    f"INVALIDATED: prospective {evidence.get('best_horizon')} evidence "
                    f"n={n} sessions={sessions} episodes={episodes} shows persistent negative "
                    f"incremental median={inc_med} mean={inc_mean} under {policy.policy_id}."
                ),
                "sufficient": True,
            }
        return {
            "status": EDGE_MEMORY_STATUS_DECAYING,
            "health_status": HEALTH_WEAKENED,
            "reason": "Remain DECAYING; recovery requires new unseen positive evidence.",
            "sufficient": True,
        }

    if strongly_negative:
        return {
            "status": EDGE_MEMORY_STATUS_INVALIDATED,
            "health_status": HEALTH_FAILED,
            "reason": (
                f"INVALIDATED because {n} prospectively born {evidence.get('best_horizon')} matches "
                f"across {sessions} sessions / {episodes} episodes have incremental median {inc_med} "
                f"and mean {inc_mean} versus contemporaneous baseline under {policy.policy_id}."
            ),
            "sufficient": True,
        }
    if not positive:
        return {
            "status": EDGE_MEMORY_STATUS_DECAYING,
            "health_status": HEALTH_WEAKENED,
            "reason": (
                f"DECAYING because forward {evidence.get('best_horizon')} evidence across "
                f"{sessions} independent sessions / {episodes} episodes no longer shows positive "
                f"incremental return (median={inc_med}); evidence is sufficient under {policy.policy_id}."
            ),
            "sufficient": True,
        }
    return {
        "status": EDGE_MEMORY_STATUS_ACTIVE,
        "health_status": HEALTH_SUPPORTED,
        "reason": (
            f"Remains ACTIVE because {n} prospectively born {evidence.get('best_horizon')} matches "
            f"across {sessions} sessions / {episodes} episodes have median incremental return "
            f"{inc_med} versus contemporaneous SAME_TRANSITION baseline under {policy.policy_id}."
        ),
        "sufficient": True,
    }


def apply_health_transitions(
    *,
    data_dir: Optional[Path] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    session_date: str = "",
    policy: ForwardHealthPolicy = DEFAULT_FORWARD_HEALTH_POLICY,
) -> Dict[str, Any]:
    from modules.edge_research.edge_memory import apply_memory_health_update

    root = ensure_storage(data_dir)
    summaries = aggregate_forward_evidence(data_dir=root, freeze_df=freeze_df)
    memory = read_ledger("edge_memory.csv", data_dir=root)
    transitions: List[Dict[str, Any]] = []
    now = _iso_now()
    by_hid = {str(s["hypothesis_id"]): s for s in summaries}

    if memory.empty:
        return {"evaluated": 0, "transitions": []}

    for idx, mem in memory.iterrows():
        hid = str(mem.get("hypothesis_id") or "")
        if not hid:
            continue
        status = str(mem.get("status") or "").upper()
        evidence = by_hid.get(hid) or {
            "hypothesis_id": hid,
            "best_horizon": mem.get("best_horizon") or "T5",
            "comparable_n": 0,
            "unique_sessions": 0,
            "unique_episodes": 0,
            "date_concentration": 0.0,
            "forward_incremental_median": None,
            "forward_incremental_mean": None,
            "total_births": 0,
            "mature_best_horizon": 0,
        }
        new_unseen = None
        decayed_at = str(mem.get("decayed_at") or "")
        if status == EDGE_MEMORY_STATUS_DECAYING and decayed_at and hid in by_hid:
            ledger = read_ledger("edge_forward_ledger.csv", data_dir=root)
            post = ledger[
                (ledger["hypothesis_id"].astype(str) == hid)
                & (ledger.get("born_at", pd.Series(dtype=str)).astype(str) > decayed_at)
            ]
            if not post.empty:
                best = _horizon_key(mem.get("best_horizon"))
                matured = post[post[f"{best.lower()}_status"].astype(str) == HORIZON_STATUS_MATURE]
                comparable = matured[matured["baseline_status"].astype(str) == "OK"] if "baseline_status" in matured.columns else matured
                inc = pd.to_numeric(comparable.get("incremental_return"), errors="coerce").dropna()
                new_unseen = {
                    "comparable_n": int(len(comparable)),
                    "unique_sessions": int(comparable["t0_trade_date"].astype(str).nunique()) if not comparable.empty else 0,
                    "forward_incremental_median": float(inc.median()) if not inc.empty else None,
                    "forward_incremental_mean": float(inc.mean()) if not inc.empty else None,
                }
        decision = decide_health_state(status, evidence, policy, new_unseen_evidence=new_unseen)
        apply_memory_health_update(
            hid,
            decision=decision,
            evidence=evidence,
            policy=policy,
            evaluated_at=now,
            data_dir=root,
        )
        fp = _fingerprint(
            {
                "hypothesis_id": hid,
                "session_date": session_date,
                "from": status,
                "to": decision["status"],
                "policy": policy.policy_id,
                "n": evidence.get("comparable_n"),
                "inc": evidence.get("forward_incremental_median"),
                "kind": VALIDATION_TYPE_FORWARD_HEALTH,
            }
        )
        _append_validation_row(
            {
                "validation_id": fp,
                "hypothesis_id": hid,
                "validation_type": VALIDATION_TYPE_FORWARD_HEALTH,
                "result": decision["status"],
                "validated_at": now,
                "edge_id": mem.get("edge_id"),
                "evaluated_at": now,
                "candidate_n": evidence.get("comparable_n"),
                "incremental_median": evidence.get("forward_incremental_median"),
                "incremental_mean": evidence.get("forward_incremental_mean"),
                "best_horizon": evidence.get("best_horizon"),
                "market_episode_count": evidence.get("unique_episodes"),
                "concentration_json": json.dumps(
                    {
                        "date_concentration": evidence.get("date_concentration"),
                        "unique_sessions": evidence.get("unique_sessions"),
                    }
                ),
                "threshold_policy_version": policy.policy_id,
                "reason": decision["reason"],
                "policy_version": policy.policy_id,
                "from_status": status,
                "to_status": decision["status"],
                "session_date": session_date,
                "evidence_json": json.dumps(evidence, default=str),
            },
            root,
        )
        if decision["status"] != status:
            tfp = _fingerprint(
                {
                    "hypothesis_id": hid,
                    "session_date": session_date,
                    "from": status,
                    "to": decision["status"],
                    "kind": VALIDATION_TYPE_STATE_TRANSITION,
                    "policy": policy.policy_id,
                }
            )
            _append_validation_row(
                {
                    "validation_id": tfp,
                    "hypothesis_id": hid,
                    "validation_type": VALIDATION_TYPE_STATE_TRANSITION,
                    "result": decision["status"],
                    "validated_at": now,
                    "edge_id": mem.get("edge_id"),
                    "evaluated_at": now,
                    "reason": decision["reason"],
                    "policy_version": policy.policy_id,
                    "from_status": status,
                    "to_status": decision["status"],
                    "session_date": session_date,
                    "evidence_json": json.dumps(evidence, default=str),
                },
                root,
            )
            transitions.append(
                {"hypothesis_id": hid, "from": status, "to": decision["status"], "reason": decision["reason"]}
            )
    path = root / "latest_edge_health.json"
    path.write_text(
        json.dumps(
            {"evaluated_at": now, "session_date": session_date, "summaries": summaries, "transitions": transitions},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return {"evaluated": int(len(memory)), "transitions": transitions, "summaries": summaries}

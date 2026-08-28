"""
Research-only counterfactual anti-context learning (Phase C).

Does NOT weaken Phase B exact-transition qualified matching.
Shadow observations never become QUALIFIED_MATCH births.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from modules.edge_research.contracts import (
    ANTI_CONTEXT_POLICY_VERSION,
    BASELINE_TYPE_SAME_TRANSITION,
    CONTEXT_COMPATIBLE,
    CONTEXT_INCOMPATIBLE,
    EDGE_ANTI_CONTEXT_COLUMNS,
    EDGE_SHADOW_OBSERVATION_COLUMNS,
    FORWARD_OUTCOME_PENDING,
    HORIZON_STATUS_MATURE,
    VALIDATION_TYPE_ANTI_CONTEXT,
)
from modules.edge_research.discovery import apply_condition
from modules.edge_research.forward_health_policy import DEFAULT_FORWARD_HEALTH_POLICY, ForwardHealthPolicy
from modules.edge_research.forward_maturity import HORIZON_N, lookup_horizon_outcome, resolve_session_calendar, target_trading_session
from modules.edge_research.metrics import compute_horizon_profile
from modules.edge_research.oos_eval import clauses_from_frozen_spec
from modules.edge_research.storage import ensure_storage, read_ledger
from modules.edge_research.t0_universe import load_session_universe

RESEARCH_SHADOW_LABEL = "RESEARCH SHADOW — NOT A QUALIFIED MATCH — NOT AUTOMATIC BUY"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(value: Any) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value or "").strip()[:10]
    return str(pd.Timestamp(ts).normalize().date())


def shadow_id_for(hypothesis_id: str, t0: str, symbol: str, context_y: str) -> str:
    key = f"{hypothesis_id}|{t0}|{str(symbol).upper().strip()}|{context_y}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def run_shadow_counterfactual_scan(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    market_context: Optional[Dict[str, str]] = None,
    session_calendar: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Observe frozen stock condition P in current context Y when Y is INCOMPATIBLE
    with the frozen claim. Writes research-only shadow rows.
    """
    root = ensure_storage(data_dir)
    current = str(
        (market_context or {}).get("research_market_transition")
        or (market_context or {}).get("market_transition")
        or ""
    )
    current_state = str(
        (market_context or {}).get("research_market_state")
        or (market_context or {}).get("market_state")
        or ""
    )
    if not current or "UNKNOWN" in current.upper():
        return {"ok": True, "reason": "NO_SHADOW_UNKNOWN_CONTEXT", "new_shadows": 0}
    try:
        universe = load_session_universe(trade_date, freeze_df=freeze_df)
    except Exception as exc:
        return {"ok": False, "reason": f"T0_UNIVERSE:{exc}", "new_shadows": 0}

    from modules.edge_research.future_recognition import evaluate_market_context, load_interpretable_active_edges

    loaded = load_interpretable_active_edges(root)
    existing = read_ledger("edge_shadow_observations.csv", data_dir=root)
    existing_ids = set(existing["shadow_id"].astype(str)) if not existing.empty and "shadow_id" in existing.columns else set()
    sessions = resolve_session_calendar(session_calendar=session_calendar, freeze_df=freeze_df)
    born_at = _iso_now()
    new_rows: List[Dict[str, Any]] = []

    for edge in loaded:
        if not edge.ok or edge.spec is None:
            continue
        verdict, _reason = evaluate_market_context(edge.spec, current, current_state)
        if verdict != CONTEXT_INCOMPATIBLE:
            continue
        clauses = clauses_from_frozen_spec(edge.spec)
        if not clauses:
            continue
        matched = apply_condition(universe.frame, list(clauses))
        for _, row in matched.iterrows():
            symbol = str(row.get("symbol") or "").upper().strip()
            sid = shadow_id_for(edge.spec.hypothesis_id, trade_date, symbol, current)
            if sid in existing_ids:
                continue
            existing_ids.add(sid)
            rec = {col: "" for col in EDGE_SHADOW_OBSERVATION_COLUMNS}
            rec.update(
                {
                    "shadow_id": sid,
                    "hypothesis_id": edge.spec.hypothesis_id,
                    "edge_id": edge.spec.edge_id,
                    "spec_hash": edge.spec.spec_hash,
                    "t0_trade_date": trade_date,
                    "symbol": symbol,
                    "context_y": current,
                    "market_state_t0": current_state,
                    "condition_key": edge.spec.condition_key,
                    "condition_text": edge.spec.condition_text,
                    "best_horizon": edge.spec.best_horizon,
                    "research_label": RESEARCH_SHADOW_LABEL,
                    "born_at": born_at,
                    "outcome_status": FORWARD_OUTCOME_PENDING,
                    "universe_count": universe.universe_count,
                }
            )
            for h, n in HORIZON_N.items():
                rec[f"{h.lower()}_target_date"] = target_trading_session(sessions, trade_date, n) or ""
                rec[f"{h.lower()}_status"] = "PENDING"
            new_rows.append(rec)

    if new_rows:
        existing = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
        existing.to_csv(root / "edge_shadow_observations.csv", index=False)
    return {
        "ok": True,
        "reason": "OK",
        "new_shadows": len(new_rows),
        "context_y": current,
        "research_only": True,
        "qualified_match": False,
    }


def mature_shadow_observations(
    session_date: str,
    *,
    data_dir: Optional[Path] = None,
    session_calendar: Optional[Sequence[str]] = None,
    freeze_df: Optional[pd.DataFrame] = None,
    ohlcv_by_symbol: Optional[Mapping[str, pd.DataFrame]] = None,
    outcomes_df: Optional[pd.DataFrame] = None,
    policy: ForwardHealthPolicy = DEFAULT_FORWARD_HEALTH_POLICY,
) -> Dict[str, Any]:
    root = ensure_storage(data_dir)
    shadows = read_ledger("edge_shadow_observations.csv", data_dir=root)
    if shadows.empty:
        return {"updated": 0}
    sessions = resolve_session_calendar(
        session_calendar=session_calendar, freeze_df=freeze_df, ohlcv_by_symbol=ohlcv_by_symbol
    )
    as_of = pd.Timestamp(session_date).normalize()
    now = _iso_now()
    changed = 0
    freeze = freeze_df
    if freeze is None:
        try:
            from modules.edge_research.t0_universe import load_t0_freeze

            freeze = load_t0_freeze()
        except Exception:
            freeze = pd.DataFrame()

    for idx, row in shadows.iterrows():
        t0 = _norm(row.get("t0_trade_date"))
        symbol = str(row.get("symbol") or "")
        best = str(row.get("best_horizon") or "T5").upper()
        n = HORIZON_N.get(best, 5)
        for h, hn in HORIZON_N.items():
            status_col = f"{h.lower()}_status"
            if str(row.get(status_col) or "") == HORIZON_STATUS_MATURE:
                continue
            target = target_trading_session(sessions, t0, hn)
            if not target or pd.Timestamp(target).normalize() > as_of:
                continue
            outcome = lookup_horizon_outcome(
                symbol, t0, hn, sessions=sessions, ohlcv_by_symbol=ohlcv_by_symbol, outcomes_df=outcomes_df
            )
            if outcome["status"] != HORIZON_STATUS_MATURE:
                continue
            shadows.at[idx, status_col] = HORIZON_STATUS_MATURE
            shadows.at[idx, f"{h.lower()}_return"] = outcome["return"]
            shadows.at[idx, f"{h.lower()}_matured_at"] = now
            shadows.at[idx, f"{h.lower()}_target_date"] = target
            changed += 1
        # contemporaneous baseline in context Y at F
        if str(shadows.at[idx, f"{best.lower()}_status"]) == HORIZON_STATUS_MATURE and str(row.get("baseline_status") or "") != "OK":
            cand = pd.to_numeric(shadows.at[idx, f"{best.lower()}_return"], errors="coerce")
            if pd.notna(cand) and freeze is not None and not freeze.empty:
                try:
                    uni = load_session_universe(t0, freeze_df=freeze)
                    frame = uni.frame
                    returns: List[float] = []
                    for _, brow in frame.iterrows():
                        if str(brow.get("symbol")).upper() == symbol.upper():
                            continue
                        out = lookup_horizon_outcome(
                            str(brow.get("symbol")),
                            t0,
                            n,
                            sessions=sessions,
                            ohlcv_by_symbol=ohlcv_by_symbol,
                            outcomes_df=outcomes_df,
                        )
                        if out["status"] == HORIZON_STATUS_MATURE and out["return"] is not None:
                            returns.append(float(out["return"]))
                    if len(returns) >= policy.min_baseline_n:
                        prof = compute_horizon_profile(pd.Series(returns), best)
                        shadows.at[idx, "baseline_n"] = len(returns)
                        shadows.at[idx, "baseline_median"] = prof.median_return
                        shadows.at[idx, "incremental_return"] = float(cand) - float(prof.median_return or 0)
                        shadows.at[idx, "baseline_status"] = "OK"
                    else:
                        shadows.at[idx, "baseline_n"] = len(returns)
                        shadows.at[idx, "baseline_status"] = "INSUFFICIENT"
                except Exception:
                    shadows.at[idx, "baseline_status"] = "UNIVERSE_UNAVAILABLE"
    shadows.to_csv(root / "edge_shadow_observations.csv", index=False)
    return {"updated": changed}


def learn_anti_context(
    *,
    data_dir: Optional[Path] = None,
    policy: ForwardHealthPolicy = DEFAULT_FORWARD_HEALTH_POLICY,
    session_date: str = "",
) -> Dict[str, Any]:
    """
    Evidence-derived anti-context. One observation is never enough.
    Does not hard-code market labels.
    """
    root = ensure_storage(data_dir)
    shadows = read_ledger("edge_shadow_observations.csv", data_dir=root)
    learned = 0
    if shadows.empty:
        return {"learned": 0}
    anti = read_ledger("edge_anti_context.csv", data_dir=root)
    existing_ids = set(anti["anti_context_id"].astype(str)) if not anti.empty and "anti_context_id" in anti.columns else set()
    now = _iso_now()
    new_rows: List[Dict[str, Any]] = []

    keys = shadows.groupby([shadows["hypothesis_id"].astype(str), shadows["context_y"].astype(str)])
    for (hid, context_y), group in keys:
        comparable = group[group["baseline_status"].astype(str) == "OK"]
        inc = pd.to_numeric(comparable.get("incremental_return"), errors="coerce").dropna()
        sessions = comparable["t0_trade_date"].astype(str).nunique() if not comparable.empty else 0
        n = int(len(comparable))
        if n < policy.anti_context_min_n or sessions < policy.anti_context_min_sessions:
            continue
        if inc.empty or not (float(inc.median()) < 0 and float(inc.mean()) < 0):
            continue
        aid = hashlib.sha256(f"{hid}|{context_y}|{ANTI_CONTEXT_POLICY_VERSION}".encode()).hexdigest()[:16]
        if aid in existing_ids:
            continue
        reason = (
            f"Learned anti-context {context_y} for hypothesis {hid}: {n} shadow observations "
            f"across {sessions} sessions have incremental median {float(inc.median()):.3f} "
            f"under {ANTI_CONTEXT_POLICY_VERSION}. RESEARCH ONLY — not a qualified match rule."
        )
        rec = {col: "" for col in EDGE_ANTI_CONTEXT_COLUMNS}
        rec.update(
            {
                "anti_context_id": aid,
                "hypothesis_id": hid,
                "edge_id": group.iloc[0].get("edge_id"),
                "spec_hash": group.iloc[0].get("spec_hash"),
                "condition_key": group.iloc[0].get("condition_key"),
                "context_y": context_y,
                "sample_n": n,
                "baseline_n": int(pd.to_numeric(comparable["baseline_n"], errors="coerce").median()) if "baseline_n" in comparable.columns else 0,
                "incremental_median": float(inc.median()),
                "incremental_mean": float(inc.mean()),
                "unique_sessions": int(sessions),
                "unique_episodes": int(sessions),
                "evidence_status": "LEARNED",
                "learned_at": now,
                "policy_version": ANTI_CONTEXT_POLICY_VERSION,
                "reason": reason,
                "evidence_json": json.dumps({"n": n, "sessions": int(sessions)}, default=str),
            }
        )
        new_rows.append(rec)
        existing_ids.add(aid)
        learned += 1
        from modules.edge_research.forward_evidence import _append_validation_row

        _append_validation_row(
            {
                "validation_id": aid,
                "hypothesis_id": hid,
                "validation_type": VALIDATION_TYPE_ANTI_CONTEXT,
                "result": "LEARNED",
                "validated_at": now,
                "reason": reason,
                "policy_version": ANTI_CONTEXT_POLICY_VERSION,
                "session_date": session_date,
                "evidence_json": rec["evidence_json"],
            },
            root,
        )

    if new_rows:
        anti = pd.concat([anti, pd.DataFrame(new_rows)], ignore_index=True)
        anti.to_csv(root / "edge_anti_context.csv", index=False)
    return {"learned": learned, "policy": ANTI_CONTEXT_POLICY_VERSION}


def load_anti_contexts(data_dir: Optional[Path] = None) -> pd.DataFrame:
    return read_ledger("edge_anti_context.csv", data_dir=data_dir)


def anti_context_for(hypothesis_id: str, context: str, data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    df = load_anti_contexts(data_dir)
    if df.empty:
        return None
    hit = df[
        (df["hypothesis_id"].astype(str) == str(hypothesis_id))
        & (df["context_y"].astype(str) == str(context))
        & (df["evidence_status"].astype(str) == "LEARNED")
    ]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()

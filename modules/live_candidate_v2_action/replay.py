"""Deterministic V2 Action Layer replay.

Uses freeze_ledger / sidecar nomination as-of + historical completed 5m parquet.
Does not reconstruct first_seen from Elite CSV save time.
Does not use future T3/T5/T10 to tune thresholds.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from modules.intraday_memory.storage import load_session
from modules.intraday_pxv_v1.candidates import CandidateEvent
from modules.intraday_pxv_v1.constants import OVERLAY_TRUTH_CANONICAL, OVERLAY_TRUTH_RETROSPECTIVE
from modules.intraday_pxv_v1.debounce import PublishedDebouncer
from modules.intraday_pxv_v1.features import FAM_EXPANSION, FAM_PXV, FAM_SELL, PXV_SELL_EXP
from modules.intraday_pxv_v1.interpret import interpret_asof
from modules.intraday_pxv_v1.time_contract import asof_allowed, parse_legal_ts, resolve_legal_existence
from modules.live_candidate.calendar import as_vn
from modules.live_camera_shadow.bars import completed_to_overlay, is_completed_bar
from modules.live_candidate_v2_action.state import (
    ActionResult,
    BarEvidence,
    FrozenNomination,
    evaluate_shadow_action,
    nomination_from_mapping,
)
from modules.live_candidate_v2_camera.feed_pass import v2_event_reason, v2_nomination_source
from modules.live_candidate_v2_camera.observe import observe_close_vs_ref
from modules.live_candidate_v2_camera.sidecar import (
    freeze_records_from_document,
    load_sidecar_document,
)

BAR_MINUTES = 5


def _fam_sell(features: Mapping[str, Any]) -> bool:
    raw = features.get(FAM_SELL)
    if raw is True:
        return True
    if isinstance(raw, Mapping):
        return bool(raw.get("state"))
    return False


def _expansion_state(features: Mapping[str, Any]) -> str | None:
    fam = features.get(FAM_EXPANSION)
    if isinstance(fam, Mapping):
        val = fam.get("state")
        return str(val) if val is not None else None
    return None


def _pxv_state(features: Mapping[str, Any]) -> str | None:
    fam = features.get(FAM_PXV)
    if isinstance(fam, Mapping):
        val = fam.get("state")
        return str(val) if val is not None else None
    return None


def bar_evidence_from_interpret(
    nom: FrozenNomination | Mapping[str, Any],
    *,
    bar: Mapping[str, Any],
    ledger: Any,
    published: str,
    observe: Mapping[str, Any],
    overlay_truth_class: str,
) -> BarEvidence:
    features = getattr(ledger, "features", None) or {}
    pxv = _pxv_state(features)
    bar_ts = bar.get("bar_ts") or bar.get("timestamp") or getattr(ledger, "asof", None)
    if not isinstance(bar_ts, datetime):
        bar_ts = pd.Timestamp(bar_ts).to_pydatetime()
    bar_ts = as_vn(bar_ts)
    return BarEvidence(
        bar_ts=bar_ts,
        asof=bar_ts,
        completed=True,
        unfinished=False,
        open=bar.get("open"),
        high=bar.get("high"),
        low=bar.get("low"),
        close=bar.get("close"),
        volume=bar.get("volume"),
        close_canonical=observe.get("close_canonical"),
        reference_kind=observe.get("reference_kind"),
        reference_value=observe.get("reference_value"),
        reference_canonical=observe.get("reference_canonical"),
        close_vs_ref=observe.get("close_vs_ref"),
        close_vs_ref_pct=observe.get("close_vs_ref_pct"),
        reference_state=str(observe.get("reference_state") or ""),
        data_state=str(getattr(ledger, "data_state", "") or ""),
        gate_reason=str(getattr(ledger, "gate_reason", "") or ""),
        raw_evidence=str(getattr(ledger, "raw_evidence", "") or ""),
        published_evidence=str(published or ""),
        volume_expansion_state=_expansion_state(features),
        price_volume_state=pxv,
        fam_sell=_fam_sell(features),
        sell_expansion=pxv == PXV_SELL_EXP,
        overlay_truth_class=overlay_truth_class,
        overlay_applied=bool(getattr(ledger, "overlay_applied", False)),
        chronology_legal=True,
    )


def _candidate_event(nom: FrozenNomination, session: date) -> CandidateEvent:
    return CandidateEvent(
        symbol=nom.symbol,
        session=session,
        candidate_reason=v2_event_reason(
            {
                "candidate_reason": nom.nomination_reason,
                "nomination_reason": nom.nomination_reason,
            }
        ),
        candidate_ts=nom.candidate_first_seen_ts,
        bot_context=nom.setup,
        source=v2_nomination_source({"nomination_source": nom.source, "source": nom.source}),
        candidate_first_seen_ts=nom.candidate_first_seen_ts,
        candidate_updated_ts=nom.candidate_first_seen_ts,
    )


def overlay_from_records(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    completed = []
    for rec in records:
        ts = rec.get("bar_ts") or rec.get("timestamp")
        if not isinstance(ts, datetime):
            ts = pd.Timestamp(ts).to_pydatetime()
        completed.append(
            {
                "symbol": str(rec.get("symbol") or "").upper(),
                "bar_ts": as_vn(ts),
                "observed_at": rec.get("observed_at") or rec.get("collected_at"),
                "open": rec.get("open"),
                "high": rec.get("high"),
                "low": rec.get("low"),
                "close": rec.get("close"),
                "volume": rec.get("volume"),
                "source": rec.get("source") or "replay",
                "data_quality": rec.get("data_quality") or rec.get("quality_flag") or "ok",
                "session_date": rec.get("session_date") or rec.get("session"),
            }
        )
    return completed_to_overlay(completed)


def legal_completed_from_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    now: datetime,
) -> list[dict[str, Any]]:
    """Completed 5m rows only. Unfinished and future bars are dropped."""
    if frame is None or frame.empty:
        return []
    now_l = as_vn(now)
    work = frame.copy()
    if "symbol" in work.columns:
        work = work[work["symbol"].astype(str).str.upper() == symbol.upper()]
    if work.empty:
        return []
    ts_col = "timestamp" if "timestamp" in work.columns else "bar_ts"
    work[ts_col] = pd.to_datetime(work[ts_col], errors="coerce")
    out: list[dict[str, Any]] = []
    for _, row in work.sort_values(ts_col).iterrows():
        ts = row[ts_col]
        if pd.isna(ts):
            continue
        bar_ts = as_vn(ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts)
        if not is_completed_bar(bar_ts, now_l):
            continue
        out.append(
            {
                "symbol": symbol.upper(),
                "bar_ts": bar_ts,
                "timestamp": bar_ts,
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "source": row.get("source") or "replay",
                "data_quality": row.get("quality_flag") or row.get("data_quality") or "ok",
                "session_date": row.get("session_date"),
                "overlay_applied": bool(row.get("overlay_applied", False)),
            }
        )
    return out


def interpret_legal_history(
    nom: FrozenNomination,
    legal_completed: Sequence[Mapping[str, Any]],
    *,
    overlay: pd.DataFrame | None = None,
    tod_qualified_sessions: int = 0,
    overlay_truth_class: str = OVERLAY_TRUTH_CANONICAL,
) -> list[BarEvidence]:
    """Walk legal completed bars with a fresh debouncer — live and replay share this."""
    if parse_legal_ts(nom.candidate_first_seen_ts) is None:
        return []
    session = date.fromisoformat(str(nom.session)[:10]) if nom.session else as_vn(
        legal_completed[0]["bar_ts"]
    ).date()
    event = _candidate_event(nom, session)
    legal = resolve_legal_existence(event)
    overlay_df = overlay if overlay is not None else overlay_from_records(legal_completed)
    if overlay_df is None or overlay_df.empty:
        return []
    eligible = parse_legal_ts(nom.eligible_from)
    debouncer = PublishedDebouncer()
    bars: list[BarEvidence] = []
    nom_map = {
        "observation_reference": nom.observation_reference or nom.required_ref,
        "ema9_at_first_seen": nom.ema9_at_first_seen,
        "breakout_ref_at_first_seen": nom.breakout_ref_at_first_seen,
    }
    for rec in legal_completed:
        bar_ts = rec["bar_ts"]
        if not asof_allowed(bar_ts, legal):
            continue
        if eligible is not None and bar_ts < eligible:
            continue
        row = interpret_asof(
            overlay_df,
            asof=bar_ts,
            candidate=event,
            tod_store=None,
            tod_qualified_sessions=tod_qualified_sessions,
        )
        published, _why = debouncer.step(row.raw_evidence)
        row.published_evidence = published
        obs = observe_close_vs_ref(nom_map, rec.get("close"))
        truth = overlay_truth_class
        if rec.get("overlay_applied") or row.overlay_applied:
            truth = OVERLAY_TRUTH_RETROSPECTIVE
        bars.append(
            bar_evidence_from_interpret(
                nom,
                bar=rec,
                ledger=row,
                published=published,
                observe=obs,
                overlay_truth_class=truth,
            )
        )
    return bars


def replay_shadow_action(
    nomination: FrozenNomination | Mapping[str, Any],
    bars: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    overlay_truth_class: str = OVERLAY_TRUTH_CANONICAL,
    observed: bool = True,
    observation_reason: str = "",
    tod_qualified_sessions: int = 0,
) -> ActionResult:
    """Replay one nomination against completed 5m history."""
    nom = nomination if isinstance(nomination, FrozenNomination) else nomination_from_mapping(nomination)
    if isinstance(bars, pd.DataFrame):
        records = legal_completed_from_frame(bars, symbol=nom.symbol, now=now)
        overlay = None
        if not bars.empty and "timestamp" in bars.columns:
            overlay = bars.copy()
            if "bar_source" not in overlay.columns:
                overlay["bar_source"] = "replay"
            if "overlay_applied" not in overlay.columns:
                overlay["overlay_applied"] = False
    else:
        records = [
            r
            for r in bars
            if is_completed_bar(
                as_vn(r["bar_ts"] if isinstance(r.get("bar_ts"), datetime) else pd.Timestamp(r.get("bar_ts")).to_pydatetime()),
                as_vn(now),
            )
        ]
        overlay = None
    history = interpret_legal_history(
        nom,
        records,
        overlay=overlay,
        tod_qualified_sessions=tod_qualified_sessions,
        overlay_truth_class=overlay_truth_class,
    )
    return evaluate_shadow_action(
        nom,
        history,
        now=now,
        overlay_truth_class=overlay_truth_class,
        observed=observed,
        observation_reason=observation_reason,
    )


def apply_freeze_ledger(
    row: Mapping[str, Any],
    ledger: Sequence[Any],
) -> dict[str, Any]:
    """Prefer freeze_ledger first_seen / refs over any Elite CSV save clock."""
    out = dict(row)
    symbol = str(out.get("symbol") or "").strip().upper()
    session = str(out.get("session") or "").strip()
    for rec in ledger or ():
        rec_sym = getattr(rec, "symbol", None) or (rec.get("symbol") if isinstance(rec, Mapping) else "")
        rec_sess = getattr(rec, "session", None) or (rec.get("session") if isinstance(rec, Mapping) else "")
        if str(rec_sym).upper() == symbol and str(rec_sess) == session:
            first = getattr(rec, "candidate_first_seen_ts", None) or (
                rec.get("candidate_first_seen_ts") if isinstance(rec, Mapping) else None
            )
            if first:
                out["candidate_first_seen_ts"] = first
            for key in ("price_at_first_seen", "ema9_at_first_seen", "breakout_ref_at_first_seen"):
                val = getattr(rec, key, None) if not isinstance(rec, Mapping) else rec.get(key)
                if val is not None:
                    out[key] = val
            break
    return out


def replay_sidecar_session(
    sidecar_path: Path,
    *,
    now: datetime,
    camera_root: Path | None = None,
    parquet: pd.DataFrame | None = None,
    session: date | None = None,
    overlay_truth_class: str = OVERLAY_TRUTH_CANONICAL,
) -> list[ActionResult]:
    """Replay every current-session sidecar nomination against parquet."""
    doc = load_sidecar_document(Path(sidecar_path))
    if doc is None:
        return []
    now_l = as_vn(now)
    sess = session or now_l.date()
    ledger = freeze_records_from_document(doc)
    rows = [r for r in (doc.get("rows") or []) if isinstance(r, Mapping)]
    frame = parquet
    if frame is None and camera_root is not None:
        frame = load_session(Path(camera_root), sess)
    results: list[ActionResult] = []
    for raw in rows:
        if str(raw.get("session") or "") != sess.isoformat():
            continue
        rec = apply_freeze_ledger(raw, ledger)
        # Never accept Elite CSV `time` as first_seen.
        if "time" in rec and rec.get("candidate_first_seen_ts") == rec.get("time"):
            rec = dict(rec)
        nom = nomination_from_mapping(rec)
        if frame is None or frame.empty:
            results.append(
                evaluate_shadow_action(
                    nom,
                    [],
                    now=now_l,
                    observed=False,
                    observation_reason="MISSING_CAMERA",
                )
            )
            continue
        results.append(
            replay_shadow_action(
                nom,
                frame,
                now=now_l,
                overlay_truth_class=overlay_truth_class,
            )
        )
    return results

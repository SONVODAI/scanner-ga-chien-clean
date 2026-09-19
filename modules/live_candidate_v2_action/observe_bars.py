"""Live/replay shared bar walk. No Brain A. No sidecar writer."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from modules.intraday_pxv_v1.candidates import CandidateEvent
from modules.intraday_pxv_v1.constants import OVERLAY_TRUTH_CANONICAL, OVERLAY_TRUTH_RETROSPECTIVE
from modules.intraday_pxv_v1.debounce import PublishedDebouncer
from modules.intraday_pxv_v1.features import FAM_EXPANSION, FAM_PXV, FAM_SELL, PXV_SELL_EXP
from modules.intraday_pxv_v1.interpret import interpret_asof
from modules.intraday_pxv_v1.time_contract import asof_allowed, parse_legal_ts, resolve_legal_existence
from modules.live_candidate.calendar import as_vn
from modules.live_camera_shadow.bars import completed_to_overlay
from modules.live_candidate_v2_action.state import BarEvidence, FrozenNomination
from modules.live_candidate_v2_camera.feed_pass import v2_event_reason, v2_nomination_source
from modules.live_candidate_v2_camera.observe import observe_close_vs_ref


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

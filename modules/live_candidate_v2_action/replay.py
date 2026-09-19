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
from modules.intraday_pxv_v1.constants import OVERLAY_TRUTH_CANONICAL
from modules.live_candidate.calendar import as_vn
from modules.live_camera_shadow.bars import is_completed_bar
from modules.live_candidate_v2_action.observe_bars import (
    interpret_legal_history,
    legal_completed_from_frame,
)
from modules.live_candidate_v2_action.state import (
    ActionResult,
    FrozenNomination,
    evaluate_shadow_action,
    nomination_from_mapping,
)
from modules.live_candidate_v2_camera.sidecar import (
    freeze_records_from_document,
    load_sidecar_document,
)

BAR_MINUTES = 5


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
        records = legal_completed_from_frame(bars, symbol=nom.symbol, now=now, source="replay")
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

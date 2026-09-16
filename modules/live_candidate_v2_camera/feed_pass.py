"""Minimum LiveShadowFeed pass-through for V2 sidecar rows.

Does not change interpret_asof. Does not default V2 rows to BUY ELITE.
"""

from __future__ import annotations

from typing import Any, Mapping

from modules.live_candidate_v2_camera.observe import observe_close_vs_ref, pxv_implies_buy

V2_MARKER = "v2_camera"


def is_v2_camera_row(rec: Mapping[str, Any] | None) -> bool:
    if not rec:
        return False
    if rec.get(V2_MARKER) is True:
        return True
    if rec.get("candidate_is_buy") is False and rec.get("observation_intent"):
        return True
    return False


def v2_event_reason(rec: Mapping[str, Any]) -> str:
    """Never fall back to BUY ELITE for V2 Camera rows."""
    return str(rec.get("candidate_reason") or rec.get("nomination_reason") or "").strip()


def v2_nomination_source(rec: Mapping[str, Any]) -> str:
    return str(rec.get("nomination_source") or rec.get("source") or "").strip()


def v2_evidence_overlay(
    rec: Mapping[str, Any],
    *,
    close: object,
    camera_session: str,
    feed_source: str = "live_shadow",
) -> dict[str, Any]:
    """Fields merged onto a V2 evidence row. candidate_is_buy stays false."""
    obs = observe_close_vs_ref(rec, close)
    published = rec.get("published_evidence")
    return {
        V2_MARKER: True,
        "nomination_session": str(rec.get("session") or ""),
        "camera_session": camera_session,
        "nomination_source": v2_nomination_source(rec),
        "source": v2_nomination_source(rec),
        "feed_source": feed_source,
        "setup": str(rec.get("setup") or rec.get("group") or ""),
        "group": str(rec.get("group") or rec.get("setup") or ""),
        "observation_intent": str(rec.get("observation_intent") or ""),
        "observation_reference": str(rec.get("observation_reference") or ""),
        "price_at_first_seen": rec.get("price_at_first_seen"),
        "ema9_at_first_seen": rec.get("ema9_at_first_seen"),
        "breakout_ref_at_first_seen": rec.get("breakout_ref_at_first_seen"),
        "source_action": str(rec.get("source_action") or ""),
        "source_reason": str(rec.get("source_reason") or ""),
        "nomination_reason": str(rec.get("nomination_reason") or rec.get("candidate_reason") or ""),
        "candidate_reason": v2_event_reason(rec),
        "elite_buy_grade": str(rec.get("elite_buy_grade") or ""),
        "market_real": rec.get("market_real"),
        "market_permission": str(rec.get("market_permission") or ""),
        "provenance": list(rec.get("provenance") or []),
        "candidate_is_buy": False,
        "alert_eligible": False,
        "pxv_implies_buy": pxv_implies_buy(published),
        **obs,
    }

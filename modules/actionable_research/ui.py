"""Read-only Streamlit view of fusion artifacts. Does not produce scientific data."""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.actionable_research.contracts import AUTHORITY_LABEL, NO_INTEREST_VI
from modules.actionable_research.paths import FusionPaths, read_json


def load_latest_fusion_view(*, paths: Optional[FusionPaths] = None) -> Dict[str, Any]:
    paths = paths or FusionPaths()
    latest = read_json(paths.latest_path())
    if not latest:
        return {
            "available": False,
            "authority": AUTHORITY_LABEL,
            "headline_vi": "Chưa có artifact Actionable Research Fusion.",
        }
    artifact = latest.get("artifact") if isinstance(latest.get("artifact"), dict) else latest
    return {
        "available": True,
        "authority": AUTHORITY_LABEL,
        "trade_date": latest.get("trade_date") or artifact.get("trade_date"),
        "session_status": latest.get("session_status") or artifact.get("session_status"),
        "headline_vi": artifact.get("headline_vi") or latest.get("headline_vi") or NO_INTEREST_VI,
        "notable_count": artifact.get("notable_count") or latest.get("notable_count") or 0,
        "surfaced_symbols": artifact.get("surfaced_symbols") or [],
        "records": artifact.get("records") or [],
        "camera_cutoff_timestamp": latest.get("camera_cutoff_timestamp")
        or artifact.get("camera_cutoff_timestamp"),
        "idempotent_replay": latest.get("idempotent_replay"),
        "artifact_path": str(paths.latest_path()),
    }


def render_actionable_research_panel(st: Any, *, paths: Optional[FusionPaths] = None) -> Dict[str, Any]:
    view = load_latest_fusion_view(paths=paths)
    st.markdown("### ACTIONABLE RESEARCH FUSION")
    st.caption(
        "RESEARCH ONLY — dung hợp bằng chứng Market / Stock / ACTIVE edge / Camera / Foreign. "
        "Không phải lệnh BUY. Thiếu dữ liệu = UNKNOWN, không phải yếu."
    )
    if not view.get("available"):
        st.info(view.get("headline_vi"))
        return view
    c1, c2, c3 = st.columns(3)
    c1.metric("Session", view.get("trade_date") or "—")
    c2.metric("Status", view.get("session_status") or "—")
    c3.metric("Notable", view.get("notable_count") or 0)
    if view.get("camera_cutoff_timestamp"):
        st.caption(f"Camera PIT cutoff: `{view['camera_cutoff_timestamp']}`")
    st.markdown(view.get("headline_vi") or NO_INTEREST_VI)
    notable = [
        r
        for r in (view.get("records") or [])
        if isinstance(r, dict) and r.get("notable")
    ]
    notable.sort(key=lambda r: (r.get("presentation_rank", 99), r.get("symbol") or ""))
    for rec in notable[:20]:
        st.markdown(
            f"**{rec.get('symbol')}** · {rec.get('interest_level')} · "
            f"edge=`{rec.get('edge_status')}` · mf=`{rec.get('money_flow_status')}` · "
            f"ff=`{rec.get('foreign_flow_status')}`  \n"
            f"{rec.get('evidence_summary')}"
        )
    return view

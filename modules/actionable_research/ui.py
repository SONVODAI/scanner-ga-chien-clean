"""Read-only Streamlit view of fusion artifacts. Speaks selectively."""

from __future__ import annotations

from typing import Any, Dict, Optional

from modules.actionable_research.contracts import AUTHORITY_LABEL, NO_INTEREST_VI, SPEAK_POLICY
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
    observations = artifact.get("observations") or [
        r for r in (artifact.get("records") or []) if isinstance(r, dict) and r.get("notable")
    ]
    return {
        "available": True,
        "authority": AUTHORITY_LABEL,
        "speak_policy": artifact.get("speak_policy") or latest.get("speak_policy") or SPEAK_POLICY,
        "trade_date": latest.get("trade_date") or artifact.get("trade_date"),
        "session_status": latest.get("session_status") or artifact.get("session_status"),
        "headline_vi": artifact.get("headline_vi") or latest.get("headline_vi") or NO_INTEREST_VI,
        "notable_count": artifact.get("notable_count") or latest.get("notable_count") or 0,
        "scanned_count": (artifact.get("scan") or {}).get("scanned_count")
        or latest.get("scanned_count")
        or 0,
        "surfaced_symbols": artifact.get("surfaced_symbols") or [],
        "observations": observations,
        "records": observations,
        "scan": artifact.get("scan") or {},
        "camera_cutoff_timestamp": latest.get("camera_cutoff_timestamp")
        or artifact.get("camera_cutoff_timestamp"),
        "idempotent_replay": latest.get("idempotent_replay"),
        "artifact_path": str(paths.latest_path()),
    }


def _family_line(rec: Dict[str, Any]) -> str:
    edge = rec.get("edge_status") or "UNKNOWN"
    activity = rec.get("activity_status") or "UNKNOWN"
    ff = rec.get("foreign_flow_status") or "UNKNOWN"
    ff_timing = rec.get("foreign_timing") or "UNKNOWN"
    sweet = rec.get("sweetspot_status") or "NONE"
    missing = rec.get("missing_evidence") or []
    parts = [
        f"ACTIVE EDGE=`{edge}`",
        f"INTRADAY ACTIVITY=`{activity}`",
        f"FOREIGN FLOW EOD=`{ff}` (timing=`{ff_timing}`)",
    ]
    if sweet and sweet not in {"NONE", "UNAVAILABLE"}:
        parts.append(f"LEGACY AUXILIARY=`{sweet}`")
    if missing:
        parts.append("UNKNOWN=`" + ",".join(str(m) for m in missing) + "`")
    return " · ".join(parts)


def render_actionable_research_panel(st: Any, *, paths: Optional[FusionPaths] = None) -> Dict[str, Any]:
    view = load_latest_fusion_view(paths=paths)
    st.markdown("### ACTIONABLE RESEARCH FUSION")
    st.caption(
        "SCAN BROADLY → SPEAK SELECTIVELY. RESEARCH ONLY — không có thẩm quyền BUY. "
        "Quét toàn bộ universe; chỉ nói khi có quan sát đáng chú ý. "
        "Camera đo hoạt động/giá trị giao dịch ước tính (close×volume), không phải dòng tiền vào/ra. "
        "Foreign flow hiện tại là EOD. Thiếu dữ liệu = UNKNOWN."
    )
    if not view.get("available"):
        st.info(view.get("headline_vi"))
        return view
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Session", view.get("trade_date") or "—")
    c2.metric("Status", view.get("session_status") or "—")
    c3.metric("Đã quét", view.get("scanned_count") or 0)
    c4.metric("Nói", view.get("notable_count") or 0)
    if view.get("camera_cutoff_timestamp"):
        st.caption(f"Camera PIT cutoff: `{view['camera_cutoff_timestamp']}`")
    observations = [r for r in (view.get("observations") or []) if isinstance(r, dict)]
    if not observations:
        st.info(view.get("headline_vi") or NO_INTEREST_VI)
        return view
    st.markdown(view.get("headline_vi") or "")
    observations.sort(key=lambda r: (r.get("presentation_rank", 99), r.get("symbol") or ""))
    for rec in observations:
        st.markdown(
            f"**{rec.get('symbol')}** · {rec.get('interest_level')} · "
            f"{rec.get('observation_relation')}  \n"
            f"{_family_line(rec)}  \n"
            f"{rec.get('evidence_summary')}"
        )
    return view

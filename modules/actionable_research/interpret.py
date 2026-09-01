"""Vietnamese research interpretation. Never emits BUY authority."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from modules.actionable_research.contracts import (
    AUTHORITY_LABEL,
    EDGE_STATUS_ACTIVE_MATCH,
    EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE,
    EDGE_STATUS_NO_ACTIVE_MATCH,
    EDGE_STATUS_UNKNOWN,
    FOREIGN_STRONG_BUY,
    INTEREST_HIGH,
    INTEREST_LOW,
    INTEREST_MEDIUM,
    INTEREST_NONE,
    INTEREST_UNABLE,
    MONEY_FLOW_STRONG,
    MONEY_FLOW_UNKNOWN,
    NO_INTEREST_VI,
    RANK_ACTIVE_FF,
    RANK_ACTIVE_MF,
    RANK_ACTIVE_MF_FF,
    RANK_ACTIVE_ONLY,
    RANK_FF_STANDALONE,
    RANK_MF_FF,
    RANK_MF_STANDALONE,
    RANK_NOT_NOTABLE,
    CAMERA_DATA_FEED_MISSING,
    CAMERA_DATA_MISSING_SYMBOL,
    FOREIGN_UNKNOWN,
)


def rank_key(rec: Dict[str, Any]) -> Tuple[int, str]:
    active = rec.get("edge_status") == EDGE_STATUS_ACTIVE_MATCH
    mf = rec.get("money_flow_status") == MONEY_FLOW_STRONG
    ff = rec.get("foreign_flow_status") == FOREIGN_STRONG_BUY
    if active and mf and ff:
        return RANK_ACTIVE_MF_FF, rec.get("symbol") or ""
    if active and mf:
        return RANK_ACTIVE_MF, rec.get("symbol") or ""
    if active and ff:
        return RANK_ACTIVE_FF, rec.get("symbol") or ""
    if mf and ff:
        return RANK_MF_FF, rec.get("symbol") or ""
    if mf:
        return RANK_MF_STANDALONE, rec.get("symbol") or ""
    if ff:
        return RANK_FF_STANDALONE, rec.get("symbol") or ""
    if active:
        return RANK_ACTIVE_ONLY, rec.get("symbol") or ""
    return RANK_NOT_NOTABLE, rec.get("symbol") or ""


def is_notable(rec: Dict[str, Any]) -> bool:
    return rank_key(rec)[0] < RANK_NOT_NOTABLE


def interest_level(rec: Dict[str, Any]) -> str:
    rank, _ = rank_key(rec)
    if rank == RANK_ACTIVE_MF_FF:
        return INTEREST_HIGH
    if rank in {RANK_ACTIVE_MF, RANK_ACTIVE_FF, RANK_MF_FF}:
        return INTEREST_HIGH if rank == RANK_MF_FF else INTEREST_MEDIUM
    if rank in {RANK_MF_STANDALONE, RANK_FF_STANDALONE}:
        return INTEREST_MEDIUM
    if rank == RANK_ACTIVE_ONLY:
        return INTEREST_LOW
    cam = rec.get("camera_data_status")
    edge = rec.get("edge_status")
    foreign = rec.get("foreign_flow_status")
    if (
        edge == EDGE_STATUS_UNKNOWN
        and rec.get("money_flow_status") == MONEY_FLOW_UNKNOWN
        and foreign == FOREIGN_UNKNOWN
        and cam in {CAMERA_DATA_FEED_MISSING, CAMERA_DATA_MISSING_SYMBOL}
    ):
        # Still a valid research record; not UNABLE unless the whole session is.
        return INTEREST_NONE
    return INTEREST_NONE


def missing_evidence(rec: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    if rec.get("edge_status") == EDGE_STATUS_UNKNOWN:
        missing.append("EDGE_RECOGNITION_OR_MEMORY")
    if rec.get("money_flow_status") == MONEY_FLOW_UNKNOWN:
        cam = rec.get("camera_data_status")
        if cam == CAMERA_DATA_FEED_MISSING:
            missing.append("CAMERA_FEED")
        elif cam == CAMERA_DATA_MISSING_SYMBOL:
            missing.append("CAMERA_SYMBOL_BARS")
        else:
            missing.append("CAMERA_MONEY_FLOW_ASSESSMENT")
    if rec.get("foreign_flow_status") == FOREIGN_UNKNOWN:
        missing.append("FOREIGN_FLOW")
    if rec.get("stock_state_source_status") not in {"OK", None, ""}:
        if rec.get("stock_state_source_status") in {
            "FREEZE_UNAVAILABLE",
            "SESSION_NOT_IN_FREEZE",
        }:
            missing.append("T0_FREEZE")
    return missing


def reasons(rec: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    edge = rec.get("edge_status")
    if edge == EDGE_STATUS_ACTIVE_MATCH:
        ids = rec.get("matched_edge_ids") or []
        out.append(f"ACTIVE_MATCH:{','.join(ids) if ids else 'yes'}")
    elif edge == EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE:
        out.append("NO_ACTIVE_EDGE_AVAILABLE")
    elif edge == EDGE_STATUS_NO_ACTIVE_MATCH:
        out.append("NO_ACTIVE_MATCH")
    elif edge == EDGE_STATUS_UNKNOWN:
        out.append("EDGE_UNKNOWN")
    mf = rec.get("money_flow_status")
    if mf == MONEY_FLOW_STRONG:
        out.append("MONEY_FLOW_STRONG")
    elif mf == MONEY_FLOW_UNKNOWN:
        out.append("CAMERA_UNKNOWN_NOT_WEAK")
    ff = rec.get("foreign_flow_status")
    if ff == FOREIGN_STRONG_BUY:
        out.append("FOREIGN_STRONG_BUY")
    elif ff == FOREIGN_UNKNOWN:
        out.append("FOREIGN_UNKNOWN_NOT_ZERO")
    ss = rec.get("sweetspot_status")
    if ss == "LEGACY_HEURISTIC_AUXILIARY":
        out.append("SWEETSPOT_AUXILIARY_NON_AUTHORITATIVE")
    out.append("AUTHORITY_RESEARCH_ONLY")
    return out


def evidence_summary_vi(rec: Dict[str, Any]) -> str:
    edge = rec.get("edge_status")
    mf = rec.get("money_flow_status")
    ff = rec.get("foreign_flow_status")
    cam = rec.get("camera_data_status")

    active = edge == EDGE_STATUS_ACTIVE_MATCH
    mf_strong = mf == MONEY_FLOW_STRONG
    ff_strong = ff == FOREIGN_STRONG_BUY
    camera_missing = cam in {CAMERA_DATA_FEED_MISSING, CAMERA_DATA_MISSING_SYMBOL} or mf == MONEY_FLOW_UNKNOWN

    if active and mf_strong and ff_strong:
        return "Cổ phiếu khớp ACTIVE edge + dòng tiền vào mạnh + nước ngoài mua mạnh."
    if active and mf_strong:
        return "Cổ phiếu khớp ACTIVE edge; Camera xác nhận dòng tiền vào mạnh."
    if active and ff_strong:
        return "Cổ phiếu khớp ACTIVE edge; nước ngoài mua mạnh (EOD, không phải Camera realtime)."
    if active and camera_missing:
        return "Cổ phiếu khớp ACTIVE edge; Camera chưa xác nhận dòng tiền mạnh."
    if active:
        return "Cổ phiếu khớp ACTIVE edge; Camera chưa xác nhận dòng tiền mạnh."
    if mf_strong and ff_strong:
        return "Không có ACTIVE edge đã được xác nhận, nhưng dòng tiền intraday vào cổ phiếu đang mạnh và nước ngoài mua mạnh."
    if mf_strong:
        return "Không có ACTIVE edge đã được xác nhận, nhưng dòng tiền intraday vào cổ phiếu đang mạnh."
    if ff_strong:
        return "Không có ACTIVE edge đã được xác nhận, nhưng nước ngoài mua mạnh (nguồn EOD, không phải Camera realtime)."
    if camera_missing and cam in {CAMERA_DATA_FEED_MISSING, CAMERA_DATA_MISSING_SYMBOL}:
        return "Không thể đánh giá Camera do thiếu dữ liệu intraday."
    if edge in {EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE, EDGE_STATUS_NO_ACTIVE_MATCH} and not mf_strong and not ff_strong:
        return "Không có edge đáng tin cậy và không có dòng tiền bất thường."
    return "Bằng chứng không nổi bật trong phiên này."


def finalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    out["authority"] = AUTHORITY_LABEL
    out["research_label"] = AUTHORITY_LABEL
    out["interest_level"] = interest_level(out)
    out["evidence_summary"] = evidence_summary_vi(out)
    out["reasons"] = reasons(out)
    out["missing_evidence"] = missing_evidence(out)
    rank, _ = rank_key(out)
    out["presentation_rank"] = rank
    out["notable"] = is_notable(out)
    return out


def session_surface(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    notable = [r for r in records if r.get("notable")]
    notable.sort(key=lambda r: (r.get("presentation_rank", 99), r.get("symbol") or ""))
    if not notable:
        headline = NO_INTEREST_VI
    else:
        top = notable[0]
        headline = f"{len(notable)} cổ phiếu có bằng chứng đáng chú ý. {top.get('evidence_summary')}"
    return {
        "notable_count": len(notable),
        "surfaced_symbols": [r.get("symbol") for r in notable],
        "headline_vi": headline,
        "authority": AUTHORITY_LABEL,
        "no_interest": len(notable) == 0,
    }
